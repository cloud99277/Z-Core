from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from zcore.runtime import RuntimePaths


ZCORE_START = "<!-- ZCORE:START (managed by zcore setup, do not edit manually) -->"
ZCORE_END = "<!-- ZCORE:END -->"


@dataclass
class AgentInfo:
    name: str
    detected: bool
    config_path: Path | None
    version: str | None
    zcore_integrated: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["config_path"] = str(self.config_path) if self.config_path else None
        return payload


@dataclass
class SetupResult:
    agent: str
    success: bool
    config_path: str
    changes: list[str]
    backup_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentSetupEngine:
    def __init__(self, runtime_paths: RuntimePaths):
        self.runtime_paths = runtime_paths

    def detect_agents(self) -> list[AgentInfo]:
        return [
            self._detect_claude(),
            self._detect_gemini(),
            self._detect_codex(),
        ]

    def setup_agent(self, agent_name: str, *, dry_run: bool = False) -> SetupResult:
        if agent_name == "all":
            changes: list[str] = []
            backup_paths: list[str] = []
            success = True
            for agent in ("claude", "gemini", "codex"):
                result = self.setup_agent(agent, dry_run=dry_run)
                success = success and result.success
                changes.extend([f"{agent}: {item}" for item in result.changes])
                if result.backup_path:
                    backup_paths.append(result.backup_path)
            return SetupResult(
                agent="all",
                success=success,
                config_path="multiple",
                changes=changes,
                backup_path=",".join(backup_paths) if backup_paths else None,
            )

        path = self._default_config_path(agent_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        original = path.read_text(encoding="utf-8") if path.exists() else ""
        updated, changes = self._inject_block(original)
        backup_path = None

        if dry_run:
            return SetupResult(
                agent=agent_name,
                success=True,
                config_path=str(path),
                changes=changes or ["no changes needed"],
                backup_path=None,
            )

        if updated != original:
            if path.exists():
                backup = path.with_suffix(path.suffix + ".bak")
                shutil.copy2(path, backup)
                backup_path = str(backup)
            path.write_text(updated, encoding="utf-8")
        return SetupResult(
            agent=agent_name,
            success=True,
            config_path=str(path),
            changes=changes or ["no changes needed"],
            backup_path=backup_path,
        )

    def render_injection_block(self) -> str:
        return "\n".join(
            [
                ZCORE_START,
                "## Z-Core Runtime Integration",
                "",
                "- 开始新任务时：`zcore session start --project <project> --agent <agent> --json`",
                "- 完成任务后：`zcore session end --session-id <id> --json`",
                '- 搜索记忆：`zcore memory search --query "<query>" --json`',
                "- 上下文分析：`zcore context analyze --model <model> --input <file> --json`",
                "- 执行 skill：`zcore run <skill-name> [--args] --json`",
                "- 所有 zcore 命令都加 `--json` 获取结构化输出",
                ZCORE_END,
            ]
        )

    def _detect_claude(self) -> AgentInfo:
        path = Path.home() / ".claude" / "CLAUDE.md"
        return self._build_agent_info("claude", path, "claude")

    def _detect_gemini(self) -> AgentInfo:
        md_path = Path.home() / ".gemini" / "GEMINI.md"
        settings_path = Path.home() / ".gemini" / "settings.json"
        path = md_path if md_path.exists() else settings_path
        return self._build_agent_info("gemini", path, "gemini")

    def _detect_codex(self) -> AgentInfo:
        home_path = Path.home() / ".codex" / "AGENTS.md"
        cwd_path = Path.cwd() / "AGENTS.md"
        path = home_path if home_path.exists() else cwd_path
        return self._build_agent_info("codex", path, "codex")

    def _build_agent_info(self, name: str, path: Path, binary: str) -> AgentInfo:
        detected = path.exists()
        content = path.read_text(encoding="utf-8") if detected else ""
        return AgentInfo(
            name=name,
            detected=detected,
            config_path=path if detected else None,
            version=self._detect_version(binary),
            zcore_integrated=ZCORE_START in content and ZCORE_END in content,
        )

    def _detect_version(self, binary: str) -> str | None:
        executable = shutil.which(binary)
        if not executable:
            return None
        try:
            completed = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            )
        except OSError:
            return None
        text = completed.stdout.strip() or completed.stderr.strip()
        return text.splitlines()[0] if text else None

    def _default_config_path(self, agent_name: str) -> Path:
        if agent_name == "claude":
            return Path.home() / ".claude" / "CLAUDE.md"
        if agent_name == "gemini":
            return Path.home() / ".gemini" / "GEMINI.md"
        if agent_name == "codex":
            existing = Path.home() / ".codex" / "AGENTS.md"
            return existing if existing.exists() else Path.cwd() / "AGENTS.md"
        raise ValueError(f"Unsupported agent: {agent_name}")

    def _inject_block(self, content: str) -> tuple[str, list[str]]:
        block = self.render_injection_block().strip()
        if ZCORE_START in content and ZCORE_END in content:
            start = content.index(ZCORE_START)
            end = content.index(ZCORE_END) + len(ZCORE_END)
            prefix = content[:start].rstrip()
            suffix = content[end:].lstrip()
            parts: list[str] = []
            if prefix:
                parts.append(prefix)
            parts.append(block)
            if suffix:
                parts.append(suffix)
            updated = "\n\n".join(parts) + "\n"
            if updated == content:
                return content, []
            return updated, ["updated managed Z-Core block"]

        body = content.rstrip()
        if body:
            updated = body + "\n\n" + block + "\n"
        else:
            updated = block + "\n"
        return updated, ["inserted managed Z-Core block"]
