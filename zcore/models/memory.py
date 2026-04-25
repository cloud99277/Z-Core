from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Literal


MemoryType = Literal["preference", "fact", "learning", "decision", "expired"]
MEMORY_TYPES: tuple[MemoryType, ...] = ("preference", "fact", "learning", "decision", "expired")

_MARKDOWN_RE = re.compile(
    r"^- \[(?P<type>preference|fact|learning|decision|expired)\] "
    r"(?P<content>.+?) "
    r"\(source: (?P<source>.*?), confidence: (?P<confidence>\d+(?:\.\d+)?), date: (?P<date>\d{4}-\d{2}-\d{2})\)$"
)
_STRUCTURED_RE = re.compile(r"\s+<!-- zcore:(?P<payload>[A-Za-z0-9_\-=]+) -->$")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class MemoryEntry:
    type: MemoryType
    content: str
    topic: str
    confidence: float = 1.0
    source: str = "unknown"
    source_session: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    project: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __post_init__(self) -> None:
        if self.type not in MEMORY_TYPES:
            raise ValueError(f"Unsupported memory type: {self.type}")
        self.content = self.content.strip()
        self.topic = self.topic.strip()
        self.source = self.source.strip() or "unknown"
        if not self.content:
            raise ValueError("Memory content must not be empty")
        if not self.topic:
            raise ValueError("Memory topic must not be empty")
        self.confidence = max(0.0, min(float(self.confidence), 1.0))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "MemoryEntry":
        payload = dict(data)
        payload.setdefault("source", "unknown")
        payload.setdefault("confidence", 1.0)
        payload.setdefault("topic", "general")
        return cls(**payload)

    def to_markdown_line(self) -> str:
        date_value = self.created_at[:10]
        content = " ".join(self.content.split())
        source = " ".join(self.source.split()) or "unknown"
        payload = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
        return (
            f"- [{self.type}] {content} "
            f"(source: {source}, confidence: {self.confidence:.2f}, date: {date_value}) "
            f"<!-- zcore:{encoded} -->"
        )

    @classmethod
    def from_markdown_line(cls, line: str, *, topic: str) -> "MemoryEntry | None":
        stripped = line.strip()
        structured_match = _STRUCTURED_RE.search(stripped)
        if structured_match:
            encoded = structured_match.group("payload")
            try:
                payload = json.loads(base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8"))
            except (ValueError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict):
                payload.setdefault("topic", topic)
                return cls.from_dict(payload)
            stripped = _STRUCTURED_RE.sub("", stripped)

        match = _MARKDOWN_RE.match(stripped)
        if not match:
            return None
        created_at = f"{match.group('date')}T00:00:00+00:00"
        return cls(
            type=match.group("type"),
            content=match.group("content"),
            topic=topic,
            source=match.group("source"),
            confidence=float(match.group("confidence")),
            created_at=created_at,
            updated_at=created_at,
        )
