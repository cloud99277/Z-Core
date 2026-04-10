from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class WorkflowStep:
    name: str
    skill: str
    command: str
    args: list[str] = field(default_factory=list)
    on_failure: str = "abort"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class WorkflowDefinition:
    name: str
    description: str
    steps: list[WorkflowStep]
    source_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [step.to_dict() for step in self.steps],
            "source_path": self.source_path,
        }


@dataclass
class StepResult:
    step_name: str
    status: str
    returncode: int
    stdout_summary: str
    duration_ms: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class WorkflowResult:
    workflow_name: str
    dry_run: bool
    steps: list[StepResult]
    overall: str

    def to_dict(self) -> dict[str, object]:
        return {
            "workflow_name": self.workflow_name,
            "dry_run": self.dry_run,
            "steps": [step.to_dict() for step in self.steps],
            "overall": self.overall,
        }
