import json
import unittest

from tests.helpers import TestHome, run_zcore


class MemoryExpireTests(unittest.TestCase):
    def test_memory_expire_check_dry_run_lists_candidates(self) -> None:
        with TestHome() as ctx:
            run_zcore("init", "--json", home=ctx.home)
            topic_file = ctx.home / ".ai-memory" / "topics" / "kitclaw.md"
            topic_file.parent.mkdir(parents=True, exist_ok=True)
            topic_file.write_text(
                "- [fact] Old fact (source: test, confidence: 1.00, date: 2025-01-01)\n",
                encoding="utf-8",
            )

            proc = run_zcore("memory", "expire-check", "--dry-run", "--older-than", "90d", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(len(payload["expired"]), 1)
            self.assertIn("[fact] Old fact", topic_file.read_text(encoding="utf-8"))

    def test_memory_expire_check_marks_entries_as_expired(self) -> None:
        with TestHome() as ctx:
            run_zcore("init", "--json", home=ctx.home)
            topic_file = ctx.home / ".ai-memory" / "topics" / "kitclaw.md"
            topic_file.parent.mkdir(parents=True, exist_ok=True)
            topic_file.write_text(
                "- [fact] Old fact (source: test, confidence: 1.00, date: 2025-01-01)\n",
                encoding="utf-8",
            )

            proc = run_zcore("memory", "expire-check", "--older-than", "90d", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(len(payload["expired"]), 1)
            self.assertEqual(payload["updated_topics"], ["kitclaw"])
            self.assertIn("[expired] Old fact", topic_file.read_text(encoding="utf-8"))
