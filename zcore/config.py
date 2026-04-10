from __future__ import annotations

import os
import re
import stat
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from zcore.runtime import RuntimePaths
from zcore.utils.filelock import FileLock


def render_default_config(paths: RuntimePaths) -> str:
    return "\n".join(
        [
            "[core]",
            'version = "2.0"',
            "",
            "[llm_backend]",
            "enabled = false",
            'provider = "google"',
            'model = "gemini-2.5-flash"',
            'endpoint = ""',
            "timeout = 30",
            "monthly_budget = 5.0",
            "retry_max = 2",
            "fallback_on_failure = true",
            "",
            "[privacy]",
            "redact_before_send = true",
            "redact_file_paths = true",
            "redact_patterns = [",
            '  "(?i)(api[_-]?key|token|secret|password)\\\\s*[=:]\\\\s*\\\\S+",',
            '  "sk-[a-zA-Z0-9]{20,}",',
            '  "AIza[a-zA-Z0-9_-]{35}",',
            "]",
            "",
            "[memory]",
            "auto_extract = false",
            "dedup_threshold = 0.85",
            "max_l2_entries = 500",
            "topic_storage = true",
            "",
            "[memory_extraction]",
            "min_turns_for_extraction = 3",
            "auto_admit_threshold = 0.8",
            "pending_threshold = 0.5",
            "dedup_threshold = 0.85",
            "",
            "[context]",
            "auto_compact = false",
            "compact_threshold_pct = 80",
            "buffer_tokens = 13000",
            "",
            "[session]",
            "auto_snapshot = false",
            "snapshot_retention_days = 30",
            "enable_handoff = false",
            "",
            "[governance]",
            'permission_mode = "ask"',
            "hooks_enabled = true",
            "",
            "[observability]",
            "cost_tracking = true",
            "execution_logging = true",
            "health_reports = false",
            "",
            "[paths]",
            f'memory_dir = "{paths.memory_dir}"',
            f'skills_dir = "{paths.skills_dir}"',
            f'knowledge_db = "{paths.knowledge_db_path}"',
            "",
        ]
    ) + "\n"


def render_default_shared_rules() -> str:
    return "\n".join(
        [
            "version: 1",
            "constraints:",
            '  - "Install external skills through zcore skill install once implemented."',
            '  - "Do not auto-commit or auto-push unless explicitly instructed."',
            '  - "Prefer progressive implementation and verify before claiming completion."',
            "user_profile:",
            '  language: "简体中文（技术术语保留英文）"',
            '  timezone: "Asia/Shanghai"',
            '  style: "先收敛范围，再实现骨架，再补自动化"',
            "routing_hint:",
            '  memory: "近期决策/行动 → memory-manager 或未来 zcore memory 命令"',
            '  knowledge: "稳定文档/SOP/研究 → knowledge-search"',
        ]
    ) + "\n"


def init_runtime(paths: RuntimePaths, force: bool = False) -> dict[str, object]:
    created_dirs = [str(path) for path in paths.ensure_runtime_dirs()]

    wrote_config = False
    if force or not paths.config_path.exists():
        paths.config_path.write_text(render_default_config(paths), encoding="utf-8")
        os.chmod(paths.config_path, 0o600)
        wrote_config = True

    wrote_shared_rules = False
    if force or not paths.shared_rules_path.exists():
        paths.shared_rules_path.write_text(render_default_shared_rules(), encoding="utf-8")
        wrote_shared_rules = True

    return {
        "created_dirs": created_dirs,
        "config_path": str(paths.config_path),
        "shared_rules_path": str(paths.shared_rules_path),
        "wrote_config": wrote_config,
        "wrote_shared_rules": wrote_shared_rules,
    }


def load_config(paths: RuntimePaths) -> dict[str, object]:
    if not paths.config_path.exists():
        return {}
    with paths.config_path.open("rb") as handle:
        return tomllib.load(handle)


_SENSITIVE_KEY_RE = re.compile(r"(^|[_-])(api[_-]?key|secret|password|auth[_-]?token)$", re.IGNORECASE)


def mask_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, item in value.items():
            if _SENSITIVE_KEY_RE.search(str(key)):
                masked[str(key)] = "***"
            else:
                masked[str(key)] = mask_sensitive_data(item)
        return masked
    if isinstance(value, list):
        return [mask_sensitive_data(item) for item in value]
    return value


def set_config_value(paths: RuntimePaths, dotted_key: str, raw_value: str) -> dict[str, object]:
    if "." not in dotted_key:
        raise ValueError("config key must use dot notation, e.g. section.key")
    section, key = dotted_key.split(".", 1)
    text = paths.config_path.read_text(encoding="utf-8") if paths.config_path.exists() else render_default_config(paths)
    section_body = _get_section_body(text, section)
    rendered_value = _render_toml_value(raw_value)
    line_re = re.compile(rf"(?m)^({re.escape(key)}\s*=\s*).*$")

    if section_body is None:
        addition = f"[{section}]\n{key} = {rendered_value}\n"
        text = text.rstrip() + "\n\n" + addition
    elif line_re.search(section_body):
        new_body = line_re.sub(rf"\1{rendered_value}", section_body)
        text = _replace_section_body(text, section, new_body)
    else:
        updated_body = section_body.rstrip() + f"\n{key} = {rendered_value}\n"
        text = _replace_section_body(text, section, updated_body)

    _atomic_write(paths.config_path, text)
    return {"ok": True, "key": dotted_key, "value": _parse_cli_value(raw_value)}


def reset_config(paths: RuntimePaths, section: str | None = None) -> dict[str, object]:
    default_text = render_default_config(paths)
    if section is None:
        _atomic_write(paths.config_path, default_text)
        return {"ok": True, "scope": "all"}

    target_body = _get_section_body(default_text, section)
    if target_body is None:
        raise ValueError(f"Unknown config section: {section}")

    current_text = paths.config_path.read_text(encoding="utf-8") if paths.config_path.exists() else default_text
    if _get_section_body(current_text, section) is None:
        current_text = current_text.rstrip() + f"\n\n[{section}]\n" + target_body.lstrip("\n")
    else:
        current_text = _replace_section_body(current_text, section, target_body)

    _atomic_write(paths.config_path, current_text)
    return {"ok": True, "scope": section}


def get_nested(config: dict[str, object], *keys: str, default: object = None) -> object:
    current: object = config
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def config_permissions_ok(paths: RuntimePaths) -> bool:
    if not paths.config_path.exists():
        return True
    if str(paths.config_path).startswith("/mnt/"):
        return True
    mode = stat.S_IMODE(paths.config_path.stat().st_mode)
    return (mode & 0o077) == 0


def config_permissions_warning(paths: RuntimePaths) -> str | None:
    if not paths.config_path.exists():
        return None
    if config_permissions_ok(paths):
        return None
    return f"config permissions should be 0o600: {paths.config_path}"


def _parse_cli_value(raw_value: str) -> Any:
    lowered = raw_value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if re.fullmatch(r"-?\d+", raw_value.strip()):
        return int(raw_value)
    if re.fullmatch(r"-?\d+\.\d+", raw_value.strip()):
        return float(raw_value)
    return raw_value


def _render_toml_value(raw_value: str) -> str:
    value = _parse_cli_value(raw_value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _get_section_body(text: str, section: str) -> str | None:
    match = re.search(rf"(?ms)^\[{re.escape(section)}\]\n(.*?)(?=^\[|\Z)", text)
    if not match:
        return None
    return match.group(1)


def _replace_section_body(text: str, section: str, body: str) -> str:
    pattern = re.compile(rf"(?ms)^(\[{re.escape(section)}\]\n)(.*?)(?=^\[|\Z)")

    def repl(match: re.Match[str]) -> str:
        normalized = body if body.endswith("\n") else body + "\n"
        return match.group(1) + normalized

    return pattern.sub(repl, text, count=1)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / f"{path.name}.lock"
    with FileLock(lock_path):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            handle.write(text)
            temp_name = handle.name
        os.replace(temp_name, path)
        if not str(path).startswith("/mnt/"):
            os.chmod(path, 0o600)
