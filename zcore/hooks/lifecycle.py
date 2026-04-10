from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zcore.hooks.builtin import BUILTIN_HOOKS, BuiltinHookResponse, HookExecutionContext
from zcore.models.skill import SkillManifest
from zcore.runtime import RuntimePaths


@dataclass
class HookResult:
    hook_name: str
    status: str
    message: str
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "hook_name": self.hook_name,
            "status": self.status,
            "message": self.message,
            "duration_ms": self.duration_ms,
        }


class HookRunner:
    def __init__(self, runtime_paths: RuntimePaths):
        self.runtime_paths = runtime_paths

    def load_hooks(self, names: list[str], *, phase: str) -> list[tuple[str, Any]]:
        hooks: list[tuple[str, Any]] = []
        for name in names:
            hook = BUILTIN_HOOKS.get(name)
            if hook is not None:
                hooks.append((name, hook))
        hooks.extend(self._load_custom_hooks(phase))
        return hooks

    def execute_chain(
        self,
        names: list[str],
        *,
        manifest: SkillManifest,
        args: dict[str, Any],
        session_id: str | None,
        project: str | None,
        phase: str,
        execution_status: str | None = None,
        execution_output: str | None = None,
        duration_ms: int | None = None,
    ) -> tuple[bool, list[HookResult]]:
        context = HookExecutionContext(
            runtime_paths=self.runtime_paths,
            manifest=manifest,
            args=args,
            session_id=session_id,
            project=project,
            execution_status=execution_status,
            execution_output=execution_output,
            duration_ms=duration_ms,
        )
        results: list[HookResult] = []
        for hook_name, hook in self.load_hooks(names, phase=phase):
            started = time.perf_counter()
            response = hook(context)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            result = HookResult(
                hook_name=hook_name,
                status=response.status,
                message=response.message,
                duration_ms=elapsed_ms,
            )
            results.append(result)
            if phase == "pre" and response.status == "fail":
                return False, results
        return True, results

    def _load_custom_hooks(self, phase: str) -> list[tuple[str, Any]]:
        hook_dir = self.runtime_paths.pre_hooks_dir if phase == "pre" else self.runtime_paths.post_hooks_dir
        if not hook_dir.exists():
            return []
        hooks: list[tuple[str, Any]] = []
        for path in sorted(hook_dir.iterdir(), key=lambda item: item.name):
            if path.suffix not in {".py", ".sh"} or not path.is_file():
                continue
            hooks.append((path.name, self._script_hook(path)))
        return hooks

    def _script_hook(self, path: Path):
        def run(context: HookExecutionContext) -> BuiltinHookResponse:
            env = os.environ.copy()
            env.update(
                {
                    "ZCORE_SKILL_NAME": context.manifest.name,
                    "ZCORE_SESSION_ID": context.session_id or "",
                    "ZCORE_PROJECT": context.project or "",
                }
            )
            command = ["python3", str(path)] if path.suffix == ".py" else ["bash", str(path)]
            completed = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
            message = completed.stdout.strip() or completed.stderr.strip()
            if completed.returncode == 0:
                return BuiltinHookResponse(status="pass", message=message)
            return BuiltinHookResponse(status="fail", message=message or f"hook failed: {path.name}")

        return run
