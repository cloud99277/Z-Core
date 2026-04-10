from __future__ import annotations

from datetime import UTC, datetime, timedelta


def parse_since_window(since: str, *, now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    if since.endswith("d"):
        return current - timedelta(days=int(since[:-1] or "0"))
    if since.endswith("h"):
        return current - timedelta(hours=int(since[:-1] or "0"))
    if since.endswith("w"):
        return current - timedelta(weeks=int(since[:-1] or "0"))
    if since.endswith("m"):
        return current - timedelta(days=int(since[:-1] or "0") * 30)
    raise ValueError(f"Unsupported time window: {since}. Use d/h/w/m suffix.")
