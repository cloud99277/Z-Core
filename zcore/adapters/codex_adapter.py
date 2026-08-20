from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from zcore.adapters.base import SourceAdapter
from zcore.models.harvester import HarvestedSession


_FILENAME_RE = re.compile(
    r"rollout-(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})-"
    r"(?P<session_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.jsonl$"
)
_SESSION_ID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_YEAR_RE = re.compile(r"\d{4}$")
_MONTH_DAY_RE = re.compile(r"\d{2}$")


class CodexAdapter(SourceAdapter):
    """Read Codex rollout JSONL files without escaping the sessions root."""

    BASE_DIR = Path.home() / ".codex" / "sessions"

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or Path.home() / ".codex" / "sessions"
        self.errors: list[str] = []
        self._error_cursor = 0

    def name(self) -> str:
        return "codex"

    def discover(self, project: str | None = None) -> list[dict[str, object]]:
        self.errors = []
        self._error_cursor = 0
        discovered: list[tuple[Path, HarvestedSession]] = []
        for path, match in self._iter_session_files():
            session = self._read_session(path, match)
            if session is None or (project is not None and session.project != project):
                continue
            discovered.append((path, session))

        sessions: list[dict[str, object]] = []
        seen_session_ids: set[str] = set()
        for path, session in discovered:
            canonical_id = str(session.metadata["codex_session_id"])
            if canonical_id in seen_session_ids:
                self.errors.append(f"{path}: duplicate Codex session UUID {canonical_id}; skipping")
                continue
            seen_session_ids.add(canonical_id)
            sessions.append(self._session_info(path, session))
        return sessions

    def ingest(self, session_id: str) -> HarvestedSession | None:
        if _SESSION_ID_RE.fullmatch(session_id) is None:
            return None
        canonical_id = session_id.lower()
        for path, match in self._iter_session_files():
            if match.group("session_id").lower() != canonical_id:
                continue
            return self._read_session(path, match)
        return None

    def health_check(self) -> dict[str, object]:
        ok = self._base_dir.is_dir() and not self._base_dir.is_symlink()
        payload: dict[str, object] = {
            "ok": ok,
            "path": str(self._base_dir),
            "errors": list(self.errors),
        }
        if not ok:
            payload["reason"] = "Codex sessions directory not found or is a symlink"
        return payload

    def drain_errors(self) -> list[str]:
        """Return newly observed local-source errors for Harvester sanitization."""
        errors = self.errors[self._error_cursor :]
        self._error_cursor = len(self.errors)
        return list(errors)

    def _iter_session_files(self) -> Iterator[tuple[Path, re.Match[str]]]:
        if self._base_dir.is_symlink():
            self._record_rejected_symlink(self._base_dir, "sessions directory")
            return
        if not self._base_dir.is_dir():
            return
        base_resolved = self._resolve(self._base_dir)
        if base_resolved is None:
            return

        for year_dir in self._iter_child_directories(self._base_dir, _YEAR_RE, "year directory"):
            for month_dir in self._iter_child_directories(year_dir, _MONTH_DAY_RE, "month directory"):
                for day_dir in self._iter_child_directories(month_dir, _MONTH_DAY_RE, "day directory"):
                    try:
                        paths = sorted(day_dir.glob("rollout-*.jsonl"))
                    except OSError as exc:
                        self._record_exception(day_dir, exc)
                        continue
                    for path in paths:
                        if path.is_symlink():
                            self._record_rejected_symlink(path, "session file")
                            continue
                        if not path.is_file() or not self._is_within_base(path, base_resolved):
                            continue
                        match = _FILENAME_RE.fullmatch(path.name)
                        if match is not None:
                            yield path, match

    def _iter_child_directories(
        self,
        parent: Path,
        name_pattern: re.Pattern[str],
        description: str,
    ) -> Iterator[Path]:
        try:
            children = sorted(parent.iterdir())
        except OSError as exc:
            self._record_exception(parent, exc)
            return
        for child in children:
            if not name_pattern.fullmatch(child.name):
                continue
            if child.is_symlink():
                self._record_rejected_symlink(child, description)
                continue
            if child.is_dir():
                yield child

    def _read_session(self, path: Path, match: re.Match[str]) -> HarvestedSession | None:
        errors: list[str] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            error = self._format_error(path, exc)
            self.errors.append(error)
            return None

        messages: list[dict[str, str]] = []
        project = ""
        ended_at: str | None = None
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
            payload = event.get("payload")
            if event.get("type") == "turn_context" and isinstance(payload, dict):
                cwd = payload.get("cwd")
                if isinstance(cwd, str):
                    project = cwd
                continue
            if event.get("type") != "response_item" or not isinstance(payload, dict):
                continue
            if payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = self._extract_content_text(payload.get("content"))
            if not content:
                continue
            messages.append({"role": role, "content": content})
            timestamp = event.get("timestamp")
            if isinstance(timestamp, str) and timestamp:
                ended_at = timestamp

        if not messages:
            return None
        canonical_id = match.group("session_id").lower()
        return HarvestedSession(
            source=self.name(),
            source_session_id=canonical_id,
            project=project,
            started_at=self._started_at(match.group("timestamp")),
            ended_at=ended_at,
            messages=messages,
            metadata={
                "codex_session_id": canonical_id,
                "path": str(path),
                "errors": errors,
            },
        )

    def _session_info(self, path: Path, session: HarvestedSession) -> dict[str, object]:
        return {
            "source": self.name(),
            "source_session_id": session.source_session_id,
            "codex_session_id": session.metadata["codex_session_id"],
            "project": session.project,
            "started_at": session.started_at,
            "message_count": len(session.messages),
            "path": str(path),
            "metadata": session.metadata,
        }

    def _resolve(self, path: Path) -> Path | None:
        try:
            return path.resolve(strict=True)
        except OSError as exc:
            self._record_exception(path, exc)
            return None

    def _is_within_base(self, path: Path, base_resolved: Path) -> bool:
        resolved = self._resolve(path)
        if resolved is None:
            return False
        try:
            resolved.relative_to(base_resolved)
        except ValueError:
            self.errors.append(f"{path}: rejected path outside sessions directory")
            return False
        return True

    @staticmethod
    def _started_at(filename_timestamp: str) -> str:
        return f"{filename_timestamp[:11]}{filename_timestamp[11:].replace('-', ':')}"

    @staticmethod
    def _extract_content_text(content: object) -> str:
        if isinstance(content, str):
            return content if content.strip() else ""
        if not isinstance(content, list):
            return ""
        texts: list[str] = []
        for block in content:
            if (
                not isinstance(block, dict)
                or block.get("type") not in {"text", "input_text", "output_text"}
            ):
                continue
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
        return "\n".join(texts)

    @staticmethod
    def _format_error(path: Path, exc: Exception) -> str:
        return f"{path}: {type(exc).__name__}: {exc}"

    def _record_exception(self, path: Path, exc: OSError) -> None:
        self.errors.append(self._format_error(path, exc))

    def _record_rejected_symlink(self, path: Path, description: str) -> None:
        self.errors.append(f"{path}: rejected symlink {description}")
