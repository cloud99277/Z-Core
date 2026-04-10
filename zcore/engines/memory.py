from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path

from zcore.config import get_nested, load_config
from zcore.models.memory import MEMORY_TYPES, MemoryEntry
from zcore.runtime import RuntimePaths
from zcore.utils.filelock import FileLock
from zcore.utils.fs import atomic_write_json, atomic_write_text, ensure_dir
from zcore.utils.prompts import render_prompt_template
from zcore.utils.time import parse_since_window


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "general"


def _extract_json_array(text: str) -> list[dict[str, object]]:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        payload = json.loads(stripped)
        return payload if isinstance(payload, list) else []
    start = stripped.find("[")
    end = stripped.rfind("]")
    if start != -1 and end != -1 and end > start:
        payload = json.loads(stripped[start : end + 1])
        return payload if isinstance(payload, list) else []
    return []


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _keywords(value: str) -> set[str]:
    normalized = _normalize_text(value)
    return set(re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", normalized))


@dataclass
class ExtractionResult:
    entries: list[MemoryEntry] = field(default_factory=list)
    admitted: int = 0
    pending: int = 0
    discarded: int = 0
    mode: str = "none"

    def to_dict(self) -> dict[str, object]:
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "admitted": self.admitted,
            "pending": self.pending,
            "discarded": self.discarded,
            "mode": self.mode,
        }


class TopicStore:
    def __init__(self, paths: RuntimePaths | None = None):
        self.paths = paths or RuntimePaths.discover()
        self.lock_path = self.paths.lock_dir / "memory-topics.lock"

    def read_topic(self, topic_name: str) -> list[MemoryEntry]:
        topic = _slugify(topic_name)
        topic_path = self.paths.topics_dir / f"{topic}.md"
        if not topic_path.exists():
            return []

        entries: list[MemoryEntry] = []
        for line in topic_path.read_text(encoding="utf-8").splitlines():
            entry = MemoryEntry.from_markdown_line(line, topic=topic)
            if entry is not None:
                entries.append(entry)
        return entries

    def write_entry(self, entry: MemoryEntry) -> None:
        topic = _slugify(entry.topic)
        topic_path = self.paths.topics_dir / f"{topic}.md"
        normalized_entry = MemoryEntry.from_dict({**entry.to_dict(), "topic": topic})
        ensure_dir(topic_path.parent)
        with FileLock(self.lock_path):
            existing = topic_path.read_text(encoding="utf-8").splitlines() if topic_path.exists() else []
            existing.append(normalized_entry.to_markdown_line())
            atomic_write_text(topic_path, "\n".join(existing).strip() + "\n")

    def rewrite_topic(self, topic_name: str, entries: list[MemoryEntry]) -> None:
        topic = _slugify(topic_name)
        topic_path = self.paths.topics_dir / f"{topic}.md"
        ensure_dir(topic_path.parent)
        with FileLock(self.lock_path):
            lines = [entry.to_markdown_line() for entry in entries]
            text = "\n".join(lines).strip()
            atomic_write_text(topic_path, (text + "\n") if text else "")

    def list_topics(self) -> list[str]:
        if not self.paths.topics_dir.exists():
            return []
        return sorted(path.stem for path in self.paths.topics_dir.glob("*.md"))

    def topic_counts(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for topic in self.list_topics():
            items.append({"topic": topic, "count": len(self.read_topic(topic))})
        return items

    def all_entries(self) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        for topic in self.list_topics():
            entries.extend(self.read_topic(topic))
        return entries


class MemoryEngine:
    def __init__(self, paths: RuntimePaths | None = None):
        self.paths = paths or RuntimePaths.discover()
        self.store = TopicStore(self.paths)
        self.config = load_config(self.paths)
        self.pending_path = self.paths.staging_dir / "pending-confirm.json"
        self.pending_lock = self.paths.lock_dir / "memory-pending.lock"
        self.log_lock = self.paths.lock_dir / "memory-extraction-log.lock"
        self.migrate_lock = self.paths.lock_dir / "memory-migrate.lock"

    def get_stats(self) -> dict[str, object]:
        entries: list[dict[str, object]] = []
        if self.paths.whiteboard_path.exists():
            try:
                data = json.loads(self.paths.whiteboard_path.read_text(encoding="utf-8"))
                raw_entries = data.get("entries", [])
                if isinstance(raw_entries, list):
                    entries = [entry for entry in raw_entries if isinstance(entry, dict)]
            except (OSError, json.JSONDecodeError):
                entries = []

        topic_entries = self.store.all_entries()
        by_type = Counter(str(entry.get("type", "unknown")) for entry in entries)
        by_type.update(entry.type for entry in topic_entries)
        recent_write_at = None
        if topic_entries:
            recent_write_at = max(entry.updated_at for entry in topic_entries)
        disk_usage_bytes = 0
        if self.paths.topics_dir.exists():
            for path in self.paths.topics_dir.glob("*.md"):
                disk_usage_bytes += path.stat().st_size

        return {
            "whiteboard_entries": len(entries),
            "topic_entries": len(topic_entries),
            "total_entries": len(entries) + len(topic_entries),
            "by_type": dict(by_type),
            "topic_count": len(self.store.list_topics()),
            "topics": self.store.topic_counts(),
            "disk_usage_bytes": disk_usage_bytes,
            "recent_write_at": recent_write_at,
            "rag_available": self.paths.knowledge_db_path.exists(),
        }

    def write_memory(self, content: str, *, topic: str = "general", tags: list[str] | None = None) -> MemoryEntry:
        normalized_tags = [tag.strip() for tag in (tags or []) if tag.strip()]
        source = "manual"
        if normalized_tags:
            source = f"manual tags={','.join(normalized_tags)}"
        entry = MemoryEntry(
            type="fact",
            content=content,
            topic=topic,
            source=source,
        )
        written = self.write(entry)
        return written or entry

    def list_topics(self) -> list[dict[str, object]]:
        return self.store.topic_counts()

    def extract_from_conversation(
        self,
        messages: list[dict[str, object]],
        *,
        model: str = "sonnet",
        project: str | None = None,
        agent: str | None = None,
        session_id: str | None = None,
    ) -> ExtractionResult:
        min_turns = int(get_nested(self.config, "memory_extraction", "min_turns_for_extraction", default=3))
        if len(messages) < min_turns:
            return ExtractionResult(mode="skipped")

        from zcore.engines.ghost_agent import GhostAgent

        ghost_agent = GhostAgent(self.paths)
        existing = self.store.all_entries()
        transcript = self._conversation_to_text(messages)
        prompt = render_prompt_template(
            "memory_extract",
            existing_memories=self._render_existing_memories(existing),
            conversation=transcript,
        )

        status = ghost_agent.availability()
        mode = "heuristic"
        extracted_entries: list[MemoryEntry] = []
        if status.get("available"):
            response = ghost_agent.generate(prompt, fallback_text="[]")
            try:
                payload = _extract_json_array(str(response.get("text", "[]")))
                extracted_entries = self._entries_from_payload(
                    payload,
                    project=project,
                    agent=agent,
                    session_id=session_id,
                )
                mode = str(response.get("mode", "llm"))
            except (ValueError, json.JSONDecodeError):
                extracted_entries = []

        if not extracted_entries:
            extracted_entries = self._heuristic_extract(
                messages,
                project=project,
                agent=agent,
                session_id=session_id,
            )
            mode = "heuristic"

        result = self._admit_entries(extracted_entries)
        result.mode = mode
        self._append_log(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "session_id": session_id or "",
                "model": model,
                "mode": mode,
                "entries_count": len(extracted_entries),
                "admitted": result.admitted,
                "pending": result.pending,
                "discarded": result.discarded,
            }
        )
        return result

    def dedup(self, entry: MemoryEntry, existing: list[MemoryEntry]) -> bool:
        threshold = float(get_nested(self.config, "memory_extraction", "dedup_threshold", default=0.85))
        candidate_text = _normalize_text(entry.content)
        candidate_keywords = _keywords(entry.content)
        for current in existing:
            current_text = _normalize_text(current.content)
            if candidate_text == current_text:
                return True
            if SequenceMatcher(None, candidate_text, current_text).ratio() > threshold:
                return True
            current_keywords = _keywords(current.content)
            if candidate_keywords and current_keywords:
                overlap = len(candidate_keywords & current_keywords) / max(
                    1, min(len(candidate_keywords), len(current_keywords))
                )
                if overlap > threshold:
                    return True
        return False

    def auto_topic(self, entry: MemoryEntry) -> str:
        if entry.project:
            return _slugify(entry.project)
        if entry.topic and entry.topic != "general":
            return _slugify(entry.topic)

        existing_topics = self.store.list_topics()
        keywords = _keywords(entry.content)
        for topic in existing_topics:
            topic_keywords = _keywords(topic.replace("-", " "))
            if topic_keywords and topic_keywords & keywords:
                return topic
        return "general"

    def write(self, entry: MemoryEntry) -> MemoryEntry | None:
        existing = self.store.all_entries()
        normalized = MemoryEntry.from_dict({**entry.to_dict(), "topic": self.auto_topic(entry)})
        if self.dedup(normalized, existing):
            return None
        self.store.write_entry(normalized)
        return normalized

    def list_entries(
        self,
        *,
        topic: str | None = None,
        type_name: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryEntry]:
        entries = self.store.read_topic(topic) if topic else self.store.all_entries()
        if type_name:
            entries = [entry for entry in entries if entry.type == type_name]
        entries.sort(key=lambda entry: entry.updated_at, reverse=True)
        if limit is not None:
            entries = entries[:limit]
        return entries

    def search(self, query: str, *, limit: int = 10) -> list[MemoryEntry]:
        needle = query.strip().lower()
        if not needle:
            return []
        results = [
            entry
            for entry in self.store.all_entries()
            if needle in entry.content.lower() or needle in entry.topic.lower() or needle in (entry.project or "").lower()
        ]
        results.sort(key=lambda entry: (needle in entry.content.lower(), entry.updated_at), reverse=True)
        return results[:limit]

    def list_pending(self) -> list[dict[str, object]]:
        if not self.pending_path.exists():
            return []
        try:
            payload = json.loads(self.pending_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        items = payload.get("entries", []) if isinstance(payload, dict) else []
        return [item for item in items if isinstance(item, dict)]

    def confirm_pending(self, entry_id: str) -> MemoryEntry:
        items = self.list_pending()
        target = next((item for item in items if str(item.get("id")) == entry_id), None)
        if target is None:
            raise KeyError(f"Pending memory not found: {entry_id}")
        entry = MemoryEntry.from_dict(target)
        written = self.write(entry) or entry
        remaining = [item for item in items if str(item.get("id")) != entry_id]
        self._write_pending(remaining)
        return written

    def reject_pending(self, entry_id: str) -> None:
        items = self.list_pending()
        remaining = [item for item in items if str(item.get("id")) != entry_id]
        if len(remaining) == len(items):
            raise KeyError(f"Pending memory not found: {entry_id}")
        self._write_pending(remaining)

    def migrate_v1(self, *, dry_run: bool = False) -> dict[str, object]:
        if not self.paths.whiteboard_path.exists():
            return {"migrated": 0, "topics": [], "backup": None, "dry_run": dry_run}

        try:
            payload = json.loads(self.paths.whiteboard_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid whiteboard payload: {exc}") from exc

        raw_entries = payload.get("entries", []) if isinstance(payload, dict) else []
        if not isinstance(raw_entries, list):
            raw_entries = []

        migrated_entries: list[MemoryEntry] = []
        for item in raw_entries:
            if not isinstance(item, dict):
                continue
            type_name = str(item.get("type", "fact"))
            if type_name not in MEMORY_TYPES:
                type_name = "fact"
            project = str(item.get("project", "")).strip() or None
            topic = project or str(item.get("topic", "")).strip() or type_name
            content = str(item.get("content", "")).strip() or str(item.get("text", "")).strip()
            if not content:
                continue
            migrated_entries.append(
                MemoryEntry(
                    type=type_name,
                    content=content,
                    topic=_slugify(topic),
                    project=project,
                    source=str(item.get("source", "whiteboard.json")),
                    source_session=item.get("source_session"),
                    confidence=float(item.get("confidence", 1.0)),
                    created_at=str(item.get("created_at") or item.get("created") or datetime.now(UTC).isoformat()),
                    updated_at=str(item.get("updated_at") or item.get("updated") or datetime.now(UTC).isoformat()),
                )
            )

        topics = sorted({entry.topic for entry in migrated_entries})
        backup = str(self.paths.memory_dir / "whiteboard.v1.json.bak")
        if dry_run:
            return {"migrated": len(migrated_entries), "topics": topics, "backup": backup, "dry_run": True}

        with FileLock(self.migrate_lock):
            for entry in migrated_entries:
                self.write(entry)
            backup_path = self.paths.memory_dir / "whiteboard.v1.json.bak"
            atomic_write_text(backup_path, self.paths.whiteboard_path.read_text(encoding="utf-8"))
        self.paths.whiteboard_path.unlink(missing_ok=True)
        return {"migrated": len(migrated_entries), "topics": topics, "backup": backup, "dry_run": False}

    def expire_check(self, *, older_than: str = "90d", dry_run: bool = False) -> dict[str, object]:
        cutoff = parse_since_window(older_than)
        expired: list[dict[str, object]] = []
        changed_topics: dict[str, list[MemoryEntry]] = {}

        for topic in self.store.list_topics():
            entries = self.store.read_topic(topic)
            updated_entries: list[MemoryEntry] = []
            topic_changed = False
            for entry in entries:
                if entry.type == "expired":
                    updated_entries.append(entry)
                    continue
                try:
                    updated_at = datetime.fromisoformat(entry.updated_at)
                except ValueError:
                    updated_entries.append(entry)
                    continue
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=UTC)
                else:
                    updated_at = updated_at.astimezone(UTC)
                if updated_at < cutoff:
                    expired.append(
                        {
                            "topic": topic,
                            "content": entry.content,
                            "previous_type": entry.type,
                            "updated_at": entry.updated_at,
                        }
                    )
                    if not dry_run:
                        entry.type = "expired"
                        entry.updated_at = datetime.now(UTC).isoformat()
                        topic_changed = True
                updated_entries.append(entry)
            if topic_changed:
                changed_topics[topic] = updated_entries

        if not dry_run:
            for topic, entries in changed_topics.items():
                self.store.rewrite_topic(topic, entries)

        return {
            "ok": True,
            "older_than": older_than,
            "dry_run": dry_run,
            "expired": expired,
            "updated_topics": sorted(changed_topics.keys()),
        }

    def _entries_from_payload(
        self,
        payload: list[dict[str, object]],
        *,
        project: str | None,
        agent: str | None,
        session_id: str | None,
    ) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            type_name = str(item.get("type", "")).strip()
            content = str(item.get("content", "")).strip()
            if type_name not in MEMORY_TYPES or not content:
                continue
            topic = _slugify(str(item.get("topic", "")).strip() or project or "general")
            entries.append(
                MemoryEntry(
                    type=type_name,
                    content=content,
                    topic=topic,
                    confidence=float(item.get("confidence", 0.7)),
                    source=agent or "ghost-agent",
                    source_session=session_id,
                    project=project,
                )
            )
        return entries

    def _heuristic_extract(
        self,
        messages: list[dict[str, object]],
        *,
        project: str | None,
        agent: str | None,
        session_id: str | None,
    ) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        marker_map = {
            "[decision]": "decision",
            "[fact]": "fact",
            "[learning]": "learning",
            "[preference]": "preference",
        }
        for message in messages:
            content = str(message.get("content", "")).strip()
            lowered = content.lower()
            for marker, type_name in marker_map.items():
                if marker in lowered:
                    cleaned = re.sub(rf"(?i){re.escape(marker)}", "", content).strip(" :-")
                    if not cleaned:
                        continue
                    entries.append(
                        MemoryEntry(
                            type=type_name,
                            content=cleaned,
                            topic=_slugify(project or "general"),
                            confidence=0.7,
                            source=agent or "heuristic",
                            source_session=session_id,
                            project=project,
                        )
                    )
                    break
        return entries

    def _admit_entries(self, entries: list[MemoryEntry]) -> ExtractionResult:
        auto_threshold = float(get_nested(self.config, "memory_extraction", "auto_admit_threshold", default=0.8))
        pending_threshold = float(get_nested(self.config, "memory_extraction", "pending_threshold", default=0.5))
        existing = self.store.all_entries()
        pending = self.list_pending()
        result = ExtractionResult(entries=entries)

        for entry in entries:
            normalized = MemoryEntry.from_dict({**entry.to_dict(), "topic": self.auto_topic(entry)})
            pending_entries = [MemoryEntry.from_dict(item) for item in pending]
            if self.dedup(normalized, existing) or self.dedup(normalized, pending_entries):
                result.discarded += 1
                continue
            if normalized.confidence >= auto_threshold:
                self.store.write_entry(normalized)
                existing.append(normalized)
                result.admitted += 1
                continue
            if normalized.confidence >= pending_threshold:
                pending.append(normalized.to_dict())
                result.pending += 1
                continue
            result.discarded += 1

        self._write_pending(pending)
        return result

    def _write_pending(self, items: list[dict[str, object]]) -> None:
        ensure_dir(self.pending_path.parent)
        with FileLock(self.pending_lock):
            atomic_write_json(self.pending_path, {"entries": items})

    def _append_log(self, payload: dict[str, object]) -> None:
        ensure_dir(self.paths.extraction_log_path.parent)
        with FileLock(self.log_lock):
            existing = ""
            if self.paths.extraction_log_path.exists():
                existing = self.paths.extraction_log_path.read_text(encoding="utf-8")
            existing += json.dumps(payload, ensure_ascii=False) + "\n"
            atomic_write_text(self.paths.extraction_log_path, existing)

    def _conversation_to_text(self, messages: list[dict[str, object]]) -> str:
        rendered: list[str] = []
        for index, message in enumerate(messages, start=1):
            role = str(message.get("role", "unknown")).strip() or "unknown"
            content = str(message.get("content", "")).strip()
            if content:
                rendered.append(f"{index}. {role}: {content}")
        return "\n".join(rendered)

    def _render_existing_memories(self, existing: list[MemoryEntry]) -> str:
        if not existing:
            return "[]"
        payload = [
            {
                "type": entry.type,
                "content": entry.content,
                "topic": entry.topic,
            }
            for entry in existing[-50:]
        ]
        return json.dumps(payload, ensure_ascii=False, indent=2)
