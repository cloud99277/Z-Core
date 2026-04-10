from __future__ import annotations

import fnmatch
import json
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zcore.config import get_nested, load_config
from zcore.runtime import RuntimePaths
from zcore.utils.filelock import FileLock


class PermissionDeniedError(RuntimeError):
    """Raised when a permission decision blocks execution."""


@dataclass
class PermissionResult:
    decision: str
    reason: str


@dataclass
class PermissionRule:
    action: str
    pattern: str
    decision: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return {
            "action": self.action,
            "pattern": self.pattern,
            "decision": self.decision,
            "source": self.source,
        }


@dataclass
class PermissionDecision:
    allowed: bool
    decision: str
    matched_rule: PermissionRule | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "decision": self.decision,
            "matched_rule": self.matched_rule.to_dict() if self.matched_rule else None,
            "reason": self.reason,
        }


DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+[/~]",
    r"rm\s+-rf\s+\*",
    r">\s*/dev/sd[a-z]",
    r"mkfs\.",
    r"dd\s+if=.+of=/dev/",
    r"chmod\s+-R\s+777",
    r"chown\s+-R\s+root",
    r"sudo\s+",
    r"curl\s+.*\|\s*(?:sh|bash)",
    r"wget\s+.*\|\s*(?:sh|bash)",
    r"eval\s+\$\(",
    r"cat\s+.*\.env",
    r"echo\s+.*API_KEY",
    r"export\s+.*SECRET",
]

RISKY_PATTERNS = [
    r"\bcurl\s+",
    r"\bwget\s+",
    r"\bpip\s+install\b",
    r"\bnpm\s+install\b",
    r"\bgit\s+push\b",
    r"\bchmod\s+",
    r"\bchown\s+",
]

_RULE_RE = re.compile(r"^(?P<action>[\w.]+)\((?P<pattern>.*)\)$")
_SOURCE_PRIORITY = {"global": 0, "project": 1, "session": 2}
_DECISION_PRIORITY = {"allow": 0, "ask": 1, "deny": 2}


def resolve_ask_behavior(action: str, target: str, *, tty: bool | None = None) -> PermissionResult:
    """Phase 0 contract for ask-mode.

    In non-TTY mode, `ask` must fail fast with a machine-readable error so the
    calling agent can request confirmation and retry explicitly.
    """
    is_tty = sys.stdin.isatty() if tty is None else tty
    if not is_tty:
        raise PermissionDeniedError(
            f"decision=ask_required action={action} target={target} mode=non_tty"
        )
    return PermissionResult(decision="ask", reason="interactive_confirmation_required")


class PermissionEngine:
    def __init__(self, runtime_paths: RuntimePaths, *, project_root: str | Path | None = None):
        self.runtime_paths = runtime_paths
        self.project_root = Path(project_root).expanduser() if project_root else Path.cwd()
        self.session_rules: list[PermissionRule] = []

    def load_rules(self) -> list[PermissionRule]:
        rules: list[PermissionRule] = []
        rules.extend(self._load_rules_from_config(load_config(self.runtime_paths), source="global"))

        project_config = self.project_root / ".zcore" / "config.toml"
        if project_config.exists():
            with project_config.open("rb") as handle:
                rules.extend(self._load_rules_from_config(tomllib.load(handle), source="project"))

        rules.extend(self.session_rules)
        return rules

    def add_session_rule(self, rule: PermissionRule) -> None:
        self.session_rules.append(rule)

    def check(self, action: str, target: str) -> PermissionDecision:
        matches = [rule for rule in self.load_rules() if rule.action == action and fnmatch.fnmatch(target, rule.pattern)]
        if matches:
            best_rule = max(matches, key=lambda rule: (_DECISION_PRIORITY[rule.decision], _SOURCE_PRIORITY.get(rule.source, -1)))
            allowed = best_rule.decision == "allow"
            reason = f"matched {best_rule.source} rule {best_rule.action}({best_rule.pattern})"
            if best_rule.decision == "ask":
                try:
                    result = resolve_ask_behavior(action, target)
                    return PermissionDecision(True, result.decision, best_rule, reason)
                except PermissionDeniedError as exc:
                    return PermissionDecision(False, "ask", best_rule, str(exc))
            return PermissionDecision(allowed, best_rule.decision, best_rule, reason)

        mode = self._permission_mode()
        if mode == "yolo":
            return PermissionDecision(True, "allow", None, "permission_mode=yolo")
        if mode == "auto":
            if action == "shell":
                classification = classify_shell_command(target)
                if classification == "dangerous":
                    return PermissionDecision(False, "deny", None, f"shell classified as {classification}")
                if classification == "risky":
                    return PermissionDecision(False, "ask", None, f"shell classified as {classification}")
            return PermissionDecision(True, "allow", None, "permission_mode=auto default allow")
        try:
            result = resolve_ask_behavior(action, target)
            return PermissionDecision(True, result.decision, None, "permission_mode=ask")
        except PermissionDeniedError as exc:
            return PermissionDecision(False, "ask", None, str(exc))

    def _load_rules_from_config(self, config: dict[str, Any], *, source: str) -> list[PermissionRule]:
        raw_rules = get_nested(config, "governance", "rules", default={})
        if not isinstance(raw_rules, dict):
            return []
        parsed: list[PermissionRule] = []
        for key, value in raw_rules.items():
            match = _RULE_RE.match(str(key))
            if not match:
                continue
            decision = str(value).strip().lower()
            if decision not in _DECISION_PRIORITY:
                continue
            parsed.append(
                PermissionRule(
                    action=match.group("action"),
                    pattern=match.group("pattern") or "*",
                    decision=decision,
                    source=source,
                )
            )
        return parsed

    def _permission_mode(self) -> str:
        config = load_config(self.runtime_paths)
        value = get_nested(config, "governance", "permission_mode", default="ask")
        return str(value)

    def add_rule(self, pattern: str, decision: str) -> PermissionRule:
        if decision not in _DECISION_PRIORITY:
            raise ValueError(f"Unsupported decision: {decision}")
        config_path = self.runtime_paths.config_path
        config_path.parent.mkdir(parents=True, exist_ok=True)
        text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
        section_pattern = re.compile(r"(?ms)^(\[governance\.rules\]\n)(.*?)(?=^\[|\Z)")
        entry_line = f'"{pattern}" = "{decision}"\n'

        if section_pattern.search(text):
            def repl(match: re.Match[str]) -> str:
                body = match.group(2)
                line_re = re.compile(rf'(?m)^"{re.escape(pattern)}"\s*=\s*".*"$')
                if line_re.search(body):
                    body = line_re.sub(entry_line.rstrip("\n"), body)
                else:
                    body = body + entry_line if body.endswith("\n") or not body else body + "\n" + entry_line
                return match.group(1) + body

            updated = section_pattern.sub(repl, text, count=1)
        else:
            block = f'[governance.rules]\n{entry_line}'
            updated = text.rstrip() + ("\n\n" if text.strip() else "") + block

        lock_path = config_path.parent / "config.toml.lock"
        with FileLock(lock_path):
            config_path.write_text(updated if updated.endswith("\n") else updated + "\n", encoding="utf-8")

        match = _RULE_RE.match(pattern)
        action = match.group("action") if match else "unknown"
        rule_pattern = match.group("pattern") if match else pattern
        return PermissionRule(action=action, pattern=rule_pattern, decision=decision, source="global")

    def read_log(self, *, last: int = 20, skill_name: str | None = None) -> list[dict[str, Any]]:
        log_path = self.runtime_paths.logs_dir / "executions.jsonl"
        if not log_path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if skill_name and payload.get("skill_name") != skill_name:
                continue
            records.append(payload)
        return records[-last:]

    def audit_report(self) -> dict[str, Any]:
        rules = self.load_rules()
        all_logs = self.read_log(last=1000)
        rule_stats = {
            "total": len(rules),
            "allow": sum(1 for rule in rules if rule.decision == "allow"),
            "deny": sum(1 for rule in rules if rule.decision == "deny"),
            "ask": sum(1 for rule in rules if rule.decision == "ask"),
        }
        denied_events = [
            item for item in all_logs if str(item.get("status") or "").lower() in {"blocked", "deny", "denied"}
        ]
        skill_counts: dict[str, int] = {}
        dangerous_history: list[dict[str, Any]] = []
        for item in all_logs:
            skill_name = str(item.get("skill_name") or "")
            if skill_name:
                skill_counts[skill_name] = skill_counts.get(skill_name, 0) + 1
            output = str(item.get("output") or "")
            if "dangerous shell command" in output or "decision=ask_required" in output:
                dangerous_history.append(item)
        high_frequency_skills = [
            {"skill_name": name, "count": count}
            for name, count in sorted(skill_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        ]
        return {
            "rule_stats": rule_stats,
            "recent_denied_events": denied_events[-10:],
            "high_frequency_skills": high_frequency_skills,
            "dangerous_command_history": dangerous_history[-10:],
        }


def classify_shell_command(cmd: str) -> str:
    lowered = cmd.strip()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, lowered):
            return "dangerous"
    for pattern in RISKY_PATTERNS:
        if re.search(pattern, lowered):
            return "risky"
    return "safe"
