from __future__ import annotations

import hashlib
import json
from pathlib import Path

from zcore.models.knowledge_contract import (
    CorpusRegistry,
    KnowledgeContractError,
    L2AttributedItem,
    L2ProviderWarning,
    L2ReadReport,
)
from zcore.models.memory import MemoryEntry


def load_corpus_registry(path: Path) -> CorpusRegistry:
    """Load and validate an explicit registry file without accessing any corpus root."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KnowledgeContractError("invalid corpus registry") from exc
    return CorpusRegistry.from_dict(payload)


def resolve_corpus_registry_path(
    explicit_path: str | None,
    config: dict[str, object],
    *,
    base_dir: Path,
) -> Path | None:
    value = explicit_path
    if not value:
        configured = config.get("knowledge")
        if isinstance(configured, dict):
            candidate = configured.get("corpus_registry_path")
            value = candidate if isinstance(candidate, str) else None
    if not value or not value.strip():
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else base_dir / path


class TopicMarkdownL2Provider:
    """Read one explicit topic-store root without falling back to another store."""

    provider_id = "topic_markdown"

    def __init__(self, root: Path):
        self.root = root

    def read(self, *, project: str | None, query: str | None, limit: int = 3) -> L2ReadReport:
        try:
            root = self.root.resolve(strict=True)
        except OSError:
            return L2ReadReport(
                provider_id=self.provider_id,
                status="unavailable",
                warnings=(L2ProviderWarning("topic_store_missing", "topic_store"),),
            )
        if not root.is_dir():
            return L2ReadReport(
                provider_id=self.provider_id,
                status="unavailable",
                warnings=(L2ProviderWarning("topic_store_missing", "topic_store"),),
            )

        digest = hashlib.sha256()
        items: list[L2AttributedItem] = []
        warnings: list[L2ProviderWarning] = []
        needle = (query or "").casefold().strip()
        for topic_path in sorted(root.glob("*.md")):
            try:
                resolved = topic_path.resolve(strict=True)
                resolved.relative_to(root)
                content = resolved.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError, ValueError):
                warnings.append(L2ProviderWarning("topic_read_failed", "topic_file"))
                continue
            digest.update(content.encode("utf-8"))
            topic = topic_path.stem
            for number, line in enumerate(content.splitlines(), start=1):
                entry = MemoryEntry.from_markdown_line(line, topic=topic)
                if entry is None:
                    if line.strip().startswith("- ["):
                        warnings.append(L2ProviderWarning("topic_entry_invalid", f"entry{number}"))
                    continue
                if project is not None and entry.project != project:
                    continue
                if needle and needle not in entry.content.casefold() and needle not in entry.topic.casefold():
                    continue
                items.append(
                    L2AttributedItem(
                        source_id=f"l2:topic:{topic}:{entry.id}",
                        provider_id=self.provider_id,
                        entry_type=entry.type,
                        content=entry.content[:1000],
                        project=entry.project,
                    )
                )
                if len(items) >= max(0, limit):
                    break
            if len(items) >= max(0, limit):
                break
        return L2ReadReport(
            provider_id=self.provider_id,
            status="partial" if warnings else "healthy",
            items=tuple(items),
            warnings=tuple(warnings),
            source_revision=digest.hexdigest(),
        )


class WhiteboardL2Provider:
    """Read one explicit legacy whiteboard file without topic-store fallback."""

    provider_id = "legacy_whiteboard"

    def __init__(self, path: Path):
        self.path = path

    def read(self, *, project: str | None, query: str | None, limit: int = 3) -> L2ReadReport:
        try:
            raw = self.path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except FileNotFoundError:
            return L2ReadReport(
                provider_id=self.provider_id,
                status="unavailable",
                warnings=(L2ProviderWarning("whiteboard_missing", "whiteboard"),),
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return L2ReadReport(
                provider_id=self.provider_id,
                status="failed",
                warnings=(L2ProviderWarning("whiteboard_invalid", "whiteboard"),),
            )
        if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
            return L2ReadReport(
                provider_id=self.provider_id,
                status="failed",
                warnings=(L2ProviderWarning("whiteboard_invalid", "whiteboard"),),
                source_revision=hashlib.sha256(raw).hexdigest(),
            )

        items: list[L2AttributedItem] = []
        warnings: list[L2ProviderWarning] = []
        needle = (query or "").casefold().strip()
        for index, entry in enumerate(payload["entries"], start=1):
            if not isinstance(entry, dict):
                warnings.append(L2ProviderWarning("whiteboard_entry_invalid", f"entry{index}"))
                continue
            content = entry.get("content")
            entry_type = entry.get("type")
            entry_project = entry.get("project")
            if not isinstance(content, str) or not content.strip() or not isinstance(entry_type, str) or not entry_type.strip():
                warnings.append(L2ProviderWarning("whiteboard_entry_invalid", f"entry{index}"))
                continue
            if entry_project is not None and not isinstance(entry_project, str):
                warnings.append(L2ProviderWarning("whiteboard_entry_invalid", f"entry{index}"))
                continue
            if project is not None and entry_project != project:
                continue
            if needle and needle not in content.casefold():
                continue
            source_seed = str(entry.get("id") or index).encode("utf-8")
            source_id = hashlib.sha256(source_seed).hexdigest()[:16]
            items.append(
                L2AttributedItem(
                    source_id=f"l2:whiteboard:{source_id}",
                    provider_id=self.provider_id,
                    entry_type=entry_type.strip(),
                    content=content.strip()[:1000],
                    project=entry_project,
                )
            )
            if len(items) >= max(0, limit):
                break
        return L2ReadReport(
            provider_id=self.provider_id,
            status="partial" if warnings else "healthy",
            items=tuple(items),
            warnings=tuple(warnings),
            source_revision=hashlib.sha256(raw).hexdigest(),
        )
