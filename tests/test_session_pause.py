import json
import unittest

from tests.helpers import TestHome, run_zcore


class SessionPauseTests(unittest.TestCase):
    def test_session_pause_defaults_to_latest_active_session(self) -> None:
        with TestHome() as ctx:
            run_zcore("init", "--json", home=ctx.home)
            start = run_zcore("session", "start", "--project", "kitclaw", "--agent", "codex", "--json", home=ctx.home)
            session_id = json.loads(start.stdout)["session_id"]

            proc = run_zcore("session", "pause", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["session_id"], session_id)
            self.assertEqual(payload["status"], "paused")
            self.assertTrue(payload["paused_at"])

    def test_session_resume_defaults_to_latest_paused_session(self) -> None:
        with TestHome() as ctx:
            run_zcore("init", "--json", home=ctx.home)
            start = run_zcore("session", "start", "--project", "kitclaw", "--agent", "codex", "--json", home=ctx.home)
            session_id = json.loads(start.stdout)["session_id"]
            run_zcore("session", "pause", "--session-id", session_id, "--json", home=ctx.home)

            proc = run_zcore("session", "resume", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["session_id"], session_id)
            self.assertEqual(payload["status"], "active")
            self.assertTrue(payload["resumed_at"])

    def test_session_pause_resume_end_flow(self) -> None:
        with TestHome() as ctx:
            run_zcore("init", "--json", home=ctx.home)
            start = run_zcore("session", "start", "--project", "kitclaw", "--agent", "codex", "--json", home=ctx.home)
            session_id = json.loads(start.stdout)["session_id"]

            pause = run_zcore("session", "pause", "--session-id", session_id, "--json", home=ctx.home)
            self.assertEqual(json.loads(pause.stdout)["status"], "paused")

            resume = run_zcore("session", "resume", "--session-id", session_id, "--json", home=ctx.home)
            self.assertEqual(json.loads(resume.stdout)["status"], "active")

            end = run_zcore("session", "end", "--session-id", session_id, "--json", home=ctx.home)
            self.assertEqual(end.returncode, 0, end.stderr)
            payload = json.loads(end.stdout)
            self.assertEqual(payload["status"], "completed")
