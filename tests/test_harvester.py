from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.helpers import run_zcore
from zcore.adapters.base import SourceAdapter
from zcore.engines.harvester import HarvesterEngine
from zcore.models.harvester import HarvestedSession, HarvestResult
from zcore.runtime import RuntimePaths


class EmptyAdapter(SourceAdapter):
    def name(self) -> str:
        return "empty"

    def discover(self, project: str | None = None) -> list[dict[str, object]]:
        return []

    def ingest(self, session_id: str) -> HarvestedSession | None:
        return None

    def health_check(self) -> dict[str, object]:
        return {"ok": True}


class HarvesterTests(unittest.TestCase):
    def test_harvested_dataclasses_create_payloads(self):
        session = HarvestedSession(
            source="claude",
            source_session_id="s1",
            project="project",
            started_at="2026-04-27T00:00:00Z",
            messages=[{"role": "user", "content": "hello"}],
        )
        result = HarvestResult(source="claude", discovered=1, ingested=0, skipped=1)

        self.assertEqual(session.to_dict()["source_session_id"], "s1")
        self.assertEqual(result.to_dict()["skipped"], 1)

    def test_harvester_engine_initializes_without_crash(self):
        with self._isolated_home() as home:
            paths = RuntimePaths.discover()
            engine = HarvesterEngine(paths)

            self.assertEqual(engine.discover(source="missing"), [])
            self.assertTrue(home.exists())

    def test_discover_and_ingest_empty_adapter_return_empty_results(self):
        with self._isolated_home():
            engine = HarvesterEngine(RuntimePaths.discover())
            engine.register_adapter(EmptyAdapter())

            self.assertEqual(engine.discover(source="empty"), [])
            payload = engine.ingest(source="empty")

        self.assertEqual(payload["totals"]["discovered"], 0)
        self.assertEqual(payload["results"][0]["source"], "empty")

    def test_status_output_shape(self):
        with self._isolated_home():
            engine = HarvesterEngine(RuntimePaths.discover())
            engine.register_adapter(EmptyAdapter())
            payload = engine.status()

        self.assertIn("harvest_dir", payload)
        self.assertEqual(payload["harvested_count"], 0)
        self.assertTrue(payload["adapters"]["empty"]["ok"])

    def test_harvest_status_cli_json_is_valid(self):
        with tempfile.TemporaryDirectory() as tempdir:
            home = Path(tempdir) / "home"
            home.mkdir()
            proc = run_zcore("harvest", "status", "--json", home=home)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("adapters", payload)
        self.assertIn("harvested_count", payload)

    def test_harvest_discover_cli_json_is_empty_without_data(self):
        with tempfile.TemporaryDirectory() as tempdir:
            home = Path(tempdir) / "home"
            home.mkdir()
            proc = run_zcore("harvest", "discover", "--json", home=home)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), [])

    def test_redacts_metadata_before_storage(self):
        with self._isolated_home():
            engine = HarvesterEngine(RuntimePaths.discover())
            session = HarvestedSession(
                source="test",
                source_session_id="s1",
                project="/home/alice/project",
                started_at="2026-04-27T00:00:00Z",
                metadata={"path": "/home/alice/.claude/session.jsonl"},
            )

            redacted = engine._redact_session(session)

        self.assertEqual(redacted.project, "/home/[USER]/project")
        self.assertEqual(redacted.metadata["path"], "/home/[USER]/.claude/session.jsonl")

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
                self_nonlocal.tempdir = tempdir
                self_nonlocal.patch = patch.dict("os.environ", env, clear=False)
                self_nonlocal.patch.__enter__()
                return home

            def __exit__(self_nonlocal, exc_type, exc, tb):
                self_nonlocal.patch.__exit__(exc_type, exc, tb)
                tempdir.cleanup()

        return Manager()
