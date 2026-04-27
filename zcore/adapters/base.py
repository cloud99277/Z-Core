from __future__ import annotations

from abc import ABC, abstractmethod

from zcore.models.harvester import HarvestedSession


class SourceAdapter(ABC):
    @abstractmethod
    def name(self) -> str:
        """Return the stable source name."""

    @abstractmethod
    def discover(self, project: str | None = None) -> list[dict[str, object]]:
        """Return candidate source sessions."""

    @abstractmethod
    def ingest(self, session_id: str) -> HarvestedSession | None:
        """Load one source session by source-specific session id."""

    @abstractmethod
    def health_check(self) -> dict[str, object]:
        """Return adapter health details."""
