from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_text(path: Path, content: str, mode: int | None = None) -> None:
    ensure_dir(path.parent)
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        if mode is not None:
            os.chmod(path, mode)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def atomic_write_json(path: Path, data: Any, mode: int | None = None) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n", mode=mode)
