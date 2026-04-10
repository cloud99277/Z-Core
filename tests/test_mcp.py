import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from zcore.engines.mcp import McpEngine
from zcore.runtime import RuntimePaths
from tests.helpers import TestHome, run_zcore


class McpTests(unittest.TestCase):
    def test_add_server(self) -> None:
        with TestHome() as ctx:
            proc = run_zcore(
                "mcp",
                "add",
                "filesystem",
                "--command",
                "npx",
                "--args",
                "-y,@modelcontextprotocol/server-filesystem,/tmp",
                "--json",
                home=ctx.home,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            registry = (ctx.home / ".zcore" / "mcp-servers.toml").read_text(encoding="utf-8")
            self.assertIn("[servers.filesystem]", registry)
            self.assertIn('@modelcontextprotocol/server-filesystem', registry)

    def test_add_duplicate_server(self) -> None:
        with TestHome() as ctx:
            first = run_zcore("mcp", "add", "echoer", "--command", "echo", "--json", home=ctx.home)
            self.assertEqual(first.returncode, 0, first.stderr)

            second = run_zcore("mcp", "add", "echoer", "--command", "echo", "--json", home=ctx.home)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("already exists", second.stdout)

    def test_remove_server(self) -> None:
        with TestHome() as ctx:
            run_zcore("mcp", "add", "echoer", "--command", "echo", "--json", home=ctx.home)

            proc = run_zcore("mcp", "remove", "echoer", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["removed"], "echoer")

            listed = run_zcore("mcp", "list", "--json", home=ctx.home)
            self.assertEqual(json.loads(listed.stdout), [])

    def test_remove_nonexistent(self) -> None:
        with TestHome() as ctx:
            proc = run_zcore("mcp", "remove", "missing", "--json", home=ctx.home)
            self.assertNotEqual(proc.returncode, 0)
            payload = json.loads(proc.stdout)
            self.assertFalse(payload["ok"])

    def test_list_empty(self) -> None:
        with TestHome() as ctx:
            proc = run_zcore("mcp", "list", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout), [])

    def test_list_servers(self) -> None:
        with TestHome() as ctx:
            run_zcore("mcp", "add", "echoer", "--command", "echo", "--args", "hello", "--json", home=ctx.home)
            run_zcore("mcp", "add", "shell", "--command", "bash", "--env", "DEBUG=1", "--json", home=ctx.home)

            proc = run_zcore("mcp", "list", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual([item["name"] for item in payload], ["echoer", "shell"])
            self.assertEqual(payload[0]["args_count"], 1)
            self.assertEqual(payload[1]["env_count"], 1)

    def test_sync_dry_run(self) -> None:
        with TestHome() as ctx:
            run_zcore("mcp", "add", "echoer", "--command", "echo", "--json", home=ctx.home)

            proc = run_zcore("mcp", "sync", "--agent", "claude", "--dry-run", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["dry_run"])
            self.assertFalse((ctx.home / ".claude" / "claude_desktop_config.json").exists())

    def test_sync_to_agent(self) -> None:
        with TestHome() as ctx:
            run_zcore(
                "mcp",
                "add",
                "filesystem",
                "--command",
                "npx",
                "--args",
                "-y,@modelcontextprotocol/server-filesystem,/tmp",
                "--json",
                home=ctx.home,
            )

            proc = run_zcore("mcp", "sync", "--agent", "claude", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["results"][0]["servers_added"], ["filesystem"])

            config_path = ctx.home / ".claude" / "claude_desktop_config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["mcpServers"]["filesystem"]["command"], "npx")

    def test_sync_preserves_other_config(self) -> None:
        with TestHome() as ctx:
            run_zcore("mcp", "add", "echoer", "--command", "echo", "--json", home=ctx.home)
            gemini_config = ctx.home / ".gemini" / "settings.json"
            gemini_config.parent.mkdir(parents=True, exist_ok=True)
            gemini_config.write_text(json.dumps({"theme": "dark", "mcpServers": {"old": {"command": "old"}}}), encoding="utf-8")

            proc = run_zcore("mcp", "sync", "--agent", "gemini", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["results"][0]["servers_removed"], ["old"])

            config = json.loads(gemini_config.read_text(encoding="utf-8"))
            self.assertEqual(config["theme"], "dark")
            self.assertIn("echoer", config["mcpServers"])

    def test_diff(self) -> None:
        with TestHome() as ctx:
            run_zcore("mcp", "add", "echoer", "--command", "echo", "--json", home=ctx.home)
            claude_config = ctx.home / ".claude" / "claude_desktop_config.json"
            claude_config.parent.mkdir(parents=True, exist_ok=True)
            claude_config.write_text(json.dumps({"mcpServers": {"old": {"command": "old"}}}), encoding="utf-8")

            proc = run_zcore("mcp", "diff", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            claude = payload["agents"]["claude"]
            self.assertEqual(claude["servers_added"], ["echoer"])
            self.assertEqual(claude["servers_removed"], ["old"])

    def test_engine_sync_updates_existing_server(self) -> None:
        with TestHome() as ctx:
            run_zcore("mcp", "add", "echoer", "--command", "echo", "--args", "hello", "--json", home=ctx.home)
            base_dir = ctx.home / ".zcore"
            memory_dir = ctx.home / ".ai-memory"
            paths = RuntimePaths(
                base_dir=base_dir,
                config_path=base_dir / "config.toml",
                shared_rules_path=base_dir / "shared-rules.yaml",
                mcp_registry_path=base_dir / "mcp-servers.toml",
                sessions_dir=base_dir / "sessions",
                session_index_path=base_dir / "sessions" / "index.json",
                logs_dir=base_dir / "logs",
                hooks_dir=base_dir / "hooks",
                pre_hooks_dir=base_dir / "hooks" / "pre-execute.d",
                post_hooks_dir=base_dir / "hooks" / "post-execute.d",
                cache_dir=base_dir / "cache",
                pending_dir=base_dir / "pending",
                memory_dir=memory_dir,
                topics_dir=memory_dir / "topics",
                staging_dir=memory_dir / "staging",
                whiteboard_path=memory_dir / "whiteboard.json",
                extraction_log_path=memory_dir / "extraction-log.jsonl",
                skills_dir=ctx.home / ".ai-skills",
                knowledge_db_path=ctx.home / ".lancedb" / "knowledge",
                lock_dir=base_dir / "locks",
            )
            engine = McpEngine(paths)
            codex_config = ctx.home / ".codex" / "config.json"
            codex_config.parent.mkdir(parents=True, exist_ok=True)
            codex_config.write_text(json.dumps({"mcpServers": {"echoer": {"command": "echo", "args": ["old"]}}}), encoding="utf-8")

            with patch.dict(os.environ, {"HOME": str(ctx.home)}):
                result = engine.sync_to_agent("codex")
            self.assertEqual(result.servers_updated, ["echoer"])
            config = json.loads(codex_config.read_text(encoding="utf-8"))
            self.assertEqual(config["mcpServers"]["echoer"]["args"], ["hello"])
