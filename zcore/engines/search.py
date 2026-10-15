from __future__ import annotations

import gzip
import json
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

from zcore.engines.search_index import SearchIndex, SearchIndexBuildError, SearchIndexCandidate
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
        if terms and all(len(term) >= 3 for term in terms):
            indexed = self._search_index(
                query,
                source=source,
                project=project,
                bounded_limit=bounded_limit,
                terms=terms,
                started=started,
            )
            if indexed is not None:
                return indexed
        return self._search_legacy(
            query,
            source=source,
            project=project,
            bounded_limit=bounded_limit,
            terms=terms,
            started=started,
        )

    def _search_legacy(
        self,
        query: str,
        *,
        source: str | None,
        project: str | None,
        bounded_limit: int,
        terms: list[str],
        started: float,
    ) -> SearchResult:
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

    def _search_index(
        self,
        query: str,
        *,
        source: str | None,
        project: str | None,
        bounded_limit: int,
        terms: list[str],
        started: float,
    ) -> SearchResult | None:
        index = SearchIndex(self.paths)
        lookup = index.find_candidates(terms, source=source, project=project)
        if lookup is None:
            return None

        hits: list[SearchHit] = []
        for candidate in lookup.candidates:
            loaded = self._load_index_candidate(candidate)
            if loaded is None:
                return None
            payload, texts = loaded
            canonical_source = candidate.source
            canonical_session_id = (
                str(payload.get("session_id", ""))
                if canonical_source == "session"
                else self._harvested_session_id(payload)
            )
            canonical_project = str(payload.get("project", ""))
            canonical_started_at = str(payload.get("started_at", ""))
            if (
                canonical_source != candidate.source
                or canonical_session_id != candidate.session_id
                or canonical_project != candidate.project
                or canonical_started_at != candidate.started_at
                or (source is not None and canonical_source != source)
                or (project and canonical_project != project)
            ):
                return None
            hit = self._match_record(
                source=canonical_source,
                session_id=canonical_session_id,
                project=canonical_project,
                started_at=canonical_started_at,
                texts=texts,
                terms=terms,
            )
            if hit is not None:
                hits.append(hit)

        hits.sort(key=lambda hit: hit.started_at, reverse=True)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return SearchResult(
            query=query,
            total_hits=len(hits),
            hits=hits[:bounded_limit],
            searched_sessions=lookup.searched_sessions,
            searched_harvested=lookup.searched_harvested,
            elapsed_ms=elapsed_ms,
        )

    def _load_index_candidate(
        self, candidate: SearchIndexCandidate
    ) -> tuple[dict[str, object], list[str]] | None:
        parts = Path(candidate.source_ref).parts
        if candidate.source == "session":
            valid_ref = len(parts) == 3 and parts[0] == "sessions" and parts[2] == "meta.json"
        else:
            valid_ref = (
                candidate.source == "harvested"
                and len(parts) == 3
                and parts[0] == "harvested"
                and parts[2].endswith(".json")
            )
        if not valid_ref or Path(candidate.source_ref).is_absolute() or ".." in parts:
            return None
        source_path = self.paths.base_dir.joinpath(*parts)
        safe_source_path = self._validated_source_path(source_path)
        if safe_source_path is None:
            return None
        payload = self._load_json(safe_source_path)
        if not isinstance(payload, dict):
            return None
        texts = [str(payload.get("summary", ""))]
        if candidate.source == "session":
            context_path = safe_source_path.parent / "context.json.gz"
            if (context_path.exists() or context_path.is_symlink()) and self._validated_source_path(
                context_path
            ) is None:
                return None
            try:
                texts.extend(self._native_context_texts(context_path, fail_closed=True))
            except SearchIndexBuildError:
                return None
        else:
            messages = payload.get("messages", [])
            if isinstance(messages, list):
                texts.extend(self._message_contents(messages))
        return payload, texts

    def _iter_native_sessions(self, *, project: str | None) -> Iterator[tuple[dict[str, object], list[str]]]:
        if not self.paths.sessions_dir.exists():
            return
        for meta_path in self.paths.sessions_dir.glob("*/meta.json"):
            safe_meta_path = self._validated_source_path(meta_path)
            if safe_meta_path is None:
                continue
            meta = self._load_json(safe_meta_path)
            if not isinstance(meta, dict):
                continue
            if project and meta.get("project") != project:
                continue
            texts = [str(meta.get("summary", ""))]
            texts.extend(self._native_context_texts(safe_meta_path.parent / "context.json.gz"))
            yield meta, texts

    def _iter_harvested_sessions(self, *, project: str | None) -> Iterator[tuple[dict[str, object], list[str]]]:
        harvest_dir = self.paths.base_dir / "harvested"
        if not harvest_dir.exists():
            return
        for session_path in harvest_dir.glob("*/*.json"):
            safe_session_path = self._validated_source_path(session_path)
            if safe_session_path is None:
                continue
            payload = self._load_json(safe_session_path)
            if not isinstance(payload, dict):
                continue
            if project and payload.get("project") != project:
                continue
            texts = [str(payload.get("summary", ""))]
            messages = payload.get("messages", [])
            if isinstance(messages, list):
                texts.extend(self._message_contents(messages))
            yield payload, texts

    def _native_context_texts(self, path: Path, *, fail_closed: bool = False) -> list[str]:
        if not path.exists() and not path.is_symlink():
            return []
        safe_path = self._validated_source_path(path)
        if safe_path is None:
            if fail_closed:
                raise SearchIndexBuildError("Search source could not be validated safely")
            return []
        try:
            raw = SearchIndex(self.paths).read_source_bytes(safe_path)
            payload = json.loads(gzip.decompress(raw).decode("utf-8"))
        except SearchIndexBuildError:
            if fail_closed:
                raise
            return []
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
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
            raw = SearchIndex(self.paths).read_source_bytes(path).decode("utf-8")
            return json.loads(raw)
        except (OSError, SearchIndexBuildError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _harvested_session_id(self, payload: dict[str, object]) -> str:
        session_id = str(payload.get("source_session_id") or payload.get("session_id") or "")
        source = str(payload.get("source") or "")
        return f"{source}:{session_id}" if source and session_id else session_id

    def _validated_source_path(self, path: Path) -> Path | None:
        try:
            return SearchIndex(self.paths).validate_source_path(path)
        except SearchIndexBuildError:
            return None
