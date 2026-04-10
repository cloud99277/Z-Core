from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from zcore.config import get_nested, load_config
from zcore.runtime import RuntimePaths
from zcore.utils.time import parse_since_window


@dataclass
class ExecutionStats:
    total: int
    success: int
    failed: int
    avg_duration_ms: float
    by_skill: dict[str, int]
    by_status: dict[str, int]
    period: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CostReport:
    total_usd: float
    by_provider: dict[str, float]
    by_model: dict[str, float]
    budget_limit: float
    budget_remaining: float
    period: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HealthReport:
    healthy: bool
    checks: dict[str, str]
    warnings: list[str]
    disk_usage: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ObservabilityEngine:
    def __init__(self, runtime_paths: RuntimePaths):
        self.runtime_paths = runtime_paths
        self.config = load_config(runtime_paths)

    def log_execution(
        self,
        skill_name: str,
        status: str | None,
        duration_ms: int | None,
        *,
        session_id: str | None = None,
        project: str | None = None,
        output: str | None = None,
        cost_usd: float | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "skill_name": skill_name,
            "session_id": session_id,
            "project": project,
            "status": status,
            "duration_ms": duration_ms,
            "output": output,
            "cost_usd": cost_usd,
            "provider": provider,
            "model": model,
        }
        self._append_jsonl(self.runtime_paths.logs_dir / "executions.jsonl", payload)
        return payload

    def log_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        *,
        session_id: str | None = None,
        skill_name: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "session_id": session_id,
            "skill_name": skill_name,
        }
        self._append_jsonl(self.runtime_paths.logs_dir / "costs.jsonl", payload)
        return payload

    def get_execution_stats(self, since: str = "7d", skill_name: str | None = None) -> ExecutionStats:
        total = 0
        success = 0
        failed = 0
        duration_total = 0
        duration_count = 0
        by_skill: dict[str, int] = {}
        by_status: dict[str, int] = {}

        for item in self._iter_jsonl(self.runtime_paths.logs_dir / "executions.jsonl", since=since):
            current_skill = str(item.get("skill_name") or "")
            if skill_name and current_skill != skill_name:
                continue
            total += 1
            status = str(item.get("status") or "unknown")
            if status == "ok":
                success += 1
            elif status:
                failed += 1
            by_skill[current_skill] = by_skill.get(current_skill, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
            duration = item.get("duration_ms")
            if isinstance(duration, (int, float)):
                duration_total += int(duration)
                duration_count += 1

        avg_duration_ms = round(duration_total / duration_count, 2) if duration_count else 0.0
        return ExecutionStats(
            total=total,
            success=success,
            failed=failed,
            avg_duration_ms=avg_duration_ms,
            by_skill=by_skill,
            by_status=by_status,
            period=since,
        )

    def get_cost_report(self, since: str = "30d", provider: str | None = None) -> CostReport:
        total_usd = 0.0
        by_provider: dict[str, float] = {}
        by_model: dict[str, float] = {}

        for item in self._iter_jsonl(self.runtime_paths.logs_dir / "costs.jsonl", since=since):
            current_provider = str(item.get("provider") or "unknown")
            if provider and current_provider != provider:
                continue
            current_model = str(item.get("model") or "unknown")
            cost = float(item.get("cost_usd") or 0.0)
            total_usd += cost
            by_provider[current_provider] = round(by_provider.get(current_provider, 0.0) + cost, 8)
            by_model[current_model] = round(by_model.get(current_model, 0.0) + cost, 8)

        budget_limit = float(get_nested(self.config, "llm_backend", "monthly_budget", default=0.0) or 0.0)
        budget_remaining = round(max(budget_limit - total_usd, 0.0), 8)
        return CostReport(
            total_usd=round(total_usd, 8),
            by_provider=by_provider,
            by_model=by_model,
            budget_limit=budget_limit,
            budget_remaining=budget_remaining,
            period=since,
        )

    def health_check(self) -> HealthReport:
        checks: dict[str, str] = {}
        warnings: list[str] = []

        expected_paths = {
            "base_dir": self.runtime_paths.base_dir,
            "config": self.runtime_paths.config_path,
            "logs": self.runtime_paths.logs_dir,
            "sessions": self.runtime_paths.sessions_dir,
            "hooks": self.runtime_paths.hooks_dir,
            "memory": self.runtime_paths.memory_dir,
            "skills": self.runtime_paths.skills_dir,
        }
        for name, path in expected_paths.items():
            if path.exists():
                checks[name] = "ok"
            else:
                checks[name] = "warn"
                warnings.append(f"missing path: {path}")

        if not self.runtime_paths.config_path.exists():
            warnings.append("config missing: run `zcore init`")

        disk_usage = {
            "sessions": self._path_size(self.runtime_paths.sessions_dir),
            "logs": self._path_size(self.runtime_paths.logs_dir),
            "cache": self._path_size(self.runtime_paths.cache_dir),
            "memory": self._path_size(self.runtime_paths.memory_dir),
        }
        healthy = all(status == "ok" for status in checks.values())
        return HealthReport(healthy=healthy, checks=checks, warnings=warnings, disk_usage=disk_usage)

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _iter_jsonl(self, path: Path, *, since: str) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        cutoff = self._parse_since(since)
        items: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            timestamp = self._parse_timestamp(payload.get("timestamp"))
            if timestamp is None or timestamp < cutoff:
                continue
            if isinstance(payload, dict):
                items.append(payload)
        return items

    def _parse_since(self, since: str) -> datetime:
        return parse_since_window(since)

    def _parse_timestamp(self, value: object) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _path_size(self, path: Path) -> int:
        if not path.exists():
            return 0
        if path.is_file():
            return path.stat().st_size
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
        return total
