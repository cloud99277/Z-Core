from __future__ import annotations

import json
from contextlib import redirect_stderr
from io import StringIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.helpers import run_zcore
from zcore.adapters.openclaw_adapter import OpenClawAdapter
from zcore.engines.harvester import HarvesterEngine
from zcore.runtime import RuntimePaths


class OpenClawAdapterTests(unittest.TestCase):
    def test_discover_finds_sessions_across_agents_with_stable_ids(self):
        with tempfile.TemporaryDirectory() as tempdir:
            agents_dir = Path(tempdir) / "agents"
            self._write_session(
                agents_dir,
                "main",
                "shared",
                [
                    {"type": "custom", "timestamp": "2026-05-01T09:59:00Z", "data": {"ignored": True}},
                    self._message("user", "main", "2026-05-01T10:00:00Z"),
                ],
            )
            self._write_session(
                agents_dir,
                "antigravity",
                "shared",
                [self._message("user", "other", "2026-05-01T11:00:00Z")],
            )

            discovered = OpenClawAdapter(agents_dir).discover()

        self.assertEqual(len({item["source_session_id"] for item in discovered}), 2)
        self.assertTrue(all("#" not in str(item["source_session_id"]) for item in discovered))
        self.assertEqual({item["project"] for item in discovered}, {"main", "antigravity"})
        self.assertTrue(all(item["path"].endswith("shared.json") for item in discovered))
        main_session = next(item for item in discovered if item["project"] == "main")
        self.assertEqual(main_session["started_at"], "2026-05-01T09:59:00Z")

    def test_discover_filters_by_project(self):
        with tempfile.TemporaryDirectory() as tempdir:
            agents_dir = Path(tempdir) / "agents"
            self._write_session(agents_dir, "main", "first", [self._message("user", "main")])
            self._write_session(agents_dir, "secondary", "second", [self._message("user", "secondary")])

            discovered = OpenClawAdapter(agents_dir).discover(project="main")

        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]["project"], "main")

    def test_discover_and_ingest_jsonl_session(self):
        with tempfile.TemporaryDirectory() as tempdir:
            agents_dir = Path(tempdir) / "agents"
            self._write_session(
                agents_dir,
                "main",
                "json-lines",
                [self._message("user", "from jsonl")],
                extension=".jsonl",
            )
            adapter = OpenClawAdapter(agents_dir)

            discovered = adapter.discover()
            session = adapter.ingest(str(discovered[0]["source_session_id"]))

        self.assertEqual(len(discovered), 1)
        self.assertIsNotNone(session)
        self.assertEqual(session.messages, [{"role": "user", "content": "from jsonl"}])

    def test_discover_disambiguates_same_stem_with_different_extensions(self):
        with tempfile.TemporaryDirectory() as tempdir:
            agents_dir = Path(tempdir) / "agents"
            self._write_session(agents_dir, "main", "duplicate", [self._message("user", "json")])
            self._write_session(
                agents_dir,
                "main",
                "duplicate",
                [self._message("user", "jsonl")],
                extension=".jsonl",
            )
            adapter = OpenClawAdapter(agents_dir)

            discovered = adapter.discover()
            ingested = [adapter.ingest(item["source_session_id"]) for item in discovered]

        self.assertEqual(len({item["source_session_id"] for item in discovered}), 2)
        self.assertTrue(all("#" not in str(item["source_session_id"]) for item in discovered))
        self.assertEqual(
            {session.messages[0]["content"] for session in ingested if session},
            {"json", "jsonl"},
        )

    def test_public_ids_round_trip_special_stems_and_extension_collisions(self):
        with tempfile.TemporaryDirectory() as tempdir:
            agents_dir = Path(tempdir) / "agents"
            self._write_session(agents_dir, "main", "foo#json", [self._message("user", "hash-json")])
            self._write_session(
                agents_dir,
                "main",
                "foo#jsonl",
                [self._message("user", "hash-jsonl")],
                extension=".jsonl",
            )
            self._write_session(agents_dir, "main", "same", [self._message("user", "same-json")])
            self._write_session(
                agents_dir,
                "main",
                "same",
                [self._message("user", "same-jsonl")],
                extension=".jsonl",
            )
            adapter = OpenClawAdapter(agents_dir)

            discovered = adapter.discover()
            ingested = [adapter.ingest(str(item["source_session_id"])) for item in discovered]

        self.assertEqual(len(discovered), 4)
        self.assertEqual(len({item["source_session_id"] for item in discovered}), 4)
        self.assertTrue(all("#" not in str(item["source_session_id"]) for item in discovered))
        self.assertTrue(all(session is not None for session in ingested))
        self.assertEqual(
            {session.messages[0]["content"] for session in ingested if session},
            {"hash-json", "hash-jsonl", "same-json", "same-jsonl"},
        )

    def test_ingest_extracts_user_assistant_messages_and_skips_tools(self):
        with tempfile.TemporaryDirectory() as tempdir:
            agents_dir = Path(tempdir) / "agents"
            self._write_session(
                agents_dir,
                "main",
                "chat",
                [
                    self._message("user", "question", "2026-05-01T10:00:00Z"),
                    self._message("toolResult", [{"type": "text", "text": "secret tool output"}], "2026-05-01T10:01:00Z"),
                    self._message(
                        "assistant",
                        [{"type": "text", "text": "answer"}],
                        "2026-05-01T10:02:00Z",
                        model="gemini-3.1-pro-preview",
                        api="google-generative-ai",
                    ),
                    self._message("toolCall", [{"type": "text", "text": "do not keep"}], "2026-05-01T10:03:00Z"),
                ],
            )

            adapter = OpenClawAdapter(agents_dir)
            session_id = str(adapter.discover()[0]["source_session_id"])
            session = adapter.ingest(session_id)

        self.assertIsNotNone(session)
        self.assertEqual(
            session.messages,
            [{"role": "user", "content": "question"}, {"role": "assistant", "content": "answer"}],
        )
        self.assertEqual(session.source_session_id, session_id)
        self.assertEqual(session.started_at, "2026-05-01T10:00:00Z")
        self.assertEqual(session.ended_at, "2026-05-01T10:02:00Z")
        self.assertEqual(session.metadata["model"], "gemini-3.1-pro-preview")
        self.assertEqual(session.metadata["api"], "google-generative-ai")

    def test_ingest_extracts_only_text_blocks_from_list_content(self):
        with tempfile.TemporaryDirectory() as tempdir:
            agents_dir = Path(tempdir) / "agents"
            self._write_session(
                agents_dir,
                "main",
                "blocks",
                [
                    self._message(
                        "user",
                        [
                            {"type": "input_text", "text": "first prompt"},
                            {"type": "image", "url": "https://example.invalid/image"},
                            {"type": "input_text", "text": "second prompt"},
                        ],
                    ),
                    self._message(
                        "assistant",
                        [
                            {"type": "text", "text": "first response"},
                            {"type": "tool_use", "name": "read_file", "input": {}},
                            {"type": "text", "text": "second response"},
                        ],
                    ),
                ],
            )

            adapter = OpenClawAdapter(agents_dir)
            session = adapter.ingest(str(adapter.discover()[0]["source_session_id"]))

        self.assertIsNotNone(session)
        self.assertEqual(session.messages[0]["content"], "first prompt\nsecond prompt")
        self.assertEqual(session.messages[1]["content"], "first response\nsecond response")

    def test_ingest_skips_unknown_event_types(self):
        with tempfile.TemporaryDirectory() as tempdir:
            agents_dir = Path(tempdir) / "agents"
            self._write_session(
                agents_dir,
                "main",
                "known-events",
                [
                    {"type": "custom", "customType": "openclaw:bootstrap-context:full", "data": {"ignored": True}},
                    self._message("user", "keep me"),
                ],
            )

            adapter = OpenClawAdapter(agents_dir)
            session = adapter.ingest(str(adapter.discover()[0]["source_session_id"]))

        self.assertIsNotNone(session)
        self.assertEqual(session.messages, [{"role": "user", "content": "keep me"}])

    def test_ingest_keeps_bad_line_errors_local_and_observable(self):
        with tempfile.TemporaryDirectory() as tempdir:
            agents_dir = Path(tempdir) / "agents"
            session_path = self._session_path(agents_dir, "main", "partially-valid")
            session_path.write_text(
                "{not json}\n" + json.dumps(self._message("user", "valid after malformed line")) + "\n",
                encoding="utf-8",
            )
            adapter = OpenClawAdapter(agents_dir)

            session = adapter.ingest(str(adapter.discover()[0]["source_session_id"]))
            health = adapter.health_check()

        self.assertIsNotNone(session)
        self.assertTrue(session.metadata["errors"])
        self.assertTrue(health["errors"])
        self.assertEqual(session.messages, [{"role": "user", "content": "valid after malformed line"}])

    def test_discover_and_ingest_reject_agent_directory_symlink(self):
        with tempfile.TemporaryDirectory() as tempdir:
            agents_dir = Path(tempdir) / "agents"
            outside_agent = Path(tempdir) / "outside-agent"
            self._write_session(outside_agent.parent, outside_agent.name, "escaped", [self._message("user", "outside")])
            agents_dir.mkdir()
            (agents_dir / "main").symlink_to(outside_agent, target_is_directory=True)
            adapter = OpenClawAdapter(agents_dir)
            escaped_id = adapter._public_session_id(agents_dir / "main" / "sessions" / "escaped.json", "main")

            discovered = adapter.discover()
            session = adapter.ingest(escaped_id)

        self.assertEqual(discovered, [])
        self.assertIsNone(session)
        self.assertTrue(adapter.health_check()["errors"])

    def test_discover_and_ingest_reject_sessions_directory_symlink(self):
        with tempfile.TemporaryDirectory() as tempdir:
            agents_dir = Path(tempdir) / "agents"
            outside_sessions = Path(tempdir) / "outside-sessions"
            outside_sessions.mkdir()
            (outside_sessions / "escaped.json").write_text(
                json.dumps(self._message("user", "outside")) + "\n",
                encoding="utf-8",
            )
            agent_dir = agents_dir / "main"
            agent_dir.mkdir(parents=True)
            (agent_dir / "sessions").symlink_to(outside_sessions, target_is_directory=True)
            adapter = OpenClawAdapter(agents_dir)
            escaped_id = adapter._public_session_id(agent_dir / "sessions" / "escaped.json", "main")

            discovered = adapter.discover()
            session = adapter.ingest(escaped_id)

        self.assertEqual(discovered, [])
        self.assertIsNone(session)
        self.assertTrue(adapter.health_check()["errors"])

    def test_discover_and_ingest_reject_session_file_symlink(self):
        with tempfile.TemporaryDirectory() as tempdir:
            agents_dir = Path(tempdir) / "agents"
            outside_session = Path(tempdir) / "outside.json"
            outside_session.write_text(json.dumps(self._message("user", "outside")) + "\n", encoding="utf-8")
            symlink_path = self._session_path(agents_dir, "main", "escaped")
            symlink_path.symlink_to(outside_session)
            adapter = OpenClawAdapter(agents_dir)
            escaped_id = adapter._public_session_id(symlink_path, "main")

            discovered = adapter.discover()
            session = adapter.ingest(escaped_id)

        self.assertEqual(discovered, [])
        self.assertIsNone(session)
        self.assertTrue(adapter.health_check()["errors"])

    def test_bad_encoding_is_observable_while_valid_sibling_is_harvested(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as tempdir:
            root = Path(tempdir)
            home = root / "home"
            home.mkdir()
            agents_dir = home / ".openclaw" / "agents"
            bad_path = self._session_path(agents_dir, "main", "bad-encoding")
            bad_path.write_bytes(b"\xff\xfe\x00")
            adapter = OpenClawAdapter(agents_dir)
            env = {
                "HOME": str(home),
                "ZCORE_HOME": str(home / ".zcore"),
                "AI_MEMORY_DIR": str(home / ".ai-memory"),
                "AI_SKILLS_DIR": str(home / ".ai-skills"),
            }
            with patch.dict("os.environ", env, clear=False):
                engine = HarvesterEngine(RuntimePaths.discover())
                engine.adapters.clear()
                engine.register_adapter(adapter)

                invalid_only = engine.ingest(source="openclaw", dry_run=True)
                self._write_session(agents_dir, "main", "valid", [self._message("user", "keep")])
                payload = engine.ingest(source="openclaw", dry_run=True)

        self.assertGreater(invalid_only["totals"]["errors"], 0)
        self.assertEqual(payload["totals"]["ingested"], 1)
        self.assertGreater(payload["totals"]["errors"], 0)
        serialized_errors = json.dumps(payload["results"][0]["errors"])
        self.assertNotIn(str(bad_path), serialized_errors)
        self.assertIn("/home/[USER]/", serialized_errors)

    def test_harvest_cli_reports_redacted_bad_encoding_error_and_valid_sibling(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as tempdir:
            home = Path(tempdir) / "home"
            home.mkdir()
            agents_dir = home / ".openclaw" / "agents"
            self._session_path(agents_dir, "main", "bad-encoding").write_bytes(b"\xff\xfe\x00")
            self._write_session(agents_dir, "main", "valid", [self._message("user", "keep")])

            proc = run_zcore("harvest", "ingest", "--source", "openclaw", "--json", home=home)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["totals"]["ingested"], 1)
        self.assertGreater(payload["totals"]["errors"], 0)
        self.assertNotIn(str(home), proc.stdout)
        self.assertIn("/home/[USER]/", proc.stdout)

    def test_harvester_reports_partially_valid_session_error_once_per_payload(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as tempdir:
            root = Path(tempdir)
            home = root / "home"
            home.mkdir()
            agents_dir = home / ".openclaw" / "agents"
            session_path = self._session_path(agents_dir, "main", "partially-valid")
            session_path.write_text(
                "{not json}\n" + json.dumps(self._message("user", "keep")) + "\n",
                encoding="utf-8",
            )
            env = {
                "HOME": str(home),
                "ZCORE_HOME": str(home / ".zcore"),
                "AI_MEMORY_DIR": str(home / ".ai-memory"),
                "AI_SKILLS_DIR": str(home / ".ai-skills"),
            }
            with patch.dict("os.environ", env, clear=False):
                engine = HarvesterEngine(RuntimePaths.discover())
                payload = engine.ingest(source="openclaw", dry_run=True)

        self.assertEqual(payload["totals"], {"discovered": 1, "ingested": 1, "skipped": 0, "errors": 1})
        self.assertEqual(len(payload["results"][0]["errors"]), 1)
        self.assertNotIn(str(session_path), json.dumps(payload["results"][0]["errors"]))
        self.assertIn("/home/[USER]/", json.dumps(payload["results"][0]["errors"]))

    def test_harvest_cli_reports_partially_valid_session_error_once_per_payload(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as tempdir:
            home = Path(tempdir) / "home"
            home.mkdir()
            agents_dir = home / ".openclaw" / "agents"
            session_path = self._session_path(agents_dir, "main", "partially-valid")
            session_path.write_text(
                "{not json}\n" + json.dumps(self._message("user", "keep")) + "\n",
                encoding="utf-8",
            )

            proc = run_zcore("harvest", "ingest", "--source", "openclaw", "--json", home=home)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["totals"], {"discovered": 1, "ingested": 1, "skipped": 0, "errors": 1})
        self.assertEqual(len(payload["results"][0]["errors"]), 1)
        self.assertNotIn(str(session_path), proc.stdout)
        self.assertIn("/home/[USER]/", proc.stdout)

    def test_harvester_redacts_missing_session_id_in_stderr_and_payload(self):
        class MissingIdAdapter:
            def name(self) -> str:
                return "missing-id"

            def discover(self, project: str | None = None) -> list[dict[str, object]]:
                return [{"path": "/home/alice/private/session.json"}]

            def ingest(self, session_id: str):
                return None

            def health_check(self) -> dict[str, object]:
                return {"ok": True}

        with self._isolated_home():
            engine = HarvesterEngine(RuntimePaths.discover())
            engine.adapters.clear()
            engine.register_adapter(MissingIdAdapter())
            stderr = StringIO()
            with redirect_stderr(stderr):
                payload = engine.ingest(source="missing-id", dry_run=True)

        error = payload["results"][0]["errors"][0]
        self.assertIn("/home/[USER]/private/session.json", error)
        self.assertIn("/home/[USER]/private/session.json", stderr.getvalue())
        self.assertNotIn("/home/alice/", error)
        self.assertNotIn("/home/alice/", stderr.getvalue())

    def test_health_check_returns_ok_only_when_agents_directory_exists(self):
        with tempfile.TemporaryDirectory() as tempdir:
            agents_dir = Path(tempdir) / "agents"
            adapter = OpenClawAdapter(agents_dir)
            missing = adapter.health_check()
            agents_dir.mkdir()
            present = adapter.health_check()

        self.assertFalse(missing["ok"])
        self.assertIn("reason", missing)
        self.assertTrue(present["ok"])

    def test_harvester_skips_openclaw_session_matching_ingest_ignore(self):
        with self._isolated_home() as home:
            agents_dir = home / ".openclaw" / "agents"
            self._write_session(agents_dir, "main", "ignored", [self._message("user", "do not persist")])
            self._write_session(
                agents_dir,
                "main",
                "kept",
                [self._message("user", "path /home/alice/private-project stays redacted")],
            )
            zcore_home = home / ".zcore"
            zcore_home.mkdir()
            (zcore_home / "ingest-ignore").write_text("**/sessions/ignored.json\n", encoding="utf-8")

            engine = HarvesterEngine(RuntimePaths.discover())
            self.assertIn("openclaw", engine.adapters)
            kept_id = next(
                item["source_session_id"]
                for item in OpenClawAdapter(agents_dir).discover()
                if item["openclaw_session_id"] == "kept"
            )
            payload = engine.ingest(source="openclaw")
            saved = next((zcore_home / "harvested" / "openclaw").glob("*.json"))
            persisted = json.loads(saved.read_text(encoding="utf-8"))

        self.assertEqual(payload["totals"], {"discovered": 2, "ingested": 1, "skipped": 1, "errors": 0})
        self.assertEqual(persisted["source_session_id"], kept_id)
        self.assertIn("/home/[USER]/private-project", persisted["messages"][0]["content"])

    @staticmethod
    def _message(
        role: str,
        content: object,
        timestamp: str = "2026-05-01T10:00:00Z",
        *,
        model: str | None = None,
        api: str | None = None,
    ) -> dict[str, object]:
        message: dict[str, object] = {"role": role, "content": content}
        if model is not None:
            message["model"] = model
        if api is not None:
            message["api"] = api
        return {"type": "message", "timestamp": timestamp, "message": message}

    def _write_session(
        self,
        agents_dir: Path,
        agent: str,
        session_name: str,
        events: list[dict[str, object]],
        *,
        extension: str = ".json",
    ) -> Path:
        path = self._session_path(agents_dir, agent, session_name, extension=extension)
        path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _session_path(
        agents_dir: Path,
        agent: str,
        session_name: str,
        *,
        extension: str = ".json",
    ) -> Path:
        sessions_dir = agents_dir / agent / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return sessions_dir / f"{session_name}{extension}"

    def _isolated_home(self):
        tempdir = tempfile.TemporaryDirectory()
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
