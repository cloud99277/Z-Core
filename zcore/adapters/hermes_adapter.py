from __future__ import annotations

import json
from pathlib import Path

from zcore.adapters.base import SourceAdapter
from zcore.models.harvester import HarvestedSession


class HermesAdapter(SourceAdapter):
    def __init__(self, sessions_dir: Path | None = None):
        self.sessions_dir = sessions_dir or Path.home() / ".hermes" / "sessions"
        self.errors: list[str] = []

    def name(self) -> str:
        return "hermes"

    def discover(self, project: str | None = None) -> list[dict[str, object]]:
        self.errors = []
        if not self.sessions_dir.exists():
            return []

        sessions: list[dict[str, object]] = []
        for path in sorted(self.sessions_dir.glob("session_*.json")):
            session = self._read_session(path)
            if session is None:
                continue
            if project is not None and session.project != project:
                continue
            sessions.append(
                {
                    "source": self.name(),
                    "source_session_id": session.source_session_id,
                    "project": session.project,
                    "started_at": session.started_at,
                    "message_count": len(session.messages),
                    "path": str(path),
                    "metadata": session.metadata,
                }
            )
        return sessions

    def ingest(self, session_id: str) -> HarvestedSession | None:
        if not self.sessions_dir.exists():
            return None
        for path in sorted(self.sessions_dir.glob("session_*.json")):
            session = self._read_session(path)
            if session is not None and session.source_session_id == session_id:
                return session
        return None

    def health_check(self) -> dict[str, object]:
        return {
            "ok": self.sessions_dir.exists(),
            "path": str(self.sessions_dir),
            "errors": list(self.errors),
        }

    def _read_session(self, path: Path) -> HarvestedSession | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.errors.append(f"{path}: {type(exc).__name__}: {exc}")
            return None
        if not isinstance(payload, dict):
            return None

        messages = []
        for message in payload.get("messages", []):
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if isinstance(role, str) and isinstance(content, str):
                messages.append({"role": role, "content": content})

        session_id = str(payload.get("session_id") or path.stem.removeprefix("session_"))
        platform = str(payload.get("platform", ""))
        return HarvestedSession(
            source=self.name(),
            source_session_id=session_id,
            project=platform,
            started_at=str(payload.get("session_start") or ""),
            ended_at=str(payload["last_updated"]) if payload.get("last_updated") else None,
            messages=messages,
            metadata={
                "model": payload.get("model", ""),
                "platform": platform,
                "path": str(path),
            },
        )
