from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zcore.engines.governance import PermissionEngine, classify_shell_command
from zcore.engines.observability import ObservabilityEngine
from zcore.models.skill import SkillManifest
from zcore.runtime import RuntimePaths


@dataclass
class HookExecutionContext:
    runtime_paths: RuntimePaths
    manifest: SkillManifest
    args: dict[str, Any]
    session_id: str | None
    project: str | None
    execution_status: str | None = None
    execution_output: str | None = None
    duration_ms: int | None = None


@dataclass
class BuiltinHookResponse:
    status: str
    message: str = ""


def validate_input(context: HookExecutionContext) -> BuiltinHookResponse:
    required = [field.type for field in context.manifest.io.input if field.type]
    if not required:
        return BuiltinHookResponse(status="pass", message="no required input schema")
    if not context.args:
        return BuiltinHookResponse(status="fail", message="skill arguments are required")
    return BuiltinHookResponse(status="pass", message="input present")


def check_permissions(context: HookExecutionContext) -> BuiltinHookResponse:
    engine = PermissionEngine(context.runtime_paths, project_root=context.project)
    targets: list[tuple[str, str]] = []
    for path in context.manifest.permissions.reads:
        targets.append(("file.read", path))
    for path in context.manifest.permissions.writes:
        targets.append(("file.write", path))
    if context.manifest.permissions.shell:
        shell_target = str(context.args.get("shell_command", "skill shell execution"))
        targets.append(("shell", shell_target))
    if context.manifest.permissions.network:
        targets.append(("network", context.manifest.name))
    targets.append(("skill.run", context.manifest.name))

    for action, target in targets:
        decision = engine.check(action, target)
        if not decision.allowed:
            return BuiltinHookResponse(status="fail", message=decision.reason)
        # Defense-in-depth: even if PermissionEngine allowed (e.g. yolo mode),
        # still block dangerous shell commands at the hook layer.
        if action == "shell":
            classification = classify_shell_command(target)
            if classification == "dangerous":
                return BuiltinHookResponse(status="fail", message=f"dangerous shell command: {target}")
    return BuiltinHookResponse(status="pass", message="permissions granted")


def log_execution(context: HookExecutionContext) -> BuiltinHookResponse:
    engine = ObservabilityEngine(context.runtime_paths)
    payload = engine.log_execution(
        context.manifest.name,
        context.execution_status,
        context.duration_ms,
        session_id=context.session_id,
        project=context.project,
        output=context.execution_output,
    )
    log_path = context.runtime_paths.logs_dir / "executions.jsonl"
    return BuiltinHookResponse(status="pass", message=f"logged to {log_path}")


BUILTIN_HOOKS = {
    "validate-input": validate_input,
    "validate_input": validate_input,
    "check-permissions": check_permissions,
    "check_permissions": check_permissions,
    "log-execution": log_execution,
    "log_execution": log_execution,
}
