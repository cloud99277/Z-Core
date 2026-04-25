import json
import os
import unittest
from pathlib import Path

from tests.helpers import TestHome, pushd, run_zcore

from zcore.engines.agent_setup import AgentSetupEngine, ZCORE_START
from zcore.runtime import RuntimePaths


class AgentSetupTests(unittest.TestCase):
    def test_detect_agents_reads_expected_files(self) -> None:
        with TestHome(with_workspace=True) as ctx:
            (ctx.home / ".claude").mkdir(parents=True)
            (ctx.home / ".gemini").mkdir(parents=True)
            (ctx.home / ".codex").mkdir(parents=True)
            (ctx.home / ".claude" / "CLAUDE.md").write_text("hello", encoding="utf-8")
            (ctx.home / ".gemini" / "GEMINI.md").write_text("hello", encoding="utf-8")
            (ctx.home / ".codex" / "AGENTS.md").write_text(f"{ZCORE_START}\nold\n<!-- ZCORE:END -->\n", encoding="utf-8")

            with pushd(ctx.workspace):
                os.environ["HOME"] = str(ctx.home)
                os.environ["ZCORE_HOME"] = str(ctx.home / ".zcore")
                paths = RuntimePaths.discover()
                engine = AgentSetupEngine(paths)
                detected = {item.name: item for item in engine.detect_agents()}

            self.assertTrue(detected["claude"].detected)
            self.assertTrue(detected["gemini"].detected)
            self.assertTrue(detected["codex"].detected)
            self.assertTrue(detected["codex"].zcore_integrated)

    def test_setup_agent_injects_block_and_is_idempotent(self) -> None:
        with TestHome() as ctx:
            (ctx.home / ".claude").mkdir(parents=True)
            target = ctx.home / ".claude" / "CLAUDE.md"
            target.write_text("# Claude\n", encoding="utf-8")

            os.environ["HOME"] = str(ctx.home)
            os.environ["ZCORE_HOME"] = str(ctx.home / ".zcore")
            paths = RuntimePaths.discover()
            engine = AgentSetupEngine(paths)

            first = engine.setup_agent("claude")
            second = engine.setup_agent("claude")

            self.assertTrue(first.success)
            self.assertIn("inserted managed Z-Core block", first.changes)
            self.assertIsNotNone(first.backup_path)
            self.assertTrue(target.read_text(encoding="utf-8").count(ZCORE_START) == 1)
            self.assertIn("--messages <messages.json>", target.read_text(encoding="utf-8"))
            self.assertEqual(second.changes, ["no changes needed"])

    def test_setup_detect_and_dry_run_cli(self) -> None:
        with TestHome(with_workspace=True) as ctx:
            (ctx.home / ".gemini").mkdir(parents=True)
            (ctx.home / ".gemini" / "GEMINI.md").write_text("# Gemini\n", encoding="utf-8")

            detect = run_zcore("setup", "detect", "--json", home=ctx.home, cwd=ctx.workspace)
            self.assertEqual(detect.returncode, 0, detect.stderr)
            payload = json.loads(detect.stdout)
            self.assertTrue(any(item["name"] == "gemini" and item["detected"] for item in payload))

            dry_run = run_zcore("setup", "gemini", "--dry-run", "--json", home=ctx.home, cwd=ctx.workspace)
            self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
            result = json.loads(dry_run.stdout)
            self.assertEqual(result["agent"], "gemini")
            self.assertIsNone(result["backup_path"])
            self.assertIn("inserted managed Z-Core block", result["changes"])
