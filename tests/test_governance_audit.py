import json
import unittest

from tests.helpers import TestHome, run_zcore


class GovernanceAuditTests(unittest.TestCase):
    def test_governance_audit_summarizes_rules_and_logs(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            run_zcore("governance", "allow", "shell(npm test)", "--json", home=ctx.home)
            run_zcore("governance", "deny", "file.write(.env)", "--json", home=ctx.home)

            log_path = ctx.home / ".zcore" / "logs" / "executions.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "timestamp": "2026-04-10T00:00:00+00:00",
                                "skill_name": "memory-manager",
                                "status": "ok",
                                "output": "",
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp": "2026-04-10T00:01:00+00:00",
                                "skill_name": "memory-manager",
                                "status": "blocked",
                                "output": "dangerous shell command: rm -rf /",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            proc = run_zcore("governance", "audit", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["rule_stats"]["allow"], 1)
            self.assertEqual(payload["rule_stats"]["deny"], 1)
            self.assertEqual(payload["high_frequency_skills"][0]["skill_name"], "memory-manager")
            self.assertEqual(len(payload["recent_denied_events"]), 1)
            self.assertEqual(len(payload["dangerous_command_history"]), 1)
