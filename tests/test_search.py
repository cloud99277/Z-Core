from __future__ import annotations

import gzip
import json
import unittest

from tests.helpers import TestHome, run_zcore
from zcore.engines.search import SearchEngine
from zcore.runtime import RuntimePaths


class SearchTests(unittest.TestCase):
    def test_search_empty_data_returns_zero_hits(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            result = SearchEngine(paths).search("missing")

        self.assertEqual(result.total_hits, 0)
        self.assertEqual(result.hits, [])
        self.assertEqual(result.searched_sessions, 0)
        self.assertEqual(result.searched_harvested, 0)

    def test_search_harvested_session_hits_message_content(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_harvested(
                ctx,
                source="claude",
                session_id="abc123",
                project="Z-Core",
                started_at="2026-04-27T00:00:00Z",
                messages=[{"role": "user", "content": "implemented harvester adapter pipeline"}],
            )

            result = SearchEngine(paths).search("harvester adapter")

        self.assertEqual(result.total_hits, 1)
        self.assertEqual(result.hits[0].source, "harvested")
        self.assertEqual(result.hits[0].session_id, "claude:abc123")
        self.assertIn("harvester adapter", result.hits[0].snippet)

    def test_search_native_session_hits_meta_summary(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                ctx,
                session_id="s_001",
                project="Z-Core",
                started_at="2026-04-28T00:00:00Z",
                summary="Discussed session search design",
            )

            result = SearchEngine(paths).search("SEARCH design", source="session")

        self.assertEqual(result.total_hits, 1)
        self.assertEqual(result.hits[0].source, "session")
        self.assertEqual(result.hits[0].session_id, "s_001")

    def test_search_native_session_hits_context_messages(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_native(
                ctx,
                session_id="s_context",
                project="Z-Core",
                started_at="2026-04-28T00:00:00Z",
                summary="unrelated summary",
                messages=[{"role": "user", "content": "context gzip message target"}],
            )

            result = SearchEngine(paths).search("gzip target", source="session")

        self.assertEqual(result.total_hits, 1)
        self.assertEqual(result.hits[0].session_id, "s_context")

    def test_multi_keyword_search_uses_and_within_same_text(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            self._write_harvested(
                ctx,
                source="claude",
                session_id="hit",
                project="Z-Core",
                started_at="2026-04-28T00:00:00Z",
                messages=[{"role": "user", "content": "harvester adapter contract"}],
            )
            self._write_harvested(
                ctx,
                source="claude",
                session_id="miss",
                project="Z-Core",
                started_at="2026-04-27T00:00:00Z",
                messages=[
                    {"role": "user", "content": "harvester only"},
                    {"role": "assistant", "content": "adapter only"},
                ],
            )

            result = SearchEngine(paths).search("harvester adapter", source="harvested")

        self.assertEqual(result.total_hits, 1)
        self.assertEqual(result.hits[0].session_id, "claude:hit")

    def test_session_search_cli_json_outputs_valid_json(self):
        with TestHome() as ctx:
            self._write_native(
                ctx,
                session_id="s_cli",
                project="Z-Core",
                started_at="2026-04-28T00:00:00Z",
                summary="cli json search target",
            )

            proc = run_zcore("session", "search", "--query", "json target", "--json", home=ctx.home)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["query"], "json target")
        self.assertEqual(payload["total_hits"], 1)
        self.assertEqual(payload["hits"][0]["session_id"], "s_cli")

    def test_limit_restricts_returned_hits(self):
        with TestHome() as ctx:
            paths = self._paths(ctx)
            for index in range(3):
                self._write_native(
                    ctx,
                    session_id=f"s_{index}",
                    project="Z-Core",
                    started_at=f"2026-04-2{index}T00:00:00Z",
                    summary="shared search phrase",
                )

            result = SearchEngine(paths).search("shared", source="session", limit=2)

        self.assertEqual(result.total_hits, 3)
        self.assertEqual(len(result.hits), 2)

    def _paths(self, ctx: TestHome) -> RuntimePaths:
        return RuntimePaths(
            base_dir=ctx.home / ".zcore",
            config_path=ctx.home / ".zcore" / "config.toml",
            shared_rules_path=ctx.home / ".zcore" / "shared-rules.yaml",
            mcp_registry_path=ctx.home / ".zcore" / "mcp-servers.toml",
            sessions_dir=ctx.home / ".zcore" / "sessions",
            session_index_path=ctx.home / ".zcore" / "sessions" / "index.json",
            logs_dir=ctx.home / ".zcore" / "logs",
            hooks_dir=ctx.home / ".zcore" / "hooks",
            pre_hooks_dir=ctx.home / ".zcore" / "hooks" / "pre-execute.d",
            post_hooks_dir=ctx.home / ".zcore" / "hooks" / "post-execute.d",
            cache_dir=ctx.home / ".zcore" / "cache",
            pending_dir=ctx.home / ".zcore" / "pending",
            memory_dir=ctx.home / ".ai-memory",
            topics_dir=ctx.home / ".ai-memory" / "topics",
            staging_dir=ctx.home / ".ai-memory" / "staging",
            whiteboard_path=ctx.home / ".ai-memory" / "whiteboard.json",
            extraction_log_path=ctx.home / ".ai-memory" / "extraction-log.jsonl",
            skills_dir=ctx.home / ".ai-skills",
            knowledge_db_path=ctx.home / ".lancedb" / "knowledge",
            lock_dir=ctx.home / ".zcore" / "locks",
        )

    def _write_native(
        self,
        ctx: TestHome,
        *,
        session_id: str,
        project: str,
        started_at: str,
        summary: str,
        messages: list[dict[str, str]] | None = None,
    ) -> None:
        session_dir = ctx.home / ".zcore" / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "session_id": session_id,
            "project": project,
            "agent": "codex",
            "started_at": started_at,
            "ended_at": None,
            "paused_at": None,
            "resumed_at": None,
            "status": "completed",
            "parent_session": None,
            "tags": [],
            "summary": summary,
            "token_count_start": 0,
            "token_count_end": 0,
            "tool_calls": 0,
            "compactions": 0,
            "compaction_mode": "none",
            "memory_mode": "none",
        }
        (session_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        if messages is not None:
            with gzip.open(session_dir / "context.json.gz", "wt", encoding="utf-8") as handle:
                json.dump(messages, handle, ensure_ascii=False)

    def _write_harvested(
        self,
        ctx: TestHome,
        *,
        source: str,
        session_id: str,
        project: str,
        started_at: str,
        messages: list[dict[str, str]],
        summary: str = "",
    ) -> None:
        source_dir = ctx.home / ".zcore" / "harvested" / source
        source_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": source,
            "source_session_id": session_id,
            "project": project,
            "started_at": started_at,
            "ended_at": None,
            "messages": messages,
            "summary": summary,
            "metadata": {},
        }
        (source_dir / f"{session_id}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
