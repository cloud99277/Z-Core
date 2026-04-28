from __future__ import annotations

import re
from copy import deepcopy
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable


DEFAULT_PATTERNS = [
    r"(?i)(api[_-]?key|token|secret|password)\s*[=:]\s*\S+",
    r"sk-[a-zA-Z0-9]{18,}",
    r"AIza[a-zA-Z0-9_-]{35}",
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    r"\b1[3-9]\d{9}\b",
    r"AKIA[0-9A-Z]{16}",
    r"Bearer\s+[A-Za-z0-9\-._~+/]+=*",
]


def redact_text(text: str, patterns: Iterable[str] | None = None, redact_file_paths: bool = True) -> str:
    result = text
    for pattern in patterns or DEFAULT_PATTERNS:
        result = re.sub(pattern, "[REDACTED]", result)
    if redact_file_paths:
        result = re.sub(r"/home/([^/\s]+)/", "/home/[USER]/", result)
        result = re.sub(r"/Users/([^/\s]+)/", "/Users/[USER]/", result)
    return result


def sanitize_transcript(
    messages: list[dict[str, str]],
    *,
    patterns: Iterable[str] | None = None,
    redact_file_paths: bool = True,
) -> list[dict[str, str]]:
    """Redact message contents without mutating the source transcript."""
    sanitized = deepcopy(messages)
    for message in sanitized:
        if "content" in message:
            message["content"] = redact_text(
                str(message["content"]),
                patterns=patterns,
                redact_file_paths=redact_file_paths,
            )
    return sanitized


def load_ingest_ignore(path: Path) -> list[str]:
    """Read an ingest-ignore file into glob patterns."""
    if not path.exists():
        return []
    patterns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        pattern = line.strip()
        if not pattern or pattern.startswith("#"):
            continue
        patterns.append(pattern)
    return patterns


def should_ignore(session_path: str, patterns: list[str]) -> bool:
    """Return whether a session path matches any ingest-ignore glob pattern."""
    return any(fnmatch(session_path, pattern) for pattern in patterns)
