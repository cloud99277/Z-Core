from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zcore.adapters.base import SourceAdapter
from zcore.engines.harvester import HarvesterEngine
from zcore.models.harvester import HarvestedSession
from zcore.runtime import RuntimePaths
from zcore.utils.privacy import load_ingest_ignore, should_ignore


class IgnoreAdapter(SourceAdapter):
    def __init__(self) -> None:
        self.ingested: list[str] = []

    def name(self) -> str:
        return "ignore-test"

    def discover(self, project: str | None = None) -> list[dict[str, object]]:
        return [
            {"source_session_id": "ignored", "path": "/tmp/project/secret/session.jsonl"},
            {"source_session_id": "kept", "path": "/tmp/project/public/session.jsonl"},
        ]

    def ingest(self, session_id: str) -> HarvestedSession | None:
        self.ingested.append(session_id)
        return HarvestedSession(
            source=self.name(),
            source_session_id=session_id,
            project="project",
            started_at="2026-04-28T00:00:00Z",
            messages=[{"role": "user", "content": "hello"}],
        )

    def health_check(self) -> dict[str, object]:
        return {"ok": True}


class IngestIgnoreTests(unittest.TestCase):
    def test_load_ingest_ignore_skips_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "ingest-ignore"
            path.write_text(
                "\n# comment\n**/secret/**\n  \n**/private-project/**\n",
                encoding="utf-8",
            )

            patterns = load_ingest_ignore(path)

        self.assertEqual(patterns, ["**/secret/**", "**/private-project/**"])

    def test_should_ignore_matches_glob_pattern(self):
        patterns = ["**/secret/**", "**/private-project/**"]

        self.assertTrue(should_ignore("/tmp/project/secret/session.jsonl", patterns))
        self.assertFalse(should_ignore("/tmp/project/public/session.jsonl", patterns))

    def test_harvester_ingest_skips_ignored_session_paths(self):
        with self._isolated_home() as home:
            zcore_home = home / ".zcore"
            zcore_home.mkdir()
            (zcore_home / "ingest-ignore").write_text("**/secret/**\n", encoding="utf-8")
            adapter = IgnoreAdapter()
            engine = HarvesterEngine(RuntimePaths.discover())
            engine.adapters.clear()
            engine.register_adapter(adapter)

            payload = engine.ingest(source="ignore-test", dry_run=True)

        self.assertEqual(adapter.ingested, ["kept"])
        self.assertEqual(payload["totals"]["discovered"], 2)
        self.assertEqual(payload["totals"]["ingested"], 1)
        self.assertEqual(payload["totals"]["skipped"], 1)

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
