from __future__ import annotations

import shlex
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from zcore.engines.router import SkillRouter
from zcore.models.workflow import StepResult, WorkflowDefinition, WorkflowResult, WorkflowStep
from zcore.runtime import RuntimePaths


class WorkflowEngine:
    def __init__(self, paths: RuntimePaths | None = None, *, cwd: Path | None = None):
        self.paths = paths or RuntimePaths.discover()
        self.cwd = (cwd or Path.cwd()).resolve()
        self.router = SkillRouter(self.paths)

    def discover_workflows(self) -> list[WorkflowDefinition]:
        workflows: list[WorkflowDefinition] = []
        seen: set[Path] = set()
        for base in self._workflow_roots():
            if not base.exists():
                continue
            for path in sorted(base.glob("*.toml")):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                workflows.append(self._parse_workflow_file(path))
        return sorted(workflows, key=lambda item: item.name)

    def load_workflow(self, name_or_file: str) -> WorkflowDefinition:
        candidate = Path(name_or_file).expanduser()
        if candidate.exists():
            return self._parse_workflow_file(candidate)

        for workflow in self.discover_workflows():
            if workflow.name == name_or_file or Path(workflow.source_path).stem == name_or_file:
                return workflow
        raise FileNotFoundError(f"Workflow not found: {name_or_file}")

    def validate_workflow(self, name_or_file: str) -> dict[str, object]:
        checks: list[dict[str, str]] = []
        workflow: WorkflowDefinition | None = None
        try:
            workflow = self.load_workflow(name_or_file)
        except Exception as exc:
            checks.append({"status": "ERROR", "check": "workflow.load", "message": str(exc)})
            return {"ok": False, "workflow": None, "checks": checks}

        checks.append({"status": "PASS", "check": "workflow.load", "message": workflow.source_path})
        if workflow.steps:
            checks.append({"status": "PASS", "check": "workflow.steps", "message": str(len(workflow.steps))})
        else:
            checks.append({"status": "ERROR", "check": "workflow.steps", "message": "workflow must define at least one step"})

        skills = {manifest.name for manifest in self.router.discover()}
        for step in workflow.steps:
            if step.skill in skills:
                checks.append({"status": "PASS", "check": f"skill:{step.name}", "message": step.skill})
            else:
                checks.append({"status": "ERROR", "check": f"skill:{step.name}", "message": f"missing skill: {step.skill}"})
            if step.on_failure in {"abort", "continue"}:
                checks.append({"status": "PASS", "check": f"on_failure:{step.name}", "message": step.on_failure})
            else:
                checks.append(
                    {
                        "status": "ERROR",
                        "check": f"on_failure:{step.name}",
                        "message": f"unsupported on_failure: {step.on_failure}",
                    }
                )

        ok = all(item["status"] != "ERROR" for item in checks)
        return {"ok": ok, "workflow": workflow.to_dict() if workflow else None, "checks": checks}

    def run_workflow(self, name_or_file: str, *, dry_run: bool = False) -> WorkflowResult:
        validation = self.validate_workflow(name_or_file)
        if not validation["ok"]:
            raise ValueError(f"Workflow validation failed: {name_or_file}")

        workflow = WorkflowDefinition(
            name=str(validation["workflow"]["name"]),
            description=str(validation["workflow"]["description"]),
            source_path=str(validation["workflow"]["source_path"]),
            steps=[WorkflowStep(**step) for step in validation["workflow"]["steps"]],
        )

        results: list[StepResult] = []
        overall = "ok"

        for index, step in enumerate(workflow.steps):
            command = [sys.executable, "-m", "zcore", *shlex.split(step.command), *step.args]
            if dry_run:
                results.append(
                    StepResult(
                        step_name=step.name,
                        status="ok",
                        returncode=0,
                        stdout_summary=" ".join(command),
                        duration_ms=0,
                    )
                )
                continue

            started = time.perf_counter()
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                cwd=str(self.cwd),
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            summary = (completed.stdout.strip() or completed.stderr.strip())[:500]
            status = "ok" if completed.returncode == 0 else "error"
            results.append(
                StepResult(
                    step_name=step.name,
                    status=status,
                    returncode=completed.returncode,
                    stdout_summary=summary,
                    duration_ms=duration_ms,
                )
            )
            if completed.returncode != 0:
                overall = "failed" if step.on_failure == "abort" else "partial"
                if step.on_failure == "abort":
                    for remaining in workflow.steps[index + 1 :]:
                        results.append(
                            StepResult(
                                step_name=remaining.name,
                                status="skipped",
                                returncode=-1,
                                stdout_summary="skipped after abort",
                                duration_ms=0,
                            )
                        )
                    break

        if not dry_run and overall == "ok" and any(item.status == "error" for item in results):
            overall = "partial"
        return WorkflowResult(workflow_name=workflow.name, dry_run=dry_run, steps=results, overall=overall)

    def _workflow_roots(self) -> list[Path]:
        return [
            self.paths.workflows_dir,
            self.cwd / ".zcore" / "workflows",
        ]

    def _parse_workflow_file(self, path: Path) -> WorkflowDefinition:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)

        workflow_data = payload.get("workflow")
        if not isinstance(workflow_data, dict):
            raise ValueError(f"workflow table missing in {path}")

        name = str(workflow_data.get("name", "")).strip() or path.stem
        description = str(workflow_data.get("description", "")).strip()
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError(f"steps array missing in {path}")

        steps: list[WorkflowStep] = []
        for index, raw_step in enumerate(raw_steps, start=1):
            if not isinstance(raw_step, dict):
                raise ValueError(f"invalid step #{index} in {path}")
            step_name = str(raw_step.get("name", "")).strip() or f"step-{index}"
            skill = str(raw_step.get("skill", "")).strip()
            command = str(raw_step.get("command", "")).strip()
            args = raw_step.get("args", [])
            on_failure = str(raw_step.get("on_failure", "abort")).strip() or "abort"
            if not skill or not command:
                raise ValueError(f"step {step_name} must define skill and command")
            if not isinstance(args, list):
                raise ValueError(f"step {step_name} args must be a list")
            steps.append(
                WorkflowStep(
                    name=step_name,
                    skill=skill,
                    command=command,
                    args=[str(item) for item in args],
                    on_failure=on_failure,
                )
            )
        return WorkflowDefinition(name=name, description=description, steps=steps, source_path=str(path.resolve()))
