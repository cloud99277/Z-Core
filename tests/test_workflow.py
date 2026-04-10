import json
import unittest

from tests.helpers import TestHome, run_zcore


def write_skill(root, name: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {name} skill",
                "---",
                "",
                f"# {name}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_workflow(path, *, fail: bool = False, missing_skill: bool = False) -> None:
    command = 'skill info memory-manager' if not fail else 'skill info missing-skill'
    second_skill = "observability" if not missing_skill else "ghost"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "[workflow]",
                'name = "daily-review"',
                'description = "Daily checks"',
                "",
                "[[steps]]",
                'name = "inspect-memory"',
                'skill = "memory-manager"',
                f'command = "{command}"',
                'args = ["--json"]',
                'on_failure = "continue"',
                "",
                "[[steps]]",
                'name = "inspect-observability"',
                f'skill = "{second_skill}"',
                'command = "observe health"',
                'args = ["--json"]',
                'on_failure = "abort"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


class WorkflowTests(unittest.TestCase):
    def test_workflow_list_discovers_global_and_project_workflows(self) -> None:
        with TestHome(with_workspace=True) as ctx:
            write_skill(ctx.home / ".ai-skills", "memory-manager")
            write_skill(ctx.home / ".ai-skills", "observability")
            write_workflow(ctx.home / ".zcore" / "workflows" / "global.toml")
            write_workflow(ctx.workspace / ".zcore" / "workflows" / "project.toml")

            proc = run_zcore("workflow", "list", "--json", home=ctx.home, cwd=ctx.workspace)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(len(payload), 2)
            self.assertEqual(payload[0]["name"], "daily-review")

    def test_workflow_validate_reports_pass_checks(self) -> None:
        with TestHome(with_workspace=True) as ctx:
            write_skill(ctx.home / ".ai-skills", "memory-manager")
            write_skill(ctx.home / ".ai-skills", "observability")
            workflow_path = ctx.workspace / ".zcore" / "workflows" / "daily-review.toml"
            write_workflow(workflow_path)

            proc = run_zcore("workflow", "validate", "daily-review", "--json", home=ctx.home, cwd=ctx.workspace)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["ok"])
            statuses = {item["status"] for item in payload["checks"]}
            self.assertEqual(statuses, {"PASS"})

    def test_workflow_validate_reports_missing_skill(self) -> None:
        with TestHome(with_workspace=True) as ctx:
            write_skill(ctx.home / ".ai-skills", "memory-manager")
            workflow_path = ctx.workspace / ".zcore" / "workflows" / "daily-review.toml"
            write_workflow(workflow_path, missing_skill=True)

            proc = run_zcore("workflow", "validate", str(workflow_path), "--json", home=ctx.home, cwd=ctx.workspace)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertFalse(payload["ok"])
            self.assertIn("ERROR", {item["status"] for item in payload["checks"]})

    def test_workflow_run_dry_run_returns_command_plan(self) -> None:
        with TestHome(with_workspace=True) as ctx:
            write_skill(ctx.home / ".ai-skills", "memory-manager")
            write_skill(ctx.home / ".ai-skills", "observability")
            write_workflow(ctx.workspace / ".zcore" / "workflows" / "daily-review.toml")

            proc = run_zcore("workflow", "run", "daily-review", "--dry-run", "--json", home=ctx.home, cwd=ctx.workspace)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["overall"], "ok")
            self.assertIn("-m zcore skill info memory-manager --json", payload["steps"][0]["stdout_summary"])

    def test_workflow_run_continues_on_failure_and_reports_partial(self) -> None:
        with TestHome(with_workspace=True) as ctx:
            write_skill(ctx.home / ".ai-skills", "memory-manager")
            write_skill(ctx.home / ".ai-skills", "observability")
            write_workflow(ctx.workspace / ".zcore" / "workflows" / "daily-review.toml", fail=True)

            proc = run_zcore("workflow", "run", "daily-review", "--json", home=ctx.home, cwd=ctx.workspace)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["overall"], "partial")
            self.assertEqual(payload["steps"][0]["status"], "error")
            self.assertEqual(payload["steps"][1]["status"], "ok")
