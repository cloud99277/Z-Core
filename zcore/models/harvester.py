from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class HarvestedSession:
    source: str
    source_session_id: str
    project: str
    started_at: str
    ended_at: str | None = None
    messages: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class HarvestResult:
    source: str
    discovered: int
    ingested: int
    skipped: int
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
