from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SessionMeta:
    session_id: str
    project: str
    agent: str
    started_at: str = field(default_factory=now_iso)
    ended_at: str | None = None
    paused_at: str | None = None
    resumed_at: str | None = None
    status: str = "active"
    parent_session: str | None = None
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    token_count_start: int = 0
    token_count_end: int = 0
    tool_calls: int = 0
    compactions: int = 0
    compaction_mode: str = "none"
    memory_mode: str = "none"

    def to_dict(self) -> dict:
        return asdict(self)
