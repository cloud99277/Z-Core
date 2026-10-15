from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
import stat as stat_module
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from zcore.runtime import RuntimePaths


SCHEMA_VERSION = "5"
INDEX_FORMAT = "fts5-trigram-contentless-v5"


class SearchIndexBuildError(RuntimeError):
    """Raised when an index rebuild cannot be completed atomically."""


@dataclass(frozen=True)
class SearchIndexCandidate:
    source: str
    source_ref: str
    session_id: str
    project: str
    started_at: str


@dataclass(frozen=True)
class SearchIndexLookup:
    candidates: list[SearchIndexCandidate]
    searched_sessions: int
    searched_harvested: int
    fingerprint: str


@dataclass(frozen=True)
class _IndexRecord:
    source: str
    source_ref: str
    session_id: str
    project: str
    started_at: str
    texts: list[str]


class SearchIndex:
    """Own the rebuildable, contentless SQLite search index."""

    def __init__(self, paths: RuntimePaths | None = None):
        self.paths = paths or RuntimePaths.discover()
        self.index_path = self.paths.base_dir / "search.db"

    def rebuild(self) -> dict[str, object]:
        """Build a complete index in a temporary database and atomically replace it."""
        try:
            self.paths.base_dir.mkdir(parents=True, exist_ok=True)
            before_fingerprint = self._fingerprint()
            descriptor, temp_name = tempfile.mkstemp(
                prefix=".search.db.", suffix=".tmp", dir=self.paths.base_dir
            )
            os.close(descriptor)
        except SearchIndexBuildError:
            raise
        except OSError as exc:
            raise SearchIndexBuildError(f"Search index rebuild setup failed: {exc}") from exc
        temp_path = Path(temp_name)
        connection: sqlite3.Connection | None = None
        native_records = 0
        harvested_records = 0
        text_rows = 0
        try:
            os.chmod(temp_path, 0o600)
            connection = sqlite3.connect(temp_path)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            self._create_schema(connection)

            for record in self._iter_records():
                cursor = connection.execute(
                    """
                    INSERT INTO search_records(
                        source, source_ref, session_id, project, started_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        record.source,
                        record.source_ref,
                        record.session_id,
                        record.project,
                        record.started_at,
                    ),
                )
                record_id = int(cursor.lastrowid)
                if record.source == "session":
                    native_records += 1
                else:
                    harvested_records += 1
                for text in record.texts:
                    cursor = connection.execute(
                        "INSERT INTO search_texts(record_id) VALUES (?)", (record_id,)
                    )
                    text_id = int(cursor.lastrowid)
                    connection.execute(
                        "INSERT INTO search_fts(rowid, text) VALUES (?, ?)",
                        (text_id, text.casefold()),
                    )
                    text_rows += 1

            connection.executemany(
                "INSERT INTO search_metadata(key, value) VALUES (?, ?)",
                (
                    ("schema_version", SCHEMA_VERSION),
                    ("index_format", INDEX_FORMAT),
                    ("source_fingerprint", before_fingerprint),
                ),
            )
            self._check_integrity(connection)
            after_fingerprint = self._fingerprint()
            if after_fingerprint != before_fingerprint:
                raise SearchIndexBuildError("Search sources changed during index rebuild")

            # A reader accepts the database only when this final transaction row exists.
            connection.execute(
                "INSERT INTO search_metadata(key, value) VALUES ('ready', '1')"
            )
            connection.commit()
            connection.close()
            connection = None
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, self.index_path)
        except SearchIndexBuildError:
            if connection is not None:
                connection.rollback()
            raise
        except (OSError, sqlite3.Error, ValueError) as exc:
            if connection is not None:
                connection.rollback()
            raise SearchIndexBuildError(f"Search index rebuild failed: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()
            self._remove_temp_files(temp_path)

        return {
            "ok": True,
            "index_path": str(self.index_path),
            "records": native_records + harvested_records,
            "native_records": native_records,
            "harvested_records": harvested_records,
            "text_rows": text_rows,
            "fingerprint": before_fingerprint,
        }

    def find_candidates(
        self,
        terms: list[str],
        *,
        source: str | None,
        project: str | None,
    ) -> SearchIndexLookup | None:
        """Return FTS candidates, or ``None`` when the index is unusable or stale."""
        if not self.index_path.is_file():
            return None
        try:
            with closing(self._connect_read_only()) as connection:
                metadata = self._read_metadata(connection)
                fingerprint = metadata.get("source_fingerprint", "")
                if not self._metadata_supported(metadata):
                    return None
                # Freshness is anchored immediately before MATCH. Mutations after
                # this snapshot are intentionally observed by the next search.
                if self._fingerprint() != fingerprint:
                    return None

                filter_sql, filter_parameters = self._filters(source=source, project=project)
                counts = connection.execute(
                    f"""
                    SELECT
                        COALESCE(SUM(source = 'session'), 0),
                        COALESCE(SUM(source = 'harvested'), 0)
                    FROM search_records
                    {filter_sql}
                    """,
                    filter_parameters,
                ).fetchone()
                expression = " AND ".join(self._quote_fts_term(term) for term in terms)
                rows = connection.execute(
                    f"""
                    SELECT DISTINCT
                        record.source,
                        record.source_ref,
                        record.session_id,
                        record.project,
                        record.started_at
                    FROM search_fts
                    JOIN search_texts AS text_ref ON text_ref.rowid = search_fts.rowid
                    JOIN search_records AS record ON record.id = text_ref.record_id
                    WHERE search_fts MATCH ?
                    {self._candidate_filters(source=source, project=project)}
                    """,
                    (expression, *filter_parameters),
                ).fetchall()
        except (OSError, SearchIndexBuildError, sqlite3.Error, ValueError):
            return None

        candidates = [SearchIndexCandidate(*map(str, row)) for row in rows]
        return SearchIndexLookup(
            candidates=candidates,
            searched_sessions=int(counts[0]) if counts else 0,
            searched_harvested=int(counts[1]) if counts else 0,
            fingerprint=fingerprint,
        )

    def validate_source_path(self, path: Path) -> Path:
        """Return a safe runtime source path or raise without following symlinks below base."""
        try:
            relative = path.relative_to(self.paths.base_dir)
        except ValueError as exc:
            raise SearchIndexBuildError("Search source is outside the runtime directory") from exc
        if not relative.parts or ".." in relative.parts:
            raise SearchIndexBuildError("Search source is outside the runtime directory")

        try:
            resolved_base = self.paths.base_dir.resolve(strict=True)
            current = self.paths.base_dir
            for part in relative.parts:
                current = current / part
                if current.is_symlink():
                    raise SearchIndexBuildError("Search source contains a symlink below runtime")
            resolved_path = path.resolve(strict=True)
        except SearchIndexBuildError:
            raise
        except OSError as exc:
            raise SearchIndexBuildError("Search source could not be resolved safely") from exc
        if not resolved_path.is_relative_to(resolved_base):
            raise SearchIndexBuildError("Search source resolves outside the runtime directory")
        return path

    def read_source_bytes(self, path: Path) -> bytes:
        """Read a runtime source through a no-follow descriptor chain."""
        try:
            relative = path.relative_to(self.paths.base_dir)
        except ValueError as exc:
            raise SearchIndexBuildError("Search source is outside the runtime directory") from exc
        if not relative.parts or ".." in relative.parts:
            raise SearchIndexBuildError("Search source is outside the runtime directory")
        if (
            not hasattr(os, "O_DIRECTORY")
            or not hasattr(os, "O_NOFOLLOW")
            or os.open not in os.supports_dir_fd
        ):
            raise SearchIndexBuildError("Descriptor-safe source reads are unsupported")

        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        file_flags = os.O_RDONLY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            directory_flags |= os.O_CLOEXEC
            file_flags |= os.O_CLOEXEC
        descriptors: list[int] = []
        try:
            resolved_base = self.paths.base_dir.resolve(strict=True)
            descriptors.append(os.open(resolved_base, directory_flags))
            for part in relative.parts[:-1]:
                descriptors.append(
                    os.open(part, directory_flags, dir_fd=descriptors[-1])
                )
            file_descriptor = os.open(
                relative.parts[-1], file_flags, dir_fd=descriptors[-1]
            )
            descriptors.append(file_descriptor)
            source_stat = os.fstat(file_descriptor)
            if not stat_module.S_ISREG(source_stat.st_mode):
                raise SearchIndexBuildError("Search source is not a regular file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(file_descriptor, 1024 * 1024)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        except SearchIndexBuildError:
            raise
        except OSError as exc:
            raise SearchIndexBuildError("Search source could not be read safely") from exc
        finally:
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        statements = (
            """
            CREATE TABLE search_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE search_records (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL CHECK(source IN ('session', 'harvested')),
                source_ref TEXT NOT NULL,
                session_id TEXT NOT NULL,
                project TEXT NOT NULL,
                started_at TEXT NOT NULL,
                UNIQUE(source, source_ref)
            )
            """,
            """
            CREATE TABLE search_texts (
                rowid INTEGER PRIMARY KEY,
                record_id INTEGER NOT NULL REFERENCES search_records(id)
            )
            """,
            """
            CREATE INDEX search_records_filter_idx
                ON search_records(source, project, started_at)
            """,
            "CREATE INDEX search_texts_record_idx ON search_texts(record_id)",
            """
            CREATE VIRTUAL TABLE search_fts USING fts5(
                text,
                content='',
                tokenize='trigram'
            )
            """,
        )
        for statement in statements:
            connection.execute(statement)

    def _check_integrity(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "INSERT INTO search_fts(search_fts) VALUES ('integrity-check')"
        )
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if result != ("ok",):
            raise SearchIndexBuildError("SQLite integrity check failed")

    def _metadata_supported(self, metadata: dict[str, str]) -> bool:
        return (
            metadata.get("schema_version") == SCHEMA_VERSION
            and metadata.get("index_format") == INDEX_FORMAT
            and metadata.get("ready") == "1"
            and bool(metadata.get("source_fingerprint"))
        )

    def _read_metadata(self, connection: sqlite3.Connection) -> dict[str, str]:
        rows = connection.execute("SELECT key, value FROM search_metadata").fetchall()
        return {str(key): str(value) for key, value in rows}

    def _connect_read_only(self) -> sqlite3.Connection:
        uri = f"{self.index_path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
        return connection

    def _filters(self, *, source: str | None, project: str | None) -> tuple[str, tuple[str, ...]]:
        clauses: list[str] = []
        parameters: list[str] = []
        if source is not None:
            clauses.append("source = ?")
            parameters.append(source)
        if project:
            clauses.append("project = ?")
            parameters.append(project)
        sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return sql, tuple(parameters)

    def _candidate_filters(self, *, source: str | None, project: str | None) -> str:
        clauses: list[str] = []
        if source is not None:
            clauses.append("record.source = ?")
        if project:
            clauses.append("record.project = ?")
        return "" if not clauses else f"AND {' AND '.join(clauses)}"

    def _quote_fts_term(self, term: str) -> str:
        escaped = term.replace('"', '""')
        return f'"{escaped}"'

    def _fingerprint(self) -> str:
        if (
            not hasattr(os, "O_DIRECTORY")
            or not hasattr(os, "O_NOFOLLOW")
            or os.open not in os.supports_dir_fd
        ):
            raise SearchIndexBuildError("Descriptor-safe source reads are unsupported")

        aggregate = hashlib.blake2b(digest_size=32)
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        file_flags = os.O_RDONLY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            directory_flags |= os.O_CLOEXEC
            file_flags |= os.O_CLOEXEC
        directory_fds: dict[tuple[str, ...], int] = {}
        try:
            resolved_base = self.paths.base_dir.resolve(strict=True)
            directory_fds[()] = os.open(resolved_base, directory_flags)
            for path in self._source_paths():
                try:
                    relative = path.relative_to(self.paths.base_dir)
                except ValueError as exc:
                    raise SearchIndexBuildError(
                        "Search source is outside the runtime directory"
                    ) from exc
                if not relative.parts or ".." in relative.parts:
                    raise SearchIndexBuildError("Search source is outside the runtime directory")

                current_parts: tuple[str, ...] = ()
                for part in relative.parts[:-1]:
                    child_parts = (*current_parts, part)
                    if child_parts not in directory_fds:
                        directory_fds[child_parts] = os.open(
                            part,
                            directory_flags,
                            dir_fd=directory_fds[current_parts],
                        )
                    current_parts = child_parts

                file_descriptor = os.open(
                    relative.parts[-1],
                    file_flags,
                    dir_fd=directory_fds[current_parts],
                )
                try:
                    source_stat = os.fstat(file_descriptor)
                    if not stat_module.S_ISREG(source_stat.st_mode):
                        raise SearchIndexBuildError("Search source is not a regular file")
                    relative_ref = relative.as_posix().encode("utf-8")
                    aggregate.update(len(relative_ref).to_bytes(8, byteorder="big"))
                    aggregate.update(relative_ref)
                    aggregate.update(source_stat.st_size.to_bytes(8, byteorder="big"))
                    bytes_read = 0
                    while True:
                        chunk = os.read(file_descriptor, 1024 * 1024)
                        if not chunk:
                            break
                        bytes_read += len(chunk)
                        aggregate.update(chunk)
                    if bytes_read != source_stat.st_size:
                        raise SearchIndexBuildError("Search source changed while fingerprinting")
                finally:
                    try:
                        os.close(file_descriptor)
                    except OSError:
                        pass
        except SearchIndexBuildError:
            raise
        except OSError as exc:
            raise SearchIndexBuildError("Search sources could not be fingerprinted safely") from exc
        finally:
            for parts in sorted(directory_fds, key=len, reverse=True):
                try:
                    os.close(directory_fds[parts])
                except OSError:
                    pass
        return aggregate.hexdigest()

    def _source_paths(self) -> list[Path]:
        source_paths = set(self._native_source_paths())
        source_paths.update(self._harvested_source_paths())
        return sorted(source_paths, key=self._relative_ref)

    def _iter_records(self) -> Iterator[_IndexRecord]:
        if self.paths.sessions_dir.exists() or self.paths.sessions_dir.is_symlink():
            for meta_path in self._native_meta_paths():
                meta = self._load_json(meta_path)
                if not isinstance(meta, dict):
                    continue
                texts = [str(meta.get("summary", ""))]
                texts.extend(self._native_context_texts(meta_path.parent / "context.json.gz"))
                yield _IndexRecord(
                    source="session",
                    source_ref=self._relative_ref(meta_path),
                    session_id=str(meta.get("session_id", "")),
                    project=str(meta.get("project", "")),
                    started_at=str(meta.get("started_at", "")),
                    texts=texts,
                )

        harvest_dir = self.paths.base_dir / "harvested"
        if harvest_dir.exists() or harvest_dir.is_symlink():
            for session_path in self._harvested_source_paths():
                payload = self._load_json(session_path)
                if not isinstance(payload, dict):
                    continue
                texts = [str(payload.get("summary", ""))]
                messages = payload.get("messages", [])
                if isinstance(messages, list):
                    texts.extend(self._message_contents(messages))
                yield _IndexRecord(
                    source="harvested",
                    source_ref=self._relative_ref(session_path),
                    session_id=self._harvested_session_id(payload),
                    project=str(payload.get("project", "")),
                    started_at=str(payload.get("started_at", "")),
                    texts=texts,
                )

    def _native_context_texts(self, path: Path) -> list[str]:
        if not path.exists() and not path.is_symlink():
            return []
        try:
            safe_path = self.validate_source_path(path)
            raw = gzip.decompress(self.read_source_bytes(safe_path)).decode("utf-8")
            payload = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return []
        messages = payload.get("messages", []) if isinstance(payload, dict) else payload
        return list(self._message_contents(messages)) if isinstance(messages, list) else []

    def _message_contents(self, messages: Iterable[object]) -> Iterator[str]:
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if content is not None:
                yield str(content)

    def _load_json(self, path: Path) -> object:
        try:
            safe_path = self.validate_source_path(path)
            raw = self.read_source_bytes(safe_path).decode("utf-8")
            return json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _native_source_paths(self) -> list[Path]:
        if not self.paths.sessions_dir.exists() and not self.paths.sessions_dir.is_symlink():
            return []
        sessions_dir = self.validate_source_path(self.paths.sessions_dir)
        source_paths: list[Path] = []
        with os.scandir(sessions_dir) as sessions:
            for session in sessions:
                if session.is_symlink():
                    raise SearchIndexBuildError("Search source contains a symlink below runtime")
                if not session.is_dir(follow_symlinks=False):
                    continue
                # Direct, non-symlink descendants of the strictly resolved root
                # cannot resolve outside it; record reads validate the full path again.
                with os.scandir(session.path) as files:
                    for source_file in files:
                        if source_file.name not in {"meta.json", "context.json.gz"}:
                            continue
                        if source_file.is_symlink():
                            raise SearchIndexBuildError(
                                "Search source contains a symlink below runtime"
                            )
                        source_paths.append(Path(source_file.path))
        return source_paths

    def _native_meta_paths(self) -> list[Path]:
        return [path for path in self._native_source_paths() if path.name == "meta.json"]

    def _harvested_source_paths(self) -> list[Path]:
        harvest_dir = self.paths.base_dir / "harvested"
        if not harvest_dir.exists() and not harvest_dir.is_symlink():
            return []
        safe_harvest_dir = self.validate_source_path(harvest_dir)
        source_paths: list[Path] = []
        with os.scandir(safe_harvest_dir) as source_dirs:
            for source_dir in source_dirs:
                if source_dir.is_symlink():
                    raise SearchIndexBuildError("Search source contains a symlink below runtime")
                if not source_dir.is_dir(follow_symlinks=False):
                    continue
                with os.scandir(source_dir.path) as files:
                    for source_file in files:
                        if not source_file.name.endswith(".json"):
                            continue
                        if source_file.is_symlink():
                            raise SearchIndexBuildError(
                                "Search source contains a symlink below runtime"
                            )
                        source_paths.append(Path(source_file.path))
        return source_paths

    def _harvested_session_id(self, payload: dict[str, object]) -> str:
        session_id = str(payload.get("source_session_id") or payload.get("session_id") or "")
        source = str(payload.get("source") or "")
        return f"{source}:{session_id}" if source and session_id else session_id

    def _relative_ref(self, path: Path) -> str:
        try:
            return path.relative_to(self.paths.base_dir).as_posix()
        except ValueError as exc:
            raise SearchIndexBuildError("Search source is outside the runtime directory") from exc

    def _remove_temp_files(self, temp_path: Path) -> None:
        for candidate in (
            temp_path,
            Path(f"{temp_path}-journal"),
            Path(f"{temp_path}-wal"),
            Path(f"{temp_path}-shm"),
        ):
            try:
                candidate.unlink()
            except OSError:
                pass
