from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from zcore.adapters.base import SourceAdapter
from zcore.models.harvester import HarvestedSession


class OpenClawAdapter(SourceAdapter):
    """Read OpenClaw JSON event streams without following source symlinks."""

    ID_SEPARATOR = "."
    ID_HASH_LENGTH = 12

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or Path.home() / ".openclaw" / "agents"
        self.errors: list[str] = []
        self._error_cursor = 0

    def name(self) -> str:
        return "openclaw"

    def discover(self, project: str | None = None) -> list[dict[str, object]]:
        self.errors = []
        self._error_cursor = 0
        if not self._base_dir.is_dir():
            return []

        discovered: list[tuple[Path, HarvestedSession]] = []
        try:
            agent_dirs = sorted(self._base_dir.iterdir())
        except OSError as exc:
            self._record_exception(self._base_dir, exc)
            return []

        for agent_dir in agent_dirs:
            if agent_dir.is_symlink():
                self._record_rejected_symlink(agent_dir, "agent directory")
                continue
            if not agent_dir.is_dir():
                continue
            if project is not None and agent_dir.name != project:
                continue
            sessions_dir = agent_dir / "sessions"
            if sessions_dir.is_symlink():
                self._record_rejected_symlink(sessions_dir, "sessions directory")
                continue
            if not sessions_dir.is_dir():
                continue
            try:
                paths = sorted((*sessions_dir.glob("*.json"), *sessions_dir.glob("*.jsonl")))
            except OSError as exc:
                self._record_exception(sessions_dir, exc)
                continue
            for path in paths:
                if path.is_symlink():
                    self._record_rejected_symlink(path, "session file")
                    continue
                session = self._read_session(path, agent_dir.name)
                if session is not None:
                    discovered.append((path, session))

        return [self._session_info(path, session) for path, session in discovered]

    def ingest(self, session_id: str) -> HarvestedSession | None:
        decoded = self._decode_session_id(session_id)
        if decoded is None:
            return None
        agent, stem, path_hash = decoded
        if not self._is_safe_component(agent) or not self._is_safe_component(stem):
            return None

        agent_dir = self._base_dir / agent
        if agent_dir.is_symlink():
            self._record_rejected_symlink(agent_dir, "agent directory")
            return None
        sessions_dir = agent_dir / "sessions"
        if sessions_dir.is_symlink():
            self._record_rejected_symlink(sessions_dir, "sessions directory")
            return None

        for suffix in (".json", ".jsonl"):
            path = sessions_dir / f"{stem}{suffix}"
            if self._path_hash(path) != path_hash:
                continue
            if path.is_symlink():
                self._record_rejected_symlink(path, "session file")
                return None
            if not path.is_file():
                return None
            session = self._read_session(path, agent)
            return replace(session, source_session_id=session_id) if session is not None else None
        return None

    def health_check(self) -> dict[str, object]:
        ok = self._base_dir.is_dir()
        payload: dict[str, object] = {
            "ok": ok,
            "path": str(self._base_dir),
            "errors": list(self.errors),
        }
        if not ok:
            payload["reason"] = "OpenClaw agents directory not found"
        return payload

    def drain_errors(self) -> list[str]:
        """Return errors not yet observed by the harvester without hiding health data."""
        errors = self.errors[self._error_cursor :]
        self._error_cursor = len(self.errors)
        return list(errors)

    def _session_info(self, path: Path, session: HarvestedSession) -> dict[str, object]:
        return {
            "source": self.name(),
            "source_session_id": self._public_session_id(path, session.project),
            "openclaw_session_id": path.stem,
            "project": session.project,
            "started_at": session.metadata["first_event_timestamp"] or session.started_at,
            "message_count": len(session.messages),
            "path": str(path),
            "metadata": session.metadata,
        }

    def _read_session(self, path: Path, agent: str) -> HarvestedSession | None:
        errors: list[str] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            error = self._format_error(path, exc)
            errors.append(error)
            self.errors.append(error)
            return None

        messages: list[dict[str, str]] = []
        first_event_timestamp = ""
        started_at = ""
        ended_at: str | None = None
        model = ""
        api = ""
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                error = f"{path}:{line_number}: {exc.msg}"
                errors.append(error)
                self.errors.append(error)
                continue
            if not isinstance(event, dict):
                continue
            if not first_event_timestamp and isinstance(event.get("timestamp"), str):
                first_event_timestamp = event["timestamp"]
            if event.get("type") != "message":
                continue
            message = event.get("message")
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = self._extract_content_text(message.get("content"))
            if not content:
                continue
            messages.append({"role": role, "content": content})
            timestamp = event.get("timestamp")
            if isinstance(timestamp, str) and timestamp:
                if role == "user" and not started_at:
                    started_at = timestamp
                ended_at = timestamp
            if not model and isinstance(message.get("model"), str):
                model = message["model"]
            if not api and isinstance(message.get("api"), str):
                api = message["api"]

        if not messages:
            return None
        return HarvestedSession(
            source=self.name(),
            source_session_id=self._public_session_id(path, agent),
            project=agent,
            started_at=started_at,
            ended_at=ended_at,
            messages=messages,
            metadata={
                "openclaw_session_id": path.stem,
                "agent": agent,
                "first_event_timestamp": first_event_timestamp,
                "model": model,
                "api": api,
                "path": str(path),
                "errors": errors,
            },
        )

    def _public_session_id(self, path: Path, agent: str) -> str:
        encoded_stem = base64.urlsafe_b64encode(path.stem.encode("utf-8")).decode("ascii").rstrip("=")
        return f"{agent}/{encoded_stem}{self.ID_SEPARATOR}{self._path_hash(path)}"

    def _decode_session_id(self, session_id: str) -> tuple[str, str, str] | None:
        agent, separator, encoded_path = session_id.partition("/")
        encoded_stem, hash_separator, path_hash = encoded_path.rpartition(self.ID_SEPARATOR)
        if (
            not separator
            or not hash_separator
            or not encoded_stem
            or "/" in encoded_stem
            or "\\" in encoded_stem
            or len(path_hash) != self.ID_HASH_LENGTH
            or any(character not in "0123456789abcdef" for character in path_hash)
        ):
            return None
        padding = "=" * (-len(encoded_stem) % 4)
        try:
            stem = base64.b64decode(
                encoded_stem + padding,
                altchars=b"-_",
                validate=True,
            ).decode("utf-8")
        except (UnicodeError, binascii.Error):
            return None
        return agent, stem, path_hash

    def _path_hash(self, path: Path) -> str:
        try:
            value = path.relative_to(self._base_dir).as_posix()
        except ValueError:
            value = str(path)
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[: self.ID_HASH_LENGTH]

    @staticmethod
    def _extract_content_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        texts: list[str] = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") not in {"text", "input_text"}:
                continue
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
        return "\n".join(texts)

    @staticmethod
    def _is_safe_component(value: str) -> bool:
        return bool(value) and "/" not in value and "\\" not in value and "\x00" not in value and value not in {".", ".."}

    @staticmethod
    def _format_error(path: Path, exc: Exception) -> str:
        return f"{path}: {type(exc).__name__}: {exc}"

    def _record_exception(self, path: Path, exc: OSError) -> None:
        self.errors.append(self._format_error(path, exc))

    def _record_rejected_symlink(self, path: Path, layer: str) -> None:
        self.errors.append(f"{path}: rejected symbolic-link {layer}")
