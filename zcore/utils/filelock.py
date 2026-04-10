from __future__ import annotations

import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


class FileLock:
    """Advisory file lock for CLI-safe atomic writes."""

    def __init__(self, path: str | Path, timeout: float = 5.0, poll_interval: float = 0.1):
        self.path = Path(path)
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._handle = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+", encoding="utf-8")

        if fcntl is None:  # pragma: no cover
            return

        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    self._handle.close()
                    self._handle = None
                    raise TimeoutError(f"Timed out acquiring lock: {self.path}")
                time.sleep(self.poll_interval)

    def release(self) -> None:
        if self._handle is None:
            return
        if fcntl is not None:  # pragma: no branch
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

