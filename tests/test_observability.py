import json
import os
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.helpers import TestHome, run_zcore

from zcore.engines.observability import ObservabilityEngine
from zcore.runtime import RuntimePaths


class ObservabilityTests(unittest.TestCase):
    def test_execution_stats_aggregate_and_filter(self) -> None:
        with TestHome() as ctx:
            os.environ["HOME"] = str(ctx.home)
            os.environ["ZCORE_HOME"] = str(ctx.home / ".zcore")
            paths = RuntimePaths.discover()
            paths.ensure_runtime_dirs()
            log_path = paths.logs_dir / "executions.jsonl"
            now = datetime.now(UTC)
            payloads = [
                {
                    "timestamp": (now - timedelta(hours=2)).isoformat(),
                    "skill_name": "memory-manager",
                    "status": "ok",
                    "duration_ms": 120,
                },
                {
                    "timestamp": (now - timedelta(hours=1)).isoformat(),
                    "skill_name": "memory-manager",
                    "status": "error",
                    "duration_ms": 240,
                },
                {
                    "timestamp": (now - timedelta(days=8)).isoformat(),
                    "skill_name": "other",
                    "status": "ok",
                    "duration_ms": 500,
                },
            ]
            log_path.write_text("\n".join(json.dumps(item) for item in payloads) + "\n", encoding="utf-8")

            stats = ObservabilityEngine(paths).get_execution_stats("7d", skill_name="memory-manager")

            self.assertEqual(stats.total, 2)
            self.assertEqual(stats.success, 1)
            self.assertEqual(stats.failed, 1)
            self.assertEqual(stats.avg_duration_ms, 180.0)
            self.assertEqual(stats.by_skill, {"memory-manager": 2})
            self.assertEqual(stats.by_status, {"ok": 1, "error": 1})

    def test_cost_report_uses_budget_and_provider_filter(self) -> None:
        with TestHome() as ctx:
            os.environ["HOME"] = str(ctx.home)
            os.environ["ZCORE_HOME"] = str(ctx.home / ".zcore")
            paths = RuntimePaths.discover()
            paths.ensure_runtime_dirs()
            paths.config_path.write_text("[llm_backend]\nmonthly_budget = 5.0\n", encoding="utf-8")
            log_path = paths.logs_dir / "costs.jsonl"
            now = datetime.now(UTC)
            payloads = [
                {
                    "timestamp": (now - timedelta(hours=2)).isoformat(),
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "cost_usd": 0.4,
                },
                {
                    "timestamp": (now - timedelta(hours=1)).isoformat(),
                    "provider": "google",
                    "model": "gemini-2.5-flash",
                    "cost_usd": 0.6,
                },
            ]
            log_path.write_text("\n".join(json.dumps(item) for item in payloads) + "\n", encoding="utf-8")

            report = ObservabilityEngine(paths).get_cost_report("30d", provider="openai")

            self.assertEqual(report.total_usd, 0.4)
            self.assertEqual(report.by_provider, {"openai": 0.4})
            self.assertEqual(report.by_model, {"gpt-4o-mini": 0.4})
            self.assertEqual(report.budget_limit, 5.0)
            self.assertEqual(report.budget_remaining, 4.6)

    def test_health_report_marks_missing_paths(self) -> None:
        with TestHome() as ctx:
            os.environ["HOME"] = str(ctx.home)
            os.environ["ZCORE_HOME"] = str(ctx.home / ".zcore")
            paths = RuntimePaths.discover()
            paths.ensure_runtime_dirs()

            report = ObservabilityEngine(paths).health_check()

            self.assertFalse(report.healthy)
            self.assertEqual(report.checks["config"], "warn")
            self.assertEqual(report.checks["logs"], "ok")
            self.assertIn("config missing: run `zcore init`", report.warnings)
            self.assertEqual(report.disk_usage["logs"], 0)

    def test_observe_cli_stats_and_health_json(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            stats = run_zcore("observe", "stats", "--json", home=ctx.home)
            self.assertEqual(stats.returncode, 0, stats.stderr)
            stats_payload = json.loads(stats.stdout)
            self.assertEqual(stats_payload["total"], 0)
            self.assertEqual(stats_payload["period"], "7d")

            health = run_zcore("observe", "health", "--json", home=ctx.home)
            self.assertEqual(health.returncode, 0, health.stderr)
            health_payload = json.loads(health.stdout)
            self.assertFalse(health_payload["healthy"])
            self.assertIn("config", health_payload["checks"])

    def test_parse_since_supports_weeks_and_months(self) -> None:
        with TestHome() as ctx:
            os.environ["HOME"] = str(ctx.home)
            os.environ["ZCORE_HOME"] = str(ctx.home / ".zcore")
            paths = RuntimePaths.discover()
            paths.ensure_runtime_dirs()
            log_path = paths.logs_dir / "executions.jsonl"
            now = datetime.now(UTC)
            payloads = [
                {
                    "timestamp": (now - timedelta(days=10)).isoformat(),
                    "skill_name": "a",
                    "status": "ok",
                    "duration_ms": 100,
                },
                {
                    "timestamp": (now - timedelta(days=40)).isoformat(),
                    "skill_name": "b",
                    "status": "ok",
                    "duration_ms": 100,
                },
            ]
            log_path.write_text("\n".join(json.dumps(item) for item in payloads) + "\n", encoding="utf-8")

            engine = ObservabilityEngine(paths)
            week_stats = engine.get_execution_stats("2w")
            self.assertEqual(week_stats.total, 1)

            month_stats = engine.get_execution_stats("2m")
            self.assertEqual(month_stats.total, 2)
