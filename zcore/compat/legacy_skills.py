from __future__ import annotations

import subprocess
from pathlib import Path

from zcore.runtime import RuntimePaths


def resolve_legacy_script(skill_name: str, script_name: str, paths: RuntimePaths | None = None) -> Path:
    runtime_paths = paths or RuntimePaths.discover()
    script_path = runtime_paths.skills_dir / skill_name / "scripts" / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"Legacy script not found: {script_path}")
    return script_path


def run_legacy_script(skill_name: str, script_name: str, *args: str, paths: RuntimePaths | None = None) -> subprocess.CompletedProcess[str]:
    script_path = resolve_legacy_script(skill_name, script_name, paths=paths)
    return subprocess.run(
        ["python3", str(script_path), *args],
        capture_output=True,
        text=True,
        check=False,
    )

