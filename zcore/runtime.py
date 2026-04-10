from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from zcore.paths import ai_memory_home, runtime_home


@dataclass(frozen=True)
class RuntimePaths:
    base_dir: Path
    config_path: Path
    shared_rules_path: Path
    mcp_registry_path: Path
    sessions_dir: Path
    session_index_path: Path
    logs_dir: Path
    hooks_dir: Path
    pre_hooks_dir: Path
    post_hooks_dir: Path
    cache_dir: Path
    pending_dir: Path
    memory_dir: Path
    topics_dir: Path
    staging_dir: Path
    whiteboard_path: Path
    extraction_log_path: Path
    skills_dir: Path
    knowledge_db_path: Path
    lock_dir: Path

    @classmethod
    def discover(cls) -> "RuntimePaths":
        env_home = Path(os.environ.get("HOME", str(Path.home()))).expanduser()
        base_dir = runtime_home()
        memory_dir = ai_memory_home()
        skills_dir = Path(os.environ.get("AI_SKILLS_DIR") or env_home / ".ai-skills").expanduser()
        knowledge_db_path = Path(
            os.environ.get("ZCORE_KNOWLEDGE_DB") or env_home / ".lancedb" / "knowledge"
        ).expanduser()
        hooks_dir = base_dir / "hooks"
        return cls(
            base_dir=base_dir,
            config_path=base_dir / "config.toml",
            shared_rules_path=base_dir / "shared-rules.yaml",
            mcp_registry_path=base_dir / "mcp-servers.toml",
            sessions_dir=base_dir / "sessions",
            session_index_path=base_dir / "sessions" / "index.json",
            logs_dir=base_dir / "logs",
            hooks_dir=hooks_dir,
            pre_hooks_dir=hooks_dir / "pre-execute.d",
            post_hooks_dir=hooks_dir / "post-execute.d",
            cache_dir=base_dir / "cache",
            pending_dir=base_dir / "pending",
            memory_dir=memory_dir,
            topics_dir=memory_dir / "topics",
            staging_dir=memory_dir / "staging",
            whiteboard_path=memory_dir / "whiteboard.json",
            extraction_log_path=memory_dir / "extraction-log.jsonl",
            skills_dir=skills_dir,
            knowledge_db_path=knowledge_db_path,
            lock_dir=base_dir / "locks",
        )

    def ensure_runtime_dirs(self) -> list[Path]:
        created: list[Path] = []
        for path in (
            self.base_dir,
            self.sessions_dir,
            self.logs_dir,
            self.cache_dir,
            self.cache_dir / "token-estimates",
            self.pending_dir,
            self.workflows_dir,
            self.pre_hooks_dir,
            self.post_hooks_dir,
            self.lock_dir,
            self.memory_dir,
            self.topics_dir,
            self.staging_dir,
        ):
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                created.append(path)
        return created

    @property
    def workflows_dir(self) -> Path:
        return self.base_dir / "workflows"
