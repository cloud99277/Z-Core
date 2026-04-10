import gzip
import json
import unittest

from tests.helpers import TestHome, run_zcore


class SessionLifecycleTests(unittest.TestCase):
    def test_session_show_outputs_metadata_and_context_size(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            start = run_zcore("session", "start", "--project", "kitclaw", "--agent", "codex", "--json", home=ctx.home)
            self.assertEqual(start.returncode, 0, start.stderr)
            session_id = json.loads(start.stdout)["session_id"]

            session_dir = ctx.home / ".zcore" / "sessions" / session_id
            with gzip.open(session_dir / "context.json.gz", "wt", encoding="utf-8") as handle:
                json.dump([{"role": "user", "content": "hello"}], handle)

            proc = run_zcore("session", "show", session_id, "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["session_id"], session_id)
            self.assertEqual(payload["project"], "kitclaw")
            self.assertGreater(payload["context_snapshot_size"], 0)

    def test_session_cleanup_dry_run_lists_old_sessions(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            start = run_zcore("session", "start", "--project", "kitclaw", "--agent", "codex", "--json", home=ctx.home)
            self.assertEqual(start.returncode, 0, start.stderr)
            session_id = json.loads(start.stdout)["session_id"]
            session_dir = ctx.home / ".zcore" / "sessions" / session_id
            meta_path = session_dir / "meta.json"
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            payload["status"] = "completed"
            payload["ended_at"] = "2026-01-01T00:00:00+00:00"
            meta_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            index_path = ctx.home / ".zcore" / "sessions" / "index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["sessions"][0] = payload
            index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

            proc = run_zcore("session", "cleanup", "--older-than", "30d", "--dry-run", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(proc.stdout)
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["removed"][0]["session_id"], session_id)
            self.assertTrue(session_dir.exists())

    def test_session_cleanup_removes_old_session(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            start = run_zcore("session", "start", "--project", "kitclaw", "--agent", "codex", "--json", home=ctx.home)
            session_id = json.loads(start.stdout)["session_id"]
            session_dir = ctx.home / ".zcore" / "sessions" / session_id
            meta_path = session_dir / "meta.json"
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            payload["status"] = "completed"
            payload["ended_at"] = "2026-01-01T00:00:00+00:00"
            meta_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            index_path = ctx.home / ".zcore" / "sessions" / "index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["sessions"][0] = payload
            index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

            proc = run_zcore("session", "cleanup", "--older-than", "30d", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(proc.stdout)
            self.assertFalse(result["dry_run"])
            self.assertEqual(result["removed"][0]["session_id"], session_id)
            self.assertFalse(session_dir.exists())
