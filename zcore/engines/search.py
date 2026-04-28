from __future__ import annotations

import gzip
import json
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

from zcore.models.search import SearchHit, SearchResult
from zcore.runtime import RuntimePaths


class SearchEngine:
    def __init__(self, paths: RuntimePaths | None = None):
        self.paths = paths or RuntimePaths.discover()

    def search(
        self,
        query: str,
        *,
        source: str | None = None,
        project: str | None = None,
        limit: int = 50,
    ) -> SearchResult:
        """Full-text search native and harvested session files."""
        started = time.perf_counter()
        terms = [term.casefold() for term in query.split() if term.strip()]
        bounded_limit = max(0, limit)
        hits: list[SearchHit] = []
        searched_sessions = 0
        searched_harvested = 0

        if source in (None, "session"):
            for meta, texts in self._iter_native_sessions(project=project):
                searched_sessions += 1
                hit = self._match_record(
                    source="session",
                    session_id=str(meta.get("session_id", "")),
                    project=str(meta.get("project", "")),
                    started_at=str(meta.get("started_at", "")),
                    texts=texts,
                    terms=terms,
                )
                if hit is not None:
                    hits.append(hit)

        if source in (None, "harvested"):
            for payload, texts in self._iter_harvested_sessions(project=project):
                searched_harvested += 1
                hit = self._match_record(
                    source="harvested",
                    session_id=self._harvested_session_id(payload),
                    project=str(payload.get("project", "")),
                    started_at=str(payload.get("started_at", "")),
                    texts=texts,
                    terms=terms,
                )
                if hit is not None:
                    hits.append(hit)

        hits.sort(key=lambda hit: hit.started_at, reverse=True)
        limited_hits = hits[:bounded_limit]
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return SearchResult(
            query=query,
            total_hits=len(hits),
            hits=limited_hits,
            searched_sessions=searched_sessions,
            searched_harvested=searched_harvested,
            elapsed_ms=elapsed_ms,
        )

    def _iter_native_sessions(self, *, project: str | None) -> Iterator[tuple[dict[str, object], list[str]]]:
        if not self.paths.sessions_dir.exists():
            return
        for meta_path in self.paths.sessions_dir.glob("*/meta.json"):
            meta = self._load_json(meta_path)
            if not isinstance(meta, dict):
                continue
            if project and meta.get("project") != project:
                continue
            texts = [str(meta.get("summary", ""))]
            texts.extend(self._native_context_texts(meta_path.parent / "context.json.gz"))
            yield meta, texts

    def _iter_harvested_sessions(self, *, project: str | None) -> Iterator[tuple[dict[str, object], list[str]]]:
        harvest_dir = self.paths.base_dir / "harvested"
        if not harvest_dir.exists():
            return
        for session_path in harvest_dir.glob("*/*.json"):
            payload = self._load_json(session_path)
            if not isinstance(payload, dict):
                continue
            if project and payload.get("project") != project:
                continue
            texts = [str(payload.get("summary", ""))]
            messages = payload.get("messages", [])
            if isinstance(messages, list):
                texts.extend(self._message_contents(messages))
            yield payload, texts

    def _native_context_texts(self, path: Path) -> list[str]:
        if not path.exists():
            return []
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(payload, dict):
            messages = payload.get("messages", [])
        else:
            messages = payload
        return list(self._message_contents(messages)) if isinstance(messages, list) else []

    def _message_contents(self, messages: Iterable[object]) -> Iterator[str]:
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if content is not None:
                yield str(content)

    def _match_record(
        self,
        *,
        source: str,
        session_id: str,
        project: str,
        started_at: str,
        texts: Iterable[str],
        terms: list[str],
    ) -> SearchHit | None:
        if not terms:
            return None
        best_snippet: str = ""
        matched = False
        for text in texts:
            folded = text.casefold()
            if all(term in folded for term in terms):
                matched = True
                candidate = self._snippet(text, folded, terms)
                # Prefer the snippet with more surrounding context (longer = richer)
                if len(candidate) > len(best_snippet):
                    best_snippet = candidate
        if not matched:
            return None
        return SearchHit(
            source=source,
            session_id=session_id,
            project=project,
            started_at=started_at,
            snippet=best_snippet,
        )

    def _snippet(self, text: str, folded: str, terms: list[str]) -> str:
        positions = [folded.find(term) for term in terms if folded.find(term) >= 0]
        first = min(positions) if positions else 0
        start = max(0, first - 50)
        end = min(len(text), first + max(len(term) for term in terms) + 50)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return f"{prefix}{text[start:end]}{suffix}"

    def _load_json(self, path: Path) -> object:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _harvested_session_id(self, payload: dict[str, object]) -> str:
        session_id = str(payload.get("source_session_id") or payload.get("session_id") or "")
        source = str(payload.get("source") or "")
        return f"{source}:{session_id}" if source and session_id else session_id
