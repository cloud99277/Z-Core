from __future__ import annotations

import gzip
import json
import os
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from zcore.adapters.base import SourceAdapter
from zcore.engines.harvester import HarvesterEngine
from tests.helpers import TestHome, run_zcore
from zcore.engines.search import SearchEngine
from zcore.engines.search_index import SearchIndex, SearchIndexBuildError
from zcore.models.harvester import HarvestedSession
from zcore.runtime import RuntimePaths


class _SingleSessionAdapter(SourceAdapter):
    def name(self) -> str:
        return "test-source"

    def discover(self, project: str | None = None) -> list[dict[str, object]]:
        return [{"source_session_id": "ingested"}]

    def ingest(self, session_id: str) -> HarvestedSession | None:
        return HarvestedSession(
            source=self.name(),
            source_session_id=session_id,
            project="Z-Core",
            started_at="2026-08-22T00:00:00Z",
            messages=[{"role": "user", "content": "ingested search body"}],
        )

    def health_check(self) -> dict[str, object]:
        return {"ok": True}


class SearchIndexTests(unittest.TestCase):
    def test_search_without_index_scans_without_creating_database(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="native",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="legacy fallback target",
            )

            result = SearchEngine(paths).search("fallback target")

            self.assertEqual(result.total_hits, 1)
            self.assertFalse((paths.base_dir / "search.db").exists())

    def test_rebuild_creates_contentless_private_index_and_fresh_search_uses_it(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="native",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="prefix HarvesterSuffix target",
            )

            rebuilt = SearchIndex(paths).rebuild()
            engine = SearchEngine(paths)
            with patch.object(engine, "_search_legacy", side_effect=AssertionError("legacy scan used")):
                result = engine.search("VESTersuffix")

            self.assertTrue(rebuilt["ok"])
            self.assertEqual(result.total_hits, 1)
            self.assertEqual(result.hits[0].session_id, "native")
            self.assertEqual(os.stat(paths.base_dir / "search.db").st_mode & 0o777, 0o600)
            self.assertEqual(list(paths.base_dir.glob(".search.db.*")), [])
            with sqlite3.connect(paths.base_dir / "search.db") as connection:
                stored = connection.execute(
                    "SELECT text FROM search_fts WHERE search_fts MATCH ?",
                    ('"harvester"',),
                ).fetchone()
                regular_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(search_records)").fetchall()
                }
            self.assertEqual(stored, (None,))
            self.assertNotIn("text", regular_columns)
            self.assertNotIn("summary", regular_columns)
            minimized = {key: value for key, value in rebuilt.items() if key != "index_path"}
            self.assertNotIn(str(paths.base_dir), json.dumps(minimized))

    def test_indexed_result_matches_legacy_result_except_elapsed_time(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="newer",
                project="Z-Core",
                started_at="2026-08-21T00:00:00Z",
                summary="short search target",
                messages=[
                    {
                        "role": "user",
                        "content": "A much richer search target message with surrounding context",
                    }
                ],
            )
            self._write_harvested(
                paths,
                source="claude",
                session_id="older",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="search target harvested",
                messages=[{"role": "user", "content": "search target duplicated text"}],
            )

            legacy = SearchEngine(paths).search("SEARCH target", limit=1).to_dict()
            SearchIndex(paths).rebuild()
            indexed = SearchEngine(paths).search("SEARCH target", limit=1).to_dict()

            legacy.pop("elapsed_ms")
            indexed.pop("elapsed_ms")
            self.assertEqual(indexed, legacy)

    def test_short_unicode_term_bypasses_fts(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="cjk",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="中文索引目标",
            )
            SearchIndex(paths).rebuild()
            engine = SearchEngine(paths)

            with patch.object(engine, "_search_index", side_effect=AssertionError("FTS used")):
                result = engine.search("索引")

            self.assertEqual(result.total_hits, 1)

    def test_indexed_search_preserves_casefold_substring_and_literal_query_syntax(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="literals",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary='ÜberStraße HarvesterSuffix AND foo-bar alpha"beta star*term',
            )
            SearchIndex(paths).rebuild()
            engine = SearchEngine(paths)

            with patch.object(engine, "_search_legacy", side_effect=AssertionError("legacy scan used")):
                for query in ("STRASSE", "vesters", "AND", "foo-bar", 'alpha"beta', "star*term"):
                    with self.subTest(query=query):
                        result = engine.search(query)
                        self.assertEqual(result.total_hits, 1)

    def test_indexed_filters_counts_order_snippet_limit_and_dedupe_match_legacy(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="newer",
                project="Z-Core",
                started_at="2026-08-22T00:00:00Z",
                summary="needle target",
                messages=[
                    {
                        "role": "user",
                        "content": "A much richer needle target message with surrounding context for the snippet",
                    }
                ],
            )
            self._write_native(
                paths,
                session_id="other-project",
                project="Other",
                started_at="2026-08-23T00:00:00Z",
                summary="needle target in another project",
            )
            self._write_harvested(
                paths,
                source="claude",
                session_id="older",
                project="Z-Core",
                started_at="2026-08-21T00:00:00Z",
                summary="needle target",
                messages=[
                    {"role": "user", "content": "needle target duplicate one"},
                    {"role": "assistant", "content": "needle target duplicate two with context"},
                ],
            )
            SearchIndex(paths).rebuild()

            result = SearchEngine(paths).search("needle target", project="Z-Core", limit=1)
            zero_limit = SearchEngine(paths).search("needle target", project="Z-Core", limit=-5)
            source_only = SearchEngine(paths).search(
                "needle target", source="harvested", project="Z-Core"
            )

            self.assertEqual(result.total_hits, 2)
            self.assertEqual(len(result.hits), 1)
            self.assertEqual(result.hits[0].session_id, "newer")
            self.assertIn("much richer", result.hits[0].snippet)
            self.assertEqual(result.hits[0].score, 1.0)
            self.assertEqual(result.searched_sessions, 1)
            self.assertEqual(result.searched_harvested, 1)
            self.assertEqual(zero_limit.total_hits, 2)
            self.assertEqual(zero_limit.hits, [])
            self.assertEqual(source_only.total_hits, 1)
            self.assertEqual(source_only.searched_sessions, 0)
            self.assertEqual(source_only.searched_harvested, 1)
            self.assertEqual(source_only.hits[0].session_id, "claude:older")

    def test_project_filter_is_sql_bound(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            project = 'Z-Core" OR 1=1 --'
            self._write_native(
                paths,
                session_id="literal-project",
                project=project,
                started_at="2026-08-20T00:00:00Z",
                summary="bound filter target",
            )
            self._write_native(
                paths,
                session_id="other-project",
                project="Other",
                started_at="2026-08-21T00:00:00Z",
                summary="bound filter target",
            )
            SearchIndex(paths).rebuild()

            result = SearchEngine(paths).search("filter target", project=project)

            self.assertEqual(result.total_hits, 1)
            self.assertEqual(result.searched_sessions, 1)
            self.assertEqual(result.hits[0].session_id, "literal-project")

    def test_empty_project_preserves_legacy_no_filter_semantics(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            for session_id, project in (("one", "Z-Core"), ("two", "Other")):
                self._write_native(
                    paths,
                    session_id=session_id,
                    project=project,
                    started_at=f"2026-08-2{1 if session_id == 'one' else 2}T00:00:00Z",
                    summary="empty project filter target",
                )
            legacy = SearchEngine(paths).search("filter target", project="").to_dict()
            SearchIndex(paths).rebuild()
            engine = SearchEngine(paths)

            with patch.object(engine, "_search_legacy", side_effect=AssertionError("legacy scan used")):
                indexed = engine.search("filter target", project="").to_dict()

            legacy.pop("elapsed_ms")
            indexed.pop("elapsed_ms")
            self.assertEqual(indexed, legacy)
            self.assertEqual(indexed["searched_sessions"], 2)

    def test_same_length_edit_with_restored_mtime_invalidates_index(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="edited",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="alpha target",
            )
            index = SearchIndex(paths)
            meta_path = paths.sessions_dir / "edited" / "meta.json"
            index.rebuild()
            original_stat = meta_path.stat()
            original = meta_path.read_text(encoding="utf-8")
            changed = original.replace("alpha", "omega")
            self.assertEqual(len(changed), len(original))
            meta_path.write_text(changed, encoding="utf-8")
            os.utime(meta_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            engine = SearchEngine(paths)

            with patch.object(engine, "_search_legacy", wraps=engine._search_legacy) as legacy:
                result = engine.search("omega target")

            self.assertEqual(result.total_hits, 1)
            legacy.assert_called_once()

    def test_tampered_candidate_project_forces_complete_legacy_fallback(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="canonical",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="canonical metadata target",
            )
            SearchIndex(paths).rebuild()
            index_path = paths.base_dir / "search.db"
            with sqlite3.connect(index_path) as connection:
                connection.execute("UPDATE search_records SET project = 'Tampered'")
            before = index_path.read_bytes()
            engine = SearchEngine(paths)

            with patch.object(engine, "_search_legacy", wraps=engine._search_legacy) as legacy:
                result = engine.search("metadata target")

            self.assertEqual(result.total_hits, 1)
            self.assertEqual(result.hits[0].project, "Z-Core")
            legacy.assert_called_once()
            self.assertEqual(index_path.read_bytes(), before)

    def test_tampered_candidate_ref_outside_runtime_forces_fallback(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="canonical",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="contained reference target",
            )
            outside = ctx.home / "outside"
            outside.mkdir()
            (outside / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "outside",
                        "project": "Outside",
                        "started_at": "2026-08-23T00:00:00Z",
                        "summary": "external secret target",
                    }
                ),
                encoding="utf-8",
            )
            SearchIndex(paths).rebuild()
            with sqlite3.connect(paths.base_dir / "search.db") as connection:
                connection.execute(
                    "UPDATE search_records SET source_ref = '../../outside/meta.json'"
                )
            engine = SearchEngine(paths)

            with patch.object(engine, "_search_legacy", wraps=engine._search_legacy) as legacy:
                result = engine.search("reference target")

            self.assertEqual(result.total_hits, 1)
            self.assertEqual(result.hits[0].session_id, "canonical")
            legacy.assert_called_once()

    def test_directory_symlink_source_fails_rebuild_and_is_not_scanned(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="safe",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="safe internal target",
            )
            index = SearchIndex(paths)
            index.rebuild()
            index_path = paths.base_dir / "search.db"
            before = index_path.read_bytes()
            outside = ctx.home / "outside-session"
            outside.mkdir()
            (outside / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "outside",
                        "project": "Outside",
                        "started_at": "2026-08-23T00:00:00Z",
                        "summary": "external symlink secret",
                    }
                ),
                encoding="utf-8",
            )
            (paths.sessions_dir / "linked").symlink_to(outside, target_is_directory=True)

            with self.assertRaises(SearchIndexBuildError):
                index.rebuild()
            engine = SearchEngine(paths)
            internal = engine.search("internal target")
            external = engine.search("symlink secret")

            self.assertEqual(index_path.read_bytes(), before)
            self.assertEqual(internal.total_hits, 1)
            self.assertEqual(external.total_hits, 0)
            self.assertEqual(list(paths.base_dir.glob(".search.db.*")), [])

    def test_file_and_context_symlinks_fail_rebuild_without_replacement(self):
        for kind in ("meta", "context"):
            with self.subTest(kind=kind), TestHome() as ctx:
                paths = self._paths(ctx)
                self._write_native(
                    paths,
                    session_id="safe",
                    project="Z-Core",
                    started_at="2026-08-20T00:00:00Z",
                    summary="safe source target",
                )
                index = SearchIndex(paths)
                index.rebuild()
                index_path = paths.base_dir / "search.db"
                before = index_path.read_bytes()
                unsafe_dir = paths.sessions_dir / "unsafe"
                unsafe_dir.mkdir()
                if kind == "meta":
                    outside_meta = ctx.home / "outside-meta.json"
                    outside_meta.write_text(
                        json.dumps(
                            {
                                "session_id": "unsafe",
                                "project": "Outside",
                                "started_at": "2026-08-23T00:00:00Z",
                                "summary": "external file secret",
                            }
                        ),
                        encoding="utf-8",
                    )
                    (unsafe_dir / "meta.json").symlink_to(outside_meta)
                else:
                    (unsafe_dir / "meta.json").write_text(
                        json.dumps(
                            {
                                "session_id": "unsafe",
                                "project": "Z-Core",
                                "started_at": "2026-08-23T00:00:00Z",
                                "summary": "internal summary",
                            }
                        ),
                        encoding="utf-8",
                    )
                    outside_context = ctx.home / "outside-context.json.gz"
                    with gzip.open(outside_context, "wt", encoding="utf-8") as handle:
                        json.dump([{"role": "user", "content": "external context secret"}], handle)
                    (unsafe_dir / "context.json.gz").symlink_to(outside_context)

                with self.assertRaises(SearchIndexBuildError):
                    index.rebuild()

                self.assertEqual(index_path.read_bytes(), before)
                self.assertEqual(list(paths.base_dir.glob(".search.db.*")), [])

    def test_final_file_symlink_swap_during_rebuild_cannot_read_outside_runtime(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="raced",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="safe race target",
            )
            index = SearchIndex(paths)
            index.rebuild()
            index_path = paths.base_dir / "search.db"
            before = index_path.read_bytes()
            meta_path = paths.sessions_dir / "raced" / "meta.json"
            outside_meta = ctx.home / "outside-race.json"
            outside_meta.write_text(
                json.dumps(
                    {
                        "session_id": "outside",
                        "project": "Outside",
                        "started_at": "2026-08-23T00:00:00Z",
                        "summary": "outside race marker",
                    }
                ),
                encoding="utf-8",
            )
            original_read = index.read_source_bytes
            swapped = False

            def swap_before_read(path: Path) -> bytes:
                nonlocal swapped
                if path == meta_path and not swapped:
                    swapped = True
                    path.unlink()
                    path.symlink_to(outside_meta)
                return original_read(path)

            with patch.object(index, "read_source_bytes", side_effect=swap_before_read):
                with self.assertRaises(SearchIndexBuildError):
                    index.rebuild()

            self.assertTrue(swapped)
            self.assertEqual(index_path.read_bytes(), before)
            self.assertNotIn(b"outside race marker", before)
            self.assertEqual(SearchEngine(paths).search("race marker").total_hits, 0)
            self.assertEqual(list(paths.base_dir.glob(".search.db.*")), [])

    def test_base_directory_symlink_is_allowed_when_sources_below_it_are_safe(self):
        with TestHome() as ctx:
            real_base = ctx.home / "runtime-real"
            real_base.mkdir()
            linked_base = ctx.home / ".zcore"
            linked_base.symlink_to(real_base, target_is_directory=True)
            paths = self._paths(ctx, base_dir=linked_base)
            self._write_native(
                paths,
                session_id="safe",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="base symlink target",
            )

            SearchIndex(paths).rebuild()
            engine = SearchEngine(paths)
            with patch.object(engine, "_search_legacy", side_effect=AssertionError("legacy scan used")):
                result = engine.search("symlink target")

            self.assertEqual(result.total_hits, 1)

    def test_stale_modified_source_falls_back_to_legacy_scan(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="changed",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="original phrase",
            )
            SearchIndex(paths).rebuild()
            self._write_native(
                paths,
                session_id="changed",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="replacement phrase with changed size",
            )
            engine = SearchEngine(paths)

            with patch.object(engine, "_search_legacy", wraps=engine._search_legacy) as legacy:
                result = engine.search("replacement phrase")

            self.assertEqual(result.total_hits, 1)
            legacy.assert_called_once()

    def test_corrupt_wrong_version_and_incomplete_indexes_fall_back_unchanged(self):
        cases = ("corrupt", "wrong-version", "unsupported", "incomplete")
        for case in cases:
            with self.subTest(case=case), TestHome() as ctx:
                paths = self._paths(ctx)
                self._write_native(
                    paths,
                    session_id="fallback",
                    project="Z-Core",
                    started_at="2026-08-20T00:00:00Z",
                    summary="fallback survives broken index",
                )
                SearchIndex(paths).rebuild()
                index_path = paths.base_dir / "search.db"
                if case == "corrupt":
                    index_path.write_bytes(b"not a sqlite database")
                else:
                    with sqlite3.connect(index_path) as connection:
                        if case == "wrong-version":
                            connection.execute(
                                "UPDATE search_metadata SET value = ? WHERE key = 'schema_version'",
                                ("999",),
                            )
                        elif case == "unsupported":
                            connection.execute(
                                "UPDATE search_metadata SET value = ? WHERE key = 'index_format'",
                                ("unknown-index",),
                            )
                        else:
                            connection.execute(
                                "DELETE FROM search_metadata WHERE key = 'ready'"
                            )
                before = index_path.read_bytes()

                result = SearchEngine(paths).search("broken index")

                self.assertEqual(result.total_hits, 1)
                self.assertEqual(index_path.read_bytes(), before)

    def test_failed_rebuild_preserves_previous_database(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="stable",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="stable index",
            )
            index = SearchIndex(paths)
            index.rebuild()
            index_path = paths.base_dir / "search.db"
            before = index_path.read_bytes()

            with patch.object(index, "_fingerprint", side_effect=["before", "after"]):
                with self.assertRaises(SearchIndexBuildError):
                    index.rebuild()

            self.assertEqual(index_path.read_bytes(), before)
            self.assertEqual(list(paths.base_dir.glob(".search.db.*")), [])

    def test_stale_added_and_deleted_sources_fall_back(self):
        for change in ("add", "delete"):
            with self.subTest(change=change), TestHome() as ctx:
                paths = self._paths(ctx)
                if change == "delete":
                    self._write_native(
                        paths,
                        session_id="changing",
                        project="Z-Core",
                        started_at="2026-08-20T00:00:00Z",
                        summary="deleted source target",
                    )
                SearchIndex(paths).rebuild()
                if change == "add":
                    self._write_native(
                        paths,
                        session_id="changing",
                        project="Z-Core",
                        started_at="2026-08-20T00:00:00Z",
                        summary="added source target",
                    )
                    query = "added source"
                    expected_hits = 1
                else:
                    (paths.sessions_dir / "changing" / "meta.json").unlink()
                    query = "deleted source"
                    expected_hits = 0
                engine = SearchEngine(paths)

                with patch.object(engine, "_search_legacy", wraps=engine._search_legacy) as legacy:
                    result = engine.search(query)

                self.assertEqual(result.total_hits, expected_hits)
                legacy.assert_called_once()

    def test_repeated_rebuild_is_idempotent_and_removes_stale_rows(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="removed",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="stale row target",
            )
            index = SearchIndex(paths)

            first = index.rebuild()
            second = index.rebuild()
            (paths.sessions_dir / "removed" / "meta.json").unlink()
            third = index.rebuild()
            engine = SearchEngine(paths)
            with patch.object(engine, "_search_legacy", side_effect=AssertionError("legacy scan used")):
                result = engine.search("stale row")

            self.assertEqual(first["records"], 1)
            self.assertEqual(second["records"], 1)
            self.assertEqual(first["fingerprint"], second["fingerprint"])
            self.assertEqual(third["records"], 0)
            self.assertEqual(result.total_hits, 0)
            with sqlite3.connect(paths.base_dir / "search.db") as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM search_records").fetchone(), (0,))

    def test_harvester_ingest_does_not_touch_search_index(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            SearchIndex(paths).rebuild()
            index_path = paths.base_dir / "search.db"
            before = index_path.read_bytes()
            engine = HarvesterEngine(paths)
            engine.adapters.clear()
            engine.register_adapter(_SingleSessionAdapter())

            with patch.object(SearchIndex, "rebuild", side_effect=AssertionError("automatic rebuild")):
                payload = engine.ingest(source="test-source")

            self.assertEqual(payload["totals"]["ingested"], 1)
            self.assertEqual(index_path.read_bytes(), before)

    def test_index_rebuild_cli_json_is_content_minimized(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                paths,
                session_id="cli",
                project="Z-Core",
                started_at="2026-08-20T00:00:00Z",
                summary="secret body text",
            )

            proc = run_zcore("index", "rebuild", "--json", home=ctx.home)

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["records"], 1)
            self.assertEqual(payload["native_records"], 1)
            self.assertNotIn("secret body text", proc.stdout)
            self.assertNotIn(str(paths.sessions_dir), proc.stdout)

    def _paths(self, ctx: TestHome, *, base_dir: Path | None = None) -> RuntimePaths:
        runtime_dir = base_dir or ctx.home / ".zcore"
        return RuntimePaths(
            base_dir=runtime_dir,
            config_path=runtime_dir / "config.toml",
            shared_rules_path=runtime_dir / "shared-rules.yaml",
            mcp_registry_path=runtime_dir / "mcp-servers.toml",
            sessions_dir=runtime_dir / "sessions",
            session_index_path=runtime_dir / "sessions" / "index.json",
            logs_dir=runtime_dir / "logs",
            hooks_dir=runtime_dir / "hooks",
            pre_hooks_dir=runtime_dir / "hooks" / "pre-execute.d",
            post_hooks_dir=runtime_dir / "hooks" / "post-execute.d",
            cache_dir=runtime_dir / "cache",
            pending_dir=runtime_dir / "pending",
            memory_dir=ctx.home / ".ai-memory",
            topics_dir=ctx.home / ".ai-memory" / "topics",
            staging_dir=ctx.home / ".ai-memory" / "staging",
            whiteboard_path=ctx.home / ".ai-memory" / "whiteboard.json",
            extraction_log_path=ctx.home / ".ai-memory" / "extraction-log.jsonl",
            skills_dir=ctx.home / ".ai-skills",
            knowledge_db_path=ctx.home / ".lancedb" / "knowledge",
            lock_dir=runtime_dir / "locks",
        )

    def _write_native(
        self,
        paths: RuntimePaths,
        *,
        session_id: str,
        project: str,
        started_at: str,
        summary: str,
        messages: list[dict[str, str]] | None = None,
    ) -> None:
        session_dir = paths.sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "session_id": session_id,
            "project": project,
            "started_at": started_at,
            "summary": summary,
        }
        (session_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
        if messages is not None:
            with gzip.open(session_dir / "context.json.gz", "wt", encoding="utf-8") as handle:
                json.dump(messages, handle, ensure_ascii=False)

    def _write_harvested(
        self,
        paths: RuntimePaths,
        *,
        source: str,
        session_id: str,
        project: str,
        started_at: str,
        summary: str,
        messages: list[dict[str, str]],
    ) -> None:
        source_dir = paths.base_dir / "harvested" / source
        source_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": source,
            "source_session_id": session_id,
            "project": project,
            "started_at": started_at,
            "summary": summary,
            "messages": messages,
        }
        (source_dir / f"{session_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
