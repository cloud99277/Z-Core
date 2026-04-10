from __future__ import annotations

import gzip
import json
import random
import shutil
from datetime import UTC, datetime, timedelta
import re
import uuid

from zcore.models.session import SessionMeta
from zcore.runtime import RuntimePaths
from zcore.utils.filelock import FileLock
from zcore.utils.fs import atomic_write_json, atomic_write_text
from zcore.utils.prompts import render_prompt_template
from zcore.utils.time import parse_since_window


class SessionManager:
    def __init__(self, paths: RuntimePaths | None = None):
        self.paths = paths or RuntimePaths.discover()
        self.index_lock = self.paths.lock_dir / "sessions-index.lock"

    LAZY_GC_PROBABILITY = 0.05  # 5% chance per session start

    def start(self, project: str, agent: str, *, tags: list[str] | None = None, resume_from: str | None = None) -> SessionMeta:
        self.paths.ensure_runtime_dirs()
        meta = SessionMeta(
            session_id=uuid.uuid4().hex[:12],
            project=project,
            agent=agent,
            parent_session=resume_from,
            tags=tags or [],
        )
        session_dir = self.paths.sessions_dir / meta.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(session_dir / "meta.json", meta.to_dict())
        self._upsert(meta)
        if random.random() < self.LAZY_GC_PROBABILITY:
            self._lazy_gc()
        return meta

    def end(
        self,
        session_id: str,
        *,
        messages: list[dict] | None = None,
        ghost_agent=None,
        auto_compact: bool = True,
        auto_extract_memory: bool = True,
        model: str = "sonnet",
    ) -> SessionMeta:
        session_dir = self.paths.sessions_dir / session_id
        meta_path = session_dir / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        meta = SessionMeta(**json.loads(meta_path.read_text(encoding="utf-8")))
        meta.status = "completed"
        meta.ended_at = datetime.now(UTC).isoformat()

        if messages:
            with gzip.open(session_dir / "context.json.gz", "wt", encoding="utf-8") as handle:
                json.dump(messages, handle, ensure_ascii=False)
            meta.summary = self._derive_summary("", messages)
            if ghost_agent is not None:
                if auto_compact:
                    compact = ghost_agent.compact_messages(messages, model=model)
                    meta.compaction_mode = str(compact.get("mode", "none"))
                    compact_summary = str(compact.get("summary", "")).strip()
                    atomic_write_text(session_dir / "context.md", compact_summary + "\n")
                    meta.summary = self._derive_summary(compact_summary, messages)
                    meta.compactions = 1 if compact_summary else 0
                if auto_extract_memory:
                    from zcore.engines.memory import MemoryEngine

                    memories = MemoryEngine(self.paths).extract_from_conversation(
                        messages,
                        model=model,
                        project=meta.project,
                        agent=meta.agent,
                        session_id=meta.session_id,
                    )
                    meta.memory_mode = memories.mode
                    atomic_write_json(session_dir / "memories.json", memories.to_dict())
            from zcore.engines.context import ContextEngine

            meta.token_count_end = ContextEngine(self.paths).analyze(messages, model).total_tokens

        atomic_write_json(meta_path, meta.to_dict())
        self._upsert(meta)
        return meta

    def list(
        self,
        *,
        project: str | None = None,
        agent: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[SessionMeta]:
        if not self.paths.session_index_path.exists():
            return []
        try:
            payload = json.loads(self.paths.session_index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        sessions = []
        for item in payload.get("sessions", []):
            if not isinstance(item, dict):
                continue
            item = dict(item)
            if "id" in item and "session_id" not in item:
                item["session_id"] = item.pop("id")
            meta = SessionMeta(**item)
            if project and meta.project != project:
                continue
            if agent and meta.agent != agent:
                continue
            if status and meta.status != status:
                continue
            sessions.append(meta)
        sessions.sort(key=self._sort_key, reverse=True)
        return sessions[:limit]

    def get(self, session_id: str) -> SessionMeta:
        meta_path = self.paths.sessions_dir / session_id / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        return SessionMeta(**json.loads(meta_path.read_text(encoding="utf-8")))

    def pause(self, session_id: str | None = None) -> SessionMeta:
        meta = self._resolve_target_session(session_id=session_id, status="active")
        meta.status = "paused"
        meta.paused_at = datetime.now(UTC).isoformat()
        self._persist_meta(meta)
        return meta

    def resume(self, session_id: str | None = None) -> SessionMeta:
        meta = self._resolve_target_session(session_id=session_id, status="paused")
        meta.status = "active"
        meta.resumed_at = datetime.now(UTC).isoformat()
        self._persist_meta(meta)
        return meta

    def find_latest(self, *, project: str, status: str = "completed") -> SessionMeta | None:
        sessions = self.list(project=project, status=status, limit=1)
        return sessions[0] if sessions else None

    def load_context(self, session_id: str) -> str:
        context_path = self.paths.sessions_dir / session_id / "context.md"
        if context_path.exists():
            return context_path.read_text(encoding="utf-8").strip()
        return ""

    def handoff(self, session_id: str, to_agent: str, *, note: str | None = None) -> str:
        meta = self.get(session_id)
        session_dir = self.paths.sessions_dir / session_id
        context_snapshot = self.load_context(session_id) or meta.summary or "No context summary captured."
        memories = self._load_memories(session_dir / "memories.json")
        decisions = self._extract_section(context_snapshot, "Key Technical Decisions Made")
        current_state = self._extract_section(context_snapshot, "Exact Current State")
        if not decisions:
            decisions = self._render_memories(memories) or "- No recorded decisions."
        if not current_state:
            current_state = meta.summary or "No explicit working state captured."

        document = render_prompt_template(
            "session_handoff.md",
            project=meta.project,
            from_agent=meta.agent,
            session_id=meta.session_id,
            duration=self._format_duration(meta),
            context_snapshot=context_snapshot,
            decisions=decisions,
            current_state=current_state,
            related_memories=self._render_memories(memories) or "- No related memories recorded.",
            handoff_note=note or f"Continue the session with agent {to_agent}.",
        )
        atomic_write_text(session_dir / "handoff.md", document + "\n")
        return document

    def show_session(self, session_id: str) -> dict[str, object]:
        meta = self.get(session_id)
        session_dir = self.paths.sessions_dir / session_id
        context_path = session_dir / "context.json.gz"
        duration = self._format_duration(meta)
        return {
            **meta.to_dict(),
            "duration": duration,
            "context_snapshot_size": context_path.stat().st_size if context_path.exists() else 0,
        }

    def cleanup_sessions(self, *, older_than: str = "30d", dry_run: bool = False) -> dict[str, object]:
        cutoff = parse_since_window(older_than)
        removed: list[dict[str, str]] = []
        kept_sessions = []
        current_sessions = self.list(limit=10000)
        for meta in current_sessions:
            session_dir = self.paths.sessions_dir / meta.session_id
            if meta.status != "completed":
                kept_sessions.append(meta.to_dict())
                continue
            reference = meta.ended_at or meta.started_at
            try:
                session_time = datetime.fromisoformat(reference)
            except ValueError:
                kept_sessions.append(meta.to_dict())
                continue
            if session_time.tzinfo is None:
                session_time = session_time.replace(tzinfo=UTC)
            else:
                session_time = session_time.astimezone(UTC)
            if session_time < cutoff:
                removed.append({"session_id": meta.session_id, "path": str(session_dir)})
                if not dry_run and session_dir.exists():
                    shutil.rmtree(session_dir, ignore_errors=True)
                continue
            kept_sessions.append(meta.to_dict())

        if not dry_run:
            with FileLock(self.index_lock):
                atomic_write_json(self.paths.session_index_path, {"schema_version": "2.0", "sessions": kept_sessions})
        return {"ok": True, "older_than": older_than, "dry_run": dry_run, "removed": removed}

    def _read_index(self) -> dict[str, object]:
        if not self.paths.session_index_path.exists():
            return {"schema_version": "2.0", "sessions": []}
        return json.loads(self.paths.session_index_path.read_text(encoding="utf-8"))

    def _persist_meta(self, meta: SessionMeta) -> None:
        session_dir = self.paths.sessions_dir / meta.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(session_dir / "meta.json", meta.to_dict())
        self._upsert(meta)

    def _resolve_target_session(self, *, session_id: str | None, status: str) -> SessionMeta:
        if session_id:
            meta = self.get(session_id)
        else:
            sessions = self.list(status=status, limit=1)
            if not sessions:
                raise FileNotFoundError(f"No {status} session found")
            meta = sessions[0]
        if meta.status != status:
            raise ValueError(f"Session {meta.session_id} must be {status}, found {meta.status}")
        return meta

    def _upsert(self, meta: SessionMeta) -> None:
        with FileLock(self.index_lock):
            index = self._read_index()
            sessions = [item for item in index.get("sessions", []) if item.get("session_id") != meta.session_id]
            sessions.append(meta.to_dict())
            index["sessions"] = sessions
            atomic_write_json(self.paths.session_index_path, index)

    def _lazy_gc(self) -> None:
        """Remove expired session snapshot directories (probabilistic, non-blocking)."""
        try:
            from zcore.config import get_nested, load_config
            config = load_config(self.paths)
            retention_days = int(get_nested(config, "session", "snapshot_retention_days", default=30))
        except Exception:
            retention_days = 30

        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        if not self.paths.sessions_dir.exists():
            return

        for session_dir in self.paths.sessions_dir.iterdir():
            if not session_dir.is_dir() or session_dir.name == "index.json":
                continue
            meta_path = session_dir / "meta.json"
            if not meta_path.exists():
                continue
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                ended_at = data.get("ended_at") or data.get("started_at", "")
                if not ended_at:
                    continue
                session_time = datetime.fromisoformat(ended_at)
                if session_time < cutoff and data.get("status") == "completed":
                    shutil.rmtree(session_dir, ignore_errors=True)
            except (OSError, json.JSONDecodeError, ValueError):
                continue

    def _sort_key(self, meta: SessionMeta) -> str:
        return meta.ended_at or meta.started_at

    def _derive_summary(self, compact_summary: str, messages: list[dict]) -> str:
        if compact_summary:
            for line in compact_summary.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith("-"):
                    return stripped[:160]

        for message in reversed(messages):
            content = str(message.get("content", "")).strip()
            if content:
                return content[:160]
        return ""

    def _load_memories(self, path) -> list[str]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        rendered: list[str] = []
        for entry in entries:
            if isinstance(entry, dict):
                content = str(entry.get("content", "")).strip()
            else:
                content = str(entry).strip()
            if content:
                rendered.append(content)
        return rendered

    def _render_memories(self, memories: list[str]) -> str:
        if not memories:
            return ""
        return "\n".join(f"- {memory}" for memory in memories)

    def _extract_section(self, text: str, heading: str) -> str:
        pattern = re.compile(
            rf"^##\s+\d+\.\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+\d+\.\s+|\Z)",
            flags=re.MULTILINE,
        )
        match = pattern.search(text)
        if not match:
            return ""
        return match.group(1).strip()

    def _format_duration(self, meta: SessionMeta) -> str:
        if not meta.ended_at:
            return "in progress"
        started = datetime.fromisoformat(meta.started_at)
        ended = datetime.fromisoformat(meta.ended_at)
        delta = ended - started
        minutes = int(delta.total_seconds() // 60)
        if minutes < 1:
            return "<1 min"
        hours, remainder = divmod(minutes, 60)
        if hours:
            return f"{hours}h {remainder}m"
        return f"{minutes}m"
