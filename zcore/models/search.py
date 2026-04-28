from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class SearchHit:
    source: str
    session_id: str
    project: str
    started_at: str
    snippet: str
    score: float = 1.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class SearchResult:
    query: str
    total_hits: int
    hits: list[SearchHit] = field(default_factory=list)
    searched_sessions: int = 0
    searched_harvested: int = 0
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
