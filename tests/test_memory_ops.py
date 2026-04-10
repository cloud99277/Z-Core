import json
import unittest

from tests.helpers import TestHome, run_zcore


class MemoryOpsTests(unittest.TestCase):
    def test_memory_write_persists_entry(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            proc = run_zcore(
                "memory",
                "write",
                "决定使用零依赖架构",
                "--topic",
                "architecture",
                "--tags",
                "decision,phase5",
                "--json",
                home=ctx.home,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["topic"], "architecture")
            topic_file = ctx.home / ".ai-memory" / "topics" / "architecture.md"
            self.assertTrue(topic_file.exists())
            self.assertIn("决定使用零依赖架构", topic_file.read_text(encoding="utf-8"))

    def test_memory_topics_lists_topic_counts(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)
            run_zcore("memory", "write", "one", "--topic", "alpha", "--json", home=ctx.home)
            run_zcore("memory", "write", "two", "--topic", "alpha", "--json", home=ctx.home)
            run_zcore("memory", "write", "three", "--topic", "beta", "--json", home=ctx.home)

            proc = run_zcore("memory", "topics", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            counts = {item["topic"]: item["count"] for item in payload}
            self.assertEqual(counts["alpha"], 2)
            self.assertEqual(counts["beta"], 1)

    def test_memory_stats_reports_totals_and_recent_write(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)
            run_zcore("memory", "write", "one", "--topic", "alpha", "--json", home=ctx.home)

            proc = run_zcore("memory", "stats", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["topic_count"], 1)
            self.assertEqual(payload["topic_entries"], 1)
            self.assertEqual(payload["total_entries"], 1)
            self.assertGreaterEqual(payload["disk_usage_bytes"], 1)
            self.assertTrue(payload["recent_write_at"])
