from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from zcore.adapters.base import SourceAdapter
from zcore.models.harvester import HarvestedSession


class ClaudeAdapter(SourceAdapter):
    ID_SEPARATOR = "#"

    def __init__(self, projects_dir: Path | None = None):
        self.projects_dir = projects_dir or Path.home() / ".claude" / "projects"
        self.errors: list[str] = []

    def name(self) -> str:
        return "claude"

    def discover(self, project: str | None = None) -> list[dict[str, object]]:
        self.errors = []
        if not self.projects_dir.exists():
            return []

        discovered: list[tuple[Path, HarvestedSession]] = []
        for path in sorted(self.projects_dir.rglob("*.jsonl")):
            session = self._read_session(path)
            if session is None:
                continue
            if project is not None and session.project != project:
                continue
            discovered.append((path, session))

        session_counts: dict[str, int] = {}
        for _, session in discovered:
            session_counts[session.source_session_id] = session_counts.get(session.source_session_id, 0) + 1

        sessions: list[dict[str, object]] = []
        for path, session in discovered:
            public_id = session.source_session_id
            if session_counts[session.source_session_id] > 1:
                public_id = self._public_session_id(session.source_session_id, path)
            sessions.append(self._session_info(session, path, public_id))
        return sessions

    def ingest(self, session_id: str) -> HarvestedSession | None:
        if not self.projects_dir.exists():
            return None
        canonical_id, path_hash = self._split_public_session_id(session_id)
        for path in sorted(self.projects_dir.rglob("*.jsonl")):
            if path_hash is not None and self._path_hash(path) != path_hash:
                continue
            session = self._read_session(path)
            if session is not None and session.source_session_id == canonical_id:
                metadata = dict(session.metadata)
                metadata["claude_session_id"] = session.source_session_id
                return replace(session, source_session_id=session_id, metadata=metadata)
        return None

    def health_check(self) -> dict[str, object]:
        return {
            "ok": self.projects_dir.exists(),
            "path": str(self.projects_dir),
            "errors": list(self.errors),
        }

    def _session_info(self, session: HarvestedSession, path: Path, public_id: str) -> dict[str, object]:
        return {
            "source": self.name(),
            "source_session_id": public_id,
            "claude_session_id": session.source_session_id,
            "project": session.project,
            "started_at": session.started_at,
            "message_count": len(session.messages),
            "path": str(path),
        }

    def _read_session(self, path: Path) -> HarvestedSession | None:
        messages: list[dict[str, str]] = []
        timestamps: list[str] = []
        session_id = ""
        project = ""
        errors: list[str] = []

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            error_text = f"{path}: {type(exc).__name__}: {exc}"
            self.errors.append(error_text)
            return None

        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                error_text = f"{path}:{line_number}: {exc.msg}"
                errors.append(error_text)
                self.errors.append(error_text)
                continue
            if not isinstance(item, dict) or item.get("type") not in {"user", "assistant"}:
                continue
            message = item.get("message", {})
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or item.get("type") or "")
            content = message.get("content")
            if not isinstance(content, str):
                continue
            messages.append({"role": role, "content": content})
            if not session_id and item.get("sessionId"):
                session_id = str(item["sessionId"])
            if not project and item.get("cwd"):
                project = str(item["cwd"])
            if item.get("timestamp"):
                timestamps.append(str(item["timestamp"]))

        if not session_id:
            session_id = path.stem
        if not messages:
            return None

        return HarvestedSession(
            source=self.name(),
            source_session_id=session_id,
            project=project,
            started_at=min(timestamps) if timestamps else "",
            messages=messages,
            metadata={"path": str(path), "errors": errors, "claude_session_id": session_id},
        )

    def _public_session_id(self, session_id: str, path: Path) -> str:
        return f"{session_id}{self.ID_SEPARATOR}{self._path_hash(path)}"

    def _split_public_session_id(self, session_id: str) -> tuple[str, str | None]:
        canonical_id, separator, path_hash = session_id.rpartition(self.ID_SEPARATOR)
        if not separator or not canonical_id or len(path_hash) != 12:
            return session_id, None
        return canonical_id, path_hash

    def _path_hash(self, path: Path) -> str:
        try:
            value = str(path.relative_to(self.projects_dir))
        except ValueError:
            value = str(path)
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
