"""Shared test helpers for zcore tests."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_zcore(*args: str, home: Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run ``python3 -m zcore`` in an isolated environment."""
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["ZCORE_HOME"] = str(home / ".zcore")
    env["AI_MEMORY_DIR"] = str(home / ".ai-memory")
    env["AI_SKILLS_DIR"] = str(home / ".ai-skills")
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-m", "zcore", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd or ROOT,
        env=env,
    )


class TestHome:
    """Context manager providing an isolated home directory with optional workspace."""

    __test__ = False

    ENV_KEYS = (
        "HOME",
        "ZCORE_HOME",
        "KITCLAW_HOME",
        "AI_MEMORY_DIR",
        "AI_SKILLS_DIR",
        "ZCORE_KNOWLEDGE_DB",
        "KITCLAW_LLM_API_KEY",
        "ZCORE_LLM_API_KEY",
    )

    def __init__(self, *, with_workspace: bool = False):
        self._with_workspace = with_workspace

    def __enter__(self) -> "TestHome":
        self._previous_env = {key: os.environ.get(key) for key in self.ENV_KEYS}
        self._tempdir = tempfile.TemporaryDirectory()
        root = Path(self._tempdir.name)
        self.home = root / "home"
        self.home.mkdir()
        if self._with_workspace:
            self.workspace = root / "workspace"
            self.workspace.mkdir()
        else:
            self.workspace = self.home
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for key, value in self._previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tempdir.cleanup()


class pushd:
    """Context manager to temporarily change the working directory."""

    def __init__(self, path: Path):
        self.path = path
        self.previous = Path.cwd()

    def __enter__(self):
        os.chdir(self.path)

    def __exit__(self, exc_type, exc, tb) -> None:
        os.chdir(self.previous)
