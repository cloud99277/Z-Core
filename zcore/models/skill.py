from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from zcore.utils.frontmatter import parse_frontmatter


@dataclass
class ActivationContext:
    min_tokens: int | None = None
    max_tokens: int | None = None
    project_types: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ActivationContext":
        payload = data or {}
        return cls(
            min_tokens=_coerce_int(payload.get("min_tokens")),
            max_tokens=_coerce_int(payload.get("max_tokens")),
            project_types=_coerce_list(payload.get("project_types")),
        )


@dataclass
class ActivationConfig:
    triggers: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    context: ActivationContext = field(default_factory=ActivationContext)
    effort: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ActivationConfig":
        payload = data or {}
        return cls(
            triggers=_coerce_list(payload.get("triggers")),
            paths=_coerce_list(payload.get("paths")),
            context=ActivationContext.from_dict(_coerce_dict(payload.get("context"))),
            effort=_coerce_str(payload.get("effort")),
        )


@dataclass
class DependencyConfig:
    required: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DependencyConfig":
        payload = data or {}
        return cls(
            required=_coerce_list(payload.get("required")),
            optional=_coerce_list(payload.get("optional")),
        )


@dataclass
class LifecycleConfig:
    pre_execute: list[str] = field(default_factory=list)
    post_execute: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "LifecycleConfig":
        payload = data or {}
        return cls(
            pre_execute=_coerce_list(payload.get("pre_execute")),
            post_execute=_coerce_list(payload.get("post_execute")),
        )


@dataclass
class PermissionConfig:
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    shell: bool = False
    network: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PermissionConfig":
        payload = data or {}
        return cls(
            reads=_coerce_list(payload.get("reads")),
            writes=_coerce_list(payload.get("writes")),
            shell=bool(payload.get("shell", False)),
            network=bool(payload.get("network", False)),
        )


@dataclass
class IOField:
    type: str = ""
    description: str = ""
    schema: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "IOField":
        payload = data or {}
        return cls(
            type=_coerce_str(payload.get("type"), ""),
            description=_coerce_str(payload.get("description"), ""),
            schema=_coerce_str(payload.get("schema")),
        )


@dataclass
class IOConfig:
    input: list[IOField] = field(default_factory=list)
    output: list[IOField] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "IOConfig":
        payload = data or {}
        return cls(
            input=[IOField.from_dict(item) for item in _coerce_list_of_dicts(payload.get("input"))],
            output=[IOField.from_dict(item) for item in _coerce_list_of_dicts(payload.get("output"))],
        )


@dataclass
class SkillManifest:
    name: str
    version: str = ""
    description: str = ""
    scripts: list[str] = field(default_factory=list)
    activation: ActivationConfig = field(default_factory=ActivationConfig)
    dependencies: DependencyConfig = field(default_factory=DependencyConfig)
    lifecycle: LifecycleConfig = field(default_factory=LifecycleConfig)
    permissions: PermissionConfig = field(default_factory=PermissionConfig)
    io: IOConfig = field(default_factory=IOConfig)
    source_path: str = ""
    source_type: str = "core"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillManifest":
        payload = dict(data)
        return cls(
            name=_coerce_str(payload.get("name"), ""),
            version=_coerce_str(payload.get("version"), ""),
            description=_coerce_str(payload.get("description"), ""),
            scripts=_coerce_list(payload.get("scripts")),
            activation=ActivationConfig.from_dict(_coerce_dict(payload.get("activation"))),
            dependencies=DependencyConfig.from_dict(_coerce_dict(payload.get("dependencies"))),
            lifecycle=LifecycleConfig.from_dict(_coerce_dict(payload.get("lifecycle"))),
            permissions=PermissionConfig.from_dict(_coerce_dict(payload.get("permissions"))),
            io=IOConfig.from_dict(_coerce_dict(payload.get("io"))),
            source_path=_coerce_str(payload.get("source_path"), ""),
            source_type=_coerce_str(payload.get("source_type"), "core"),
            warnings=_coerce_list(payload.get("warnings")),
        )

    @classmethod
    def from_skill_md(cls, path: Path, *, source_type: str | None = None) -> "SkillManifest":
        text = path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)
        name = _coerce_str(frontmatter.get("name"), "")
        if not name:
            raise ValueError(f"Skill frontmatter missing required field 'name': {path}")

        warnings: list[str] = []
        description = _coerce_str(frontmatter.get("description"), "")
        if not description:
            warnings.append("description missing; using empty string")

        scripts = _discover_scripts(path.parent)
        payload = {
            "name": name,
            "version": _coerce_str(frontmatter.get("version"), ""),
            "description": description,
            "scripts": scripts,
            "activation": _normalize_activation(frontmatter),
            "dependencies": _coerce_dict(frontmatter.get("dependencies")),
            "lifecycle": _coerce_dict(frontmatter.get("lifecycle")),
            "permissions": _coerce_dict(frontmatter.get("permissions")),
            "io": _coerce_dict(frontmatter.get("io")),
            "source_path": str(path),
            "source_type": source_type or _infer_source_type(path),
            "warnings": warnings,
        }
        manifest = cls.from_dict(payload)
        if not manifest.lifecycle.post_execute:
            manifest.lifecycle.post_execute.append("log-execution")
        return manifest


def _normalize_activation(frontmatter: dict[str, Any]) -> dict[str, Any]:
    activation = _coerce_dict(frontmatter.get("activation"))
    if not activation:
        activation = {}
    if "triggers" not in activation and "triggers" in frontmatter:
        activation["triggers"] = frontmatter.get("triggers")
    return activation


def _discover_scripts(skill_dir: Path) -> list[str]:
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.exists():
        return []
    return sorted(str(path) for path in scripts_dir.glob("*.py"))


def _infer_source_type(path: Path) -> str:
    expanded = path.expanduser().resolve()
    skills_home = Path.home().expanduser() / ".ai-skills"
    if skills_home in expanded.parents:
        return "core"
    if ".skills" in expanded.parts:
        return "project"
    return "ecosystem"


def _coerce_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _coerce_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _coerce_str(value: Any, default: str | None = None) -> str | None:
    if value is None:
        return default
    return str(value)


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except ValueError:
        return None
