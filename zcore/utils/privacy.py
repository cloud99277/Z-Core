from __future__ import annotations

import re
from typing import Iterable


DEFAULT_PATTERNS = [
    r"(?i)(api[_-]?key|token|secret|password)\s*[=:]\s*\S+",
    r"sk-[a-zA-Z0-9]{20,}",
    r"AIza[a-zA-Z0-9_-]{35}",
]


def redact_text(text: str, patterns: Iterable[str] | None = None, redact_file_paths: bool = True) -> str:
    result = text
    for pattern in patterns or DEFAULT_PATTERNS:
        result = re.sub(pattern, "[REDACTED]", result)
    if redact_file_paths:
        result = re.sub(r"/home/([^/\s]+)/", "/home/[USER]/", result)
        result = re.sub(r"/Users/([^/\s]+)/", "/Users/[USER]/", result)
    return result
