import json
import os
import unittest

from tests.helpers import TestHome, run_zcore

from zcore.hooks.lifecycle import HookRunner
from zcore.models.skill import SkillManifest
from zcore.runtime import RuntimePaths


class GovernanceExtensionTests(unittest.TestCase):
    def test_governance_allow_and_deny_persist_rules(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            allow = run_zcore("governance", "allow", "shell(npm test)", "--json", home=ctx.home)
            deny = run_zcore("governance", "deny", "file.write(.env)", "--json", home=ctx.home)

            self.assertEqual(allow.returncode, 0, allow.stderr)
            self.assertEqual(deny.returncode, 0, deny.stderr)

            rules = run_zcore("governance", "rules", "--json", home=ctx.home)
            payload = json.loads(rules.stdout)
            decisions = {(item["action"], item["pattern"]): item["decision"] for item in payload}
            self.assertEqual(decisions[("shell", "npm test")], "allow")
            self.assertEqual(decisions[("file.write", ".env")], "deny")

    def test_governance_log_reads_recent_entries(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            log_path = ctx.home / ".zcore" / "logs" / "executions.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "\n".join(
                    [
                        json.dumps({"timestamp": "2026-04-10T00:00:00+00:00", "skill_name": "a", "status": "ok"}),
                        json.dumps({"timestamp": "2026-04-10T00:01:00+00:00", "skill_name": "b", "status": "error"}),
                        json.dumps({"timestamp": "2026-04-10T00:02:00+00:00", "skill_name": "a", "status": "ok"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            proc = run_zcore("governance", "log", "--last", "2", "--skill", "a", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(len(payload), 2)
            self.assertTrue(all(item["skill_name"] == "a" for item in payload))

    def test_custom_pre_hooks_run_after_builtin_and_can_block(self) -> None:
        with TestHome() as ctx:
            os.environ["HOME"] = str(ctx.home)
            os.environ["ZCORE_HOME"] = str(ctx.home / ".zcore")
            paths = RuntimePaths.discover()
            paths.ensure_runtime_dirs()

            env_file = ctx.home / "hook-env.txt"
            (paths.pre_hooks_dir / "10-pass.sh").write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        f'echo \"$ZCORE_SKILL_NAME:$ZCORE_SESSION_ID:$ZCORE_PROJECT\" > "{env_file}"',
                        'echo "pre-ok"',
                        "exit 0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (paths.pre_hooks_dir / "20-block.py").write_text(
                'print("blocked by custom hook")\nraise SystemExit(1)\n',
                encoding="utf-8",
            )

            manifest = SkillManifest(name="demo-skill")
            runner = HookRunner(paths)
            allowed, results = runner.execute_chain(
                ["validate-input"],
                manifest=manifest,
                args={},
                session_id="sess-1",
                project="kitclaw",
                phase="pre",
            )

            self.assertFalse(allowed)
            self.assertEqual(results[0].hook_name, "validate-input")
            self.assertEqual(results[1].hook_name, "10-pass.sh")
            self.assertEqual(results[2].hook_name, "20-block.py")
            self.assertEqual(env_file.read_text(encoding="utf-8").strip(), "demo-skill:sess-1:kitclaw")
