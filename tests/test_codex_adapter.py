from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zcore.adapters.codex_adapter import CodexAdapter
from zcore.engines.harvester import HarvesterEngine
from zcore.runtime import RuntimePaths


class CodexAdapterTests(unittest.TestCase):
    SESSION_ID = "11111111-1111-1111-1111-111111111111"

    def test_discover_keeps_first_duplicate_uuid_and_records_error(self):
        with tempfile.TemporaryDirectory() as tempdir:
            sessions_dir = Path(tempdir) / "sessions"
            self._write_session(
                sessions_dir,
                "2026",
                "05",
                "01",
                self.SESSION_ID,
                [self._turn_context("/work/demo"), self._message("user", "hello")],
            )
            self._write_session(
                sessions_dir,
                "2026",
                "05",
                "02",
                self.SESSION_ID,
                [self._turn_context("/work/other"), self._message("user", "second")],
            )
            (sessions_dir / "not-a-rollout.jsonl").write_text("{}\n", encoding="utf-8")

            adapter = CodexAdapter(sessions_dir)
            discovered = adapter.discover()
            errors = adapter.drain_errors()

        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]["source_session_id"], self.SESSION_ID)
        self.assertEqual({item["codex_session_id"] for item in discovered}, {self.SESSION_ID})
        self.assertEqual(discovered[0]["started_at"], "2026-05-01T10:00:00")
        self.assertTrue(any("duplicate Codex session UUID" in error for error in errors))

    def test_unique_uuid_is_public_id_and_survives_date_path_move(self):
        with tempfile.TemporaryDirectory() as tempdir:
            sessions_dir = Path(tempdir) / "sessions"
            source_path = self._write_session(
                sessions_dir,
                "2026",
                "05",
                "01",
                self.SESSION_ID,
                [self._turn_context("/work/demo"), self._message("user", "before move")],
            )
            adapter = CodexAdapter(sessions_dir)
            session_id = str(adapter.discover()[0]["source_session_id"])
            moved_path = self._session_path(sessions_dir, "2026", "05", "02", self.SESSION_ID)
            moved_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.rename(moved_path)

            session = adapter.ingest(session_id)

        self.assertEqual(session_id, self.SESSION_ID)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.source_session_id, self.SESSION_ID)
        self.assertEqual(session.messages, [{"role": "user", "content": "before move"}])

    def test_duplicate_uuid_ingest_uses_same_sorted_first_session(self):
        with tempfile.TemporaryDirectory() as tempdir:
            sessions_dir = Path(tempdir) / "sessions"
            self._write_session(
                sessions_dir,
                "2026",
                "05",
                "01",
                self.SESSION_ID,
                [self._message("user", "first")],
            )
            self._write_session(
                sessions_dir,
                "2026",
                "05",
                "02",
                self.SESSION_ID,
                [self._message("user", "second")],
            )
            adapter = CodexAdapter(sessions_dir)
            discovered = adapter.discover()

            session = adapter.ingest(self.SESSION_ID)

        self.assertEqual([item["source_session_id"] for item in discovered], [self.SESSION_ID])
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.source_session_id, self.SESSION_ID)
        self.assertEqual(session.messages, [{"role": "user", "content": "first"}])
        self.assertTrue(any("duplicate Codex session UUID" in error for error in adapter.drain_errors()))

    def test_discover_filters_by_turn_context_cwd(self):
        with tempfile.TemporaryDirectory() as tempdir:
            sessions_dir = Path(tempdir) / "sessions"
            self._write_session(
                sessions_dir,
                "2026",
                "05",
                "01",
                self.SESSION_ID,
                [self._turn_context("/work/demo"), self._message("user", "keep")],
            )
            self._write_session(
                sessions_dir,
                "2026",
                "05",
                "02",
                "22222222-2222-2222-2222-222222222222",
                [self._turn_context("/work/other"), self._message("user", "skip")],
            )

            discovered = CodexAdapter(sessions_dir).discover(project="/work/demo")

        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]["project"], "/work/demo")

    def test_ingest_extracts_message_whitelist_and_text_content_forms(self):
        with tempfile.TemporaryDirectory() as tempdir:
            sessions_dir = Path(tempdir) / "sessions"
            self._write_session(
                sessions_dir,
                "2026",
                "05",
                "01",
                self.SESSION_ID,
                [
                    self._turn_context("/work/demo"),
                    self._message("user", "plain prompt", "2026-05-01T10:01:00Z"),
                    self._message(
                        "assistant",
                        [
                            {"type": "text", "text": "first answer"},
                            {"type": "tool_use", "name": "read_file"},
                            {"type": "output_text", "text": "second answer"},
                        ],
                        "2026-05-01T10:02:00Z",
                    ),
                    self._message(
                        "user",
                        [{"type": "input_text", "text": "follow up"}, {"type": "image", "url": "ignored"}],
                        "2026-05-01T10:03:00Z",
                    ),
                    {"type": "response_item", "payload": {"type": "reasoning", "summary": []}},
                    self._message("tool", "do not collect", "2026-05-01T10:04:00Z"),
                    {"type": "event_msg", "payload": {"type": "token_count"}},
                ],
            )
            adapter = CodexAdapter(sessions_dir)
            session_id = str(adapter.discover()[0]["source_session_id"])

            session = adapter.ingest(session_id)

        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(
            session.messages,
            [
                {"role": "user", "content": "plain prompt"},
                {"role": "assistant", "content": "first answer\nsecond answer"},
                {"role": "user", "content": "follow up"},
            ],
        )
        self.assertEqual(session.project, "/work/demo")
        self.assertEqual(session.started_at, "2026-05-01T10:00:00")
        self.assertEqual(session.ended_at, "2026-05-01T10:03:00Z")
        self.assertEqual(session.metadata["codex_session_id"], self.SESSION_ID)

    def test_ingest_allows_missing_turn_context_with_empty_project(self):
        with tempfile.TemporaryDirectory() as tempdir:
            sessions_dir = Path(tempdir) / "sessions"
            self._write_session(
                sessions_dir,
                "2026",
                "05",
                "01",
                self.SESSION_ID,
                [self._message("user", "no context")],
            )
            adapter = CodexAdapter(sessions_dir)

            session = adapter.ingest(str(adapter.discover()[0]["source_session_id"]))

        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.project, "")

    def test_health_check_reports_existing_sessions_directory(self):
        with tempfile.TemporaryDirectory() as tempdir:
            sessions_dir = Path(tempdir) / "sessions"
            sessions_dir.mkdir()

            health = CodexAdapter(sessions_dir).health_check()

        self.assertTrue(health["ok"])
        self.assertEqual(health["path"], str(sessions_dir))
        self.assertEqual(health["errors"], [])

    def test_bad_json_and_encoding_are_observable_without_blocking_valid_sibling(self):
        with self._isolated_home() as home:
            sessions_dir = home / ".codex" / "sessions"
            bad_json = self._session_path(sessions_dir, "2026", "05", "01", self.SESSION_ID)
            bad_json.parent.mkdir(parents=True)
            bad_json.write_text(
                "{invalid json}\n" + json.dumps(self._message("user", "valid after error")) + "\n",
                encoding="utf-8",
            )
            bad_encoding = self._session_path(
                sessions_dir,
                "2026",
                "05",
                "02",
                "22222222-2222-2222-2222-222222222222",
            )
            bad_encoding.parent.mkdir(parents=True)
            bad_encoding.write_bytes(b"\xff\xfe\x00")
            adapter = CodexAdapter(sessions_dir)
            engine = HarvesterEngine(RuntimePaths.discover())
            engine.adapters.clear()
            engine.register_adapter(adapter)

            payload = engine.ingest(source="codex", dry_run=True)

        self.assertEqual(payload["totals"]["ingested"], 1)
        self.assertGreater(payload["totals"]["errors"], 0)
        self.assertNotIn(str(home), json.dumps(payload))

    def test_discover_and_ingest_reject_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            sessions_dir = root / "sessions"
            outside = root / "outside"
            self._write_session(
                outside,
                "2026",
                "05",
                "01",
                self.SESSION_ID,
                [self._message("user", "outside")],
            )
            sessions_dir.mkdir()
            (sessions_dir / "2026").symlink_to(outside / "2026", target_is_directory=True)
            adapter = CodexAdapter(sessions_dir)

            discovered = adapter.discover()
            session = adapter.ingest(self.SESSION_ID)

        self.assertEqual(discovered, [])
        self.assertIsNone(session)
        self.assertTrue(adapter.health_check()["errors"])

    def test_harvester_skips_codex_session_matching_ingest_ignore(self):
        with self._isolated_home() as home:
            sessions_dir = home / ".codex" / "sessions"
            self._write_session(
                sessions_dir,
                "2026",
                "05",
                "01",
                self.SESSION_ID,
                [self._turn_context("/work/demo"), self._message("user", "ignored")],
            )
            zcore_home = home / ".zcore"
            zcore_home.mkdir()
            (zcore_home / "ingest-ignore").write_text("**/rollout-*.jsonl\n", encoding="utf-8")
            engine = HarvesterEngine(RuntimePaths.discover())
            engine.adapters.clear()
            engine.register_adapter(CodexAdapter(sessions_dir))

            payload = engine.ingest(source="codex", dry_run=True)

        self.assertEqual(payload["totals"], {"discovered": 1, "ingested": 0, "skipped": 1, "errors": 0})

    def test_harvester_redacts_codex_payload_before_persistence(self):
        with self._isolated_home() as home:
            sessions_dir = home / ".codex" / "sessions"
            self._write_session(
                sessions_dir,
                "2026",
                "05",
                "01",
                self.SESSION_ID,
                [
                    self._turn_context("/home/alice/private-project"),
                    self._message("user", "read /home/alice/secret.txt"),
                ],
            )
            engine = HarvesterEngine(RuntimePaths.discover())
            engine.adapters.clear()
            engine.register_adapter(CodexAdapter(sessions_dir))

            payload = engine.ingest(source="codex")
            saved = next((home / ".zcore" / "harvested" / "codex").glob("*.json"))
            saved_payload = json.loads(saved.read_text(encoding="utf-8"))

        self.assertEqual(payload["totals"]["ingested"], 1)
        self.assertNotIn("/home/alice", json.dumps(saved_payload))
        self.assertIn("[USER]", json.dumps(saved_payload))

    def test_harvester_keeps_existing_uuid_index_when_duplicate_appears(self):
        with self._isolated_home() as home:
            sessions_dir = home / ".codex" / "sessions"
            self._write_session(
                sessions_dir,
                "2026",
                "05",
                "01",
                self.SESSION_ID,
                [self._message("user", "first")],
            )
            engine = HarvesterEngine(RuntimePaths.discover())
            engine.adapters.clear()
            engine.register_adapter(CodexAdapter(sessions_dir))
            first = engine.ingest(source="codex")
            self._write_session(
                sessions_dir,
                "2026",
                "05",
                "02",
                self.SESSION_ID,
                [self._message("user", "duplicate")],
            )

            second = engine.ingest(source="codex")

        self.assertEqual(first["totals"]["ingested"], 1)
        self.assertEqual(second["totals"]["discovered"], 1)
        self.assertEqual(second["totals"]["ingested"], 0)
        self.assertEqual(second["totals"]["skipped"], 1)
        self.assertGreater(second["totals"]["errors"], 0)
        self.assertNotIn(str(home), json.dumps(second))
        self.assertIn("duplicate Codex session UUID", json.dumps(second))

    def test_harvester_auto_registers_codex_adapter(self):
        with self._isolated_home():
            engine = HarvesterEngine(RuntimePaths.discover())

        self.assertIn("codex", engine.adapters)

    def _write_session(
        self,
        sessions_dir: Path,
        year: str,
        month: str,
        day: str,
        session_id: str,
        events: list[dict[str, object]],
    ) -> Path:
        path = self._session_path(sessions_dir, year, month, day, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
        return path

    def _session_path(self, sessions_dir: Path, year: str, month: str, day: str, session_id: str) -> Path:
        filename = f"rollout-{year}-{month}-{day}T10-00-00-{session_id}.jsonl"
        return sessions_dir / year / month / day / filename

    @staticmethod
    def _turn_context(cwd: str) -> dict[str, object]:
        return {"type": "turn_context", "payload": {"cwd": cwd}}

    @staticmethod
    def _message(role: str, content: object, timestamp: str = "2026-05-01T10:00:00Z") -> dict[str, object]:
        return {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {"type": "message", "role": role, "content": content},
        }

    def _isolated_home(self):
        tempdir = tempfile.TemporaryDirectory(dir=Path.home())
        home = Path(tempdir.name) / "home"
        home.mkdir()
        env = {
            "HOME": str(home),
            "ZCORE_HOME": str(home / ".zcore"),
            "AI_MEMORY_DIR": str(home / ".ai-memory"),
            "AI_SKILLS_DIR": str(home / ".ai-skills"),
        }

        class Manager:
            def __enter__(self_nonlocal):
                self_nonlocal.patch = patch.dict("os.environ", env, clear=False)
                self_nonlocal.patch.__enter__()
                return home

            def __exit__(self_nonlocal, exc_type, exc, tb):
                self_nonlocal.patch.__exit__(exc_type, exc, tb)
                tempdir.cleanup()

        return Manager()
