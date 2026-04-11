from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zcore.hooks.lifecycle import HookRunner
from zcore.models.skill import SkillManifest
from zcore.paths import repo_root
from zcore.runtime import RuntimePaths


def _bundled_skills_dir() -> Path:
    """Return the path to skills/core/ bundled with the Z-Core repo."""
    return repo_root() / "skills" / "core"


@dataclass
class SkillMatch:
    manifest: SkillManifest
    score: float
    match_layer: int
    match_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "score": self.score,
            "match_layer": self.match_layer,
            "match_reason": self.match_reason,
        }


@dataclass
class SkillResult:
    skill_name: str
    status: str
    output: str
    duration_ms: int
    hooks_log: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "status": self.status,
            "output": self.output,
            "duration_ms": self.duration_ms,
            "hooks_log": self.hooks_log,
        }


class SkillRouter:
    def __init__(self, runtime_paths: RuntimePaths):
        self.runtime_paths = runtime_paths
        self._cache: list[SkillManifest] | None = None

    def discover(self, search_paths: list[str] | None = None) -> list[SkillManifest]:
        manifests: list[SkillManifest] = []
        for base in self._normalized_search_paths(search_paths):
            if not base.exists():
                continue
            for skill_md in sorted(base.glob("*/SKILL.md")):
                try:
                    manifests.append(SkillManifest.from_skill_md(skill_md, source_type=self._source_type_for(base)))
                except Exception as exc:
                    # Gracefully degrade: include a minimal manifest with a warning
                    # instead of crashing the entire discover flow.
                    manifests.append(
                        SkillManifest(
                            name=skill_md.parent.name,
                            source_path=str(skill_md),
                            source_type=self._source_type_for(base),
                            warnings=[f"frontmatter parse error: {exc}"],
                        )
                    )
        self._cache = manifests
        return manifests

    def match(
        self,
        query: str,
        *,
        file_paths: list[str] | None = None,
        token_count: int | None = None,
        project: str | None = None,
    ) -> list[SkillMatch]:
        manifests = self._cache or self.discover()
        query_tokens = _tokenize(query)
        project_lower = (project or "").strip().lower()
        matches: list[SkillMatch] = []
        for manifest in manifests:
            layer1_score = _keyword_score(query_tokens, manifest)
            if layer1_score > 0:
                matches.append(
                    SkillMatch(
                        manifest=manifest,
                        score=layer1_score,
                        match_layer=1,
                        match_reason="keyword overlap in description/triggers",
                    )
                )
                continue
            path_score = _path_score(file_paths or [], manifest.activation.paths)
            if path_score > 0:
                matches.append(
                    SkillMatch(
                        manifest=manifest,
                        score=path_score,
                        match_layer=2,
                        match_reason="activation.paths matched current files",
                    )
                )
                continue
            context_score, context_reason = _context_score(token_count, project_lower, manifest)
            if context_score > 0:
                matches.append(
                    SkillMatch(
                        manifest=manifest,
                        score=context_score,
                        match_layer=3,
                        match_reason=context_reason,
                    )
                )
        return sorted(matches, key=lambda item: (-item.score, item.match_layer, item.manifest.name))

    def activate_conditional(self, file_paths: list[str], cwd: str) -> list[str]:
        manifests = self._cache or self.discover()
        activated: list[str] = []
        for manifest in manifests:
            for file_path in file_paths:
                rel_path = _relative_path(file_path, cwd)
                if any(fnmatch.fnmatch(rel_path, pattern) for pattern in manifest.activation.paths):
                    activated.append(manifest.name)
                    break
        return activated

    def execute(self, skill_name: str, args: dict[str, Any], *, session_id: str | None = None) -> SkillResult:
        manifests = self._cache or self.discover()
        manifest = next((item for item in manifests if item.name == skill_name), None)
        if manifest is None:
            raise ValueError(f"Unknown skill: {skill_name}")

        self.runtime_paths.ensure_runtime_dirs()
        hook_runner = HookRunner(self.runtime_paths)
        project = args.get("project") or str(repo_root())

        ok, pre_results = hook_runner.execute_chain(
            manifest.lifecycle.pre_execute,
            manifest=manifest,
            args=args,
            session_id=session_id,
            project=project,
            phase="pre",
        )
        if not ok:
            return SkillResult(
                skill_name=manifest.name,
                status="blocked",
                output=pre_results[-1].message if pre_results else "pre-hook blocked execution",
                duration_ms=0,
                hooks_log=[item.to_dict() for item in pre_results],
            )

        script_path = _resolve_script(manifest, args)
        if script_path is None:
            raise ValueError(f"Skill {skill_name} has no runnable script")

        command = ["python3", str(script_path)]
        command.extend(_args_to_cli(args))
        started = time.perf_counter()
        completed = subprocess.run(command, capture_output=True, text=True, timeout=int(args.get("timeout", 30)))
        duration_ms = int((time.perf_counter() - started) * 1000)
        status = "ok" if completed.returncode == 0 else "error"
        output = completed.stdout.strip() or completed.stderr.strip()

        _, post_results = hook_runner.execute_chain(
            manifest.lifecycle.post_execute,
            manifest=manifest,
            args=args,
            session_id=session_id or str(uuid.uuid4()),
            project=project,
            phase="post",
            execution_status=status,
            execution_output=output,
            duration_ms=duration_ms,
        )
        return SkillResult(
            skill_name=manifest.name,
            status=status,
            output=output,
            duration_ms=duration_ms,
            hooks_log=[item.to_dict() for item in [*pre_results, *post_results]],
        )

    def _normalized_search_paths(self, search_paths: list[str] | None) -> list[Path]:
        if search_paths:
            return [Path(path).expanduser() for path in search_paths]
        return [self.runtime_paths.skills_dir, repo_root() / ".skills"]

    def _source_type_for(self, base: Path) -> str:
        if base == self.runtime_paths.skills_dir:
            return "core"
        if base.name == ".skills":
            return "project"
        return "ecosystem"

    def get_skill_info(self, skill_name: str) -> SkillManifest:
        manifests = self._cache or self.discover()
        manifest = next((item for item in manifests if item.name == skill_name), None)
        if manifest is None:
            raise ValueError(f"Unknown skill: {skill_name}")
        return manifest

    def list_available(self) -> list[dict[str, Any]]:
        """List core skills bundled with Z-Core that are not yet installed."""
        bundled = _bundled_skills_dir()
        if not bundled.exists():
            return []
        installed_names = {m.name for m in self.discover()}
        available: list[dict[str, Any]] = []
        for skill_md in sorted(bundled.glob("*/SKILL.md")):
            try:
                manifest = SkillManifest.from_skill_md(skill_md, source_type="bundled")
            except Exception:
                manifest = SkillManifest(
                    name=skill_md.parent.name,
                    source_path=str(skill_md),
                    source_type="bundled",
                )
            status = "installed" if manifest.name in installed_names else "available"
            available.append({
                "name": manifest.name,
                "description": manifest.description,
                "source_path": str(skill_md.parent),
                "status": status,
            })
        return available

    def install_core_skills(self, *, force: bool = False) -> dict[str, Any]:
        """Install all bundled core skills from skills/core/ into ~/.ai-skills/."""
        bundled = _bundled_skills_dir()
        if not bundled.exists():
            raise FileNotFoundError(f"Bundled skills directory not found: {bundled}")
        results: list[dict[str, Any]] = []
        for skill_dir in sorted(bundled.iterdir()):
            if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
                continue
            try:
                result = self.install_skill(str(skill_dir), force=force)
                results.append({"name": result["name"], "status": "installed"})
            except FileExistsError:
                results.append({"name": skill_dir.name, "status": "already_installed"})
            except Exception as exc:
                results.append({"name": skill_dir.name, "status": "error", "error": str(exc)})
        installed = sum(1 for r in results if r["status"] == "installed")
        skipped = sum(1 for r in results if r["status"] == "already_installed")
        errors = sum(1 for r in results if r["status"] == "error")
        return {
            "ok": errors == 0,
            "total": len(results),
            "installed": installed,
            "skipped": skipped,
            "errors": errors,
            "results": results,
        }

    def uninstall_skill(self, skill_name: str) -> dict[str, Any]:
        """Remove an installed skill from ~/.ai-skills/."""
        target = self.runtime_paths.skills_dir / skill_name
        if not target.exists():
            raise FileNotFoundError(f"Skill not installed: {skill_name}")
        shutil.rmtree(target)
        self._cache = None
        return {
            "ok": True,
            "name": skill_name,
            "removed_path": str(target),
        }

    def install_skill(self, source: str, *, name: str | None = None, force: bool = False) -> dict[str, Any]:
        self.runtime_paths.ensure_runtime_dirs()
        source_path = Path(source).expanduser()
        target_name = name or self._infer_skill_name(source_path, source)
        target_dir = self.runtime_paths.skills_dir / target_name
        if target_dir.exists():
            if not force:
                raise FileExistsError(f"Skill already exists: {target_dir}")
            shutil.rmtree(target_dir)

        if source_path.exists():
            skill_root = self._normalize_skill_source(source_path)
            shutil.copytree(skill_root, target_dir)
            installed_from = str(skill_root)
        else:
            if not re.match(r"^https?://", source):
                raise FileNotFoundError(f"Skill source not found: {source}")
            git_bin = shutil.which("git")
            if not git_bin:
                raise RuntimeError("git is not available; only local path install is supported")
            completed = subprocess.run(
                [git_bin, "clone", "--depth", "1", source, str(target_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip() or f"git clone failed: {source}")
            installed_from = source
            git_dir = target_dir / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)

        self._cleanup_installed_skill(target_dir)
        validation = self.validate_skill(target_name)
        self._cache = None
        return {
            "ok": True,
            "name": target_name,
            "source": installed_from,
            "target_dir": str(target_dir),
            "validation": validation,
        }

    def validate_skill(self, skill_name: str) -> dict[str, Any]:
        skill_dir = self.runtime_paths.skills_dir / skill_name
        checks: list[dict[str, str]] = []
        skill_md = skill_dir / "SKILL.md"
        has_error = False

        if skill_dir.exists():
            checks.append({"status": "PASS", "check": "skill_dir", "message": str(skill_dir)})
        else:
            checks.append({"status": "ERROR", "check": "skill_dir", "message": "skill directory missing"})
            has_error = True

        if skill_md.exists():
            checks.append({"status": "PASS", "check": "skill_md", "message": "SKILL.md present"})
        else:
            checks.append({"status": "ERROR", "check": "skill_md", "message": "SKILL.md missing"})
            has_error = True

        manifest: SkillManifest | None = None
        if skill_md.exists():
            try:
                manifest = SkillManifest.from_skill_md(skill_md, source_type="core")
                if manifest.name:
                    checks.append({"status": "PASS", "check": "frontmatter.name", "message": manifest.name})
                else:
                    checks.append({"status": "ERROR", "check": "frontmatter.name", "message": "name field is empty"})
                    has_error = True
            except Exception as exc:
                checks.append({"status": "ERROR", "check": "frontmatter.parse", "message": str(exc)})
                has_error = True

        scripts_dir = skill_dir / "scripts"
        if scripts_dir.exists():
            for script in sorted(scripts_dir.iterdir()):
                if not script.is_file():
                    continue
                mode = script.stat().st_mode
                if mode & 0o111:
                    checks.append({"status": "PASS", "check": f"script.exec:{script.name}", "message": "executable"})
                else:
                    checks.append({"status": "WARN", "check": f"script.exec:{script.name}", "message": "not executable"})

        return {
            "ok": not has_error,
            "name": skill_name,
            "path": str(skill_dir),
            "checks": checks,
            "manifest": manifest.to_dict() if manifest is not None else None,
        }

    def _normalize_skill_source(self, source_path: Path) -> Path:
        if source_path.is_file() and source_path.name == "SKILL.md":
            return source_path.parent
        if (source_path / "SKILL.md").exists():
            return source_path
        raise FileNotFoundError(f"Skill source must contain SKILL.md: {source_path}")

    def _infer_skill_name(self, source_path: Path, source: str) -> str:
        if source_path.exists():
            skill_root = self._normalize_skill_source(source_path)
            try:
                manifest = SkillManifest.from_skill_md(skill_root / "SKILL.md", source_type="core")
                if manifest.name:
                    return manifest.name
            except Exception:
                pass
            return skill_root.name
        suffix = source.rstrip("/").rsplit("/", 1)[-1]
        return suffix[:-4] if suffix.endswith(".git") else suffix

    def _cleanup_installed_skill(self, target_dir: Path) -> None:
        readme_path = target_dir / "README.md"
        if readme_path.exists():
            text = readme_path.read_text(encoding="utf-8")
            marker = re.search(r"(?im)^#+\s+install(?:ation)?\b", text)
            if marker:
                cleaned = text[: marker.start()].rstrip()
                readme_path.write_text((cleaned + "\n") if cleaned else "", encoding="utf-8")


def _keyword_score(query_tokens: set[str], manifest: SkillManifest) -> float:
    description = manifest.description.lower()
    triggers = [item.lower() for item in manifest.activation.triggers]
    haystack_text = " ".join([description, *triggers]).strip()
    if not query_tokens and not haystack_text:
        return 0.0
    for trigger in triggers:
        if trigger and any(trigger in token or token in trigger for token in query_tokens):
            return 130.0
    if any(token in description for token in query_tokens if len(token) >= 2):
        return 115.0
    haystack = _tokenize(haystack_text)
    if not haystack:
        return 0.0
    overlap = len(query_tokens & haystack)
    if overlap == 0:
        return 0.0
    return round(100.0 + (overlap / max(len(query_tokens), 1)) * 20.0, 2)


def _path_score(file_paths: list[str], patterns: list[str]) -> float:
    for file_path in file_paths:
        for pattern in patterns:
            if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(Path(file_path).name, pattern):
                return 80.0
    return 0.0


def _context_score(token_count: int | None, project: str, manifest: SkillManifest) -> tuple[float, str]:
    context = manifest.activation.context
    if token_count is not None and context.min_tokens is not None and token_count >= context.min_tokens:
        return 60.0, f"token_count >= {context.min_tokens}"
    if token_count is not None and context.max_tokens is not None and token_count <= context.max_tokens:
        return 55.0, f"token_count <= {context.max_tokens}"
    if project and context.project_types and project in {item.lower() for item in context.project_types}:
        return 50.0, f"project matched {project}"
    return 0.0, ""


def _tokenize(text: str) -> set[str]:
    normalized = text.lower()
    tokens = set(part for part in re.findall(r"[\w\u4e00-\u9fff]+", normalized) if len(part) >= 2)
    for piece in normalized.split():
        compact = piece.strip()
        if compact:
            tokens.add(compact)
    return tokens


def _relative_path(file_path: str, cwd: str) -> str:
    path = Path(file_path).expanduser()
    base = Path(cwd).expanduser()
    try:
        return str(path.relative_to(base))
    except ValueError:
        return file_path


def _resolve_script(manifest: SkillManifest, args: dict[str, Any]) -> Path | None:
    if not manifest.scripts:
        return None
    action = str(args.get("action", "")).strip()
    if action:
        action_candidates = {
            action,
            action.replace("-", "_"),
            action.replace("_", "-"),
        }
        for script in manifest.scripts:
            path = Path(script)
            if path.stem in action_candidates:
                return path
    if len(manifest.scripts) == 1:
        return Path(manifest.scripts[0])
    for script in manifest.scripts:
        if Path(script).stem in {"run", "main", manifest.name.replace("-", "_")}:
            return Path(script)
    return None


def _args_to_cli(args: dict[str, Any]) -> list[str]:
    cli_args: list[str] = []
    for key, value in args.items():
        if key in {"timeout", "project"} or value is None:
            continue
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                cli_args.append(flag)
            continue
        if isinstance(value, list):
            for item in value:
                cli_args.extend([flag, str(item)])
            continue
        cli_args.extend([flag, str(value)])
    return cli_args
