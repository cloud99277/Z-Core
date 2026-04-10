from __future__ import annotations

import os
from pathlib import Path


def runtime_home() -> Path:
    raw = os.environ.get("ZCORE_HOME") or os.environ.get("KITCLAW_HOME") or "~/.zcore"
    return Path(raw).expanduser()


def ai_memory_home() -> Path:
    raw = os.environ.get("AI_MEMORY_DIR") or "~/.ai-memory"
    return Path(raw).expanduser()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
