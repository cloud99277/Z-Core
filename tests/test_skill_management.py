import json
import unittest

from tests.helpers import TestHome, run_zcore


def write_skill(root, name: str, description: str = "Sample skill") -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "permissions:",
                "  shell: false",
                "io:",
                "  input:",
                "    - type: text",
                "      description: query",
                "---",
                "",
                f"# {name}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    (scripts_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")


class SkillManagementTests(unittest.TestCase):
    def test_skill_info_outputs_manifest_json(self) -> None:
        with TestHome() as ctx:
            write_skill(ctx.home / ".ai-skills", "memory-manager", "Memory utilities")

            proc = run_zcore("skill", "info", "memory-manager", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["name"], "memory-manager")
            self.assertEqual(payload["description"], "Memory utilities")
            self.assertEqual(payload["io"]["input"][0]["type"], "text")

    def test_skill_install_local_path_and_validate(self) -> None:
        with TestHome() as ctx:
            source_root = ctx.home / "source-skill"
            write_skill(source_root, "demo-skill", "Installed locally")

            install = run_zcore("skill", "install", str(source_root / "demo-skill"), "--json", home=ctx.home)
            self.assertEqual(install.returncode, 0, install.stderr)
            install_payload = json.loads(install.stdout)
            self.assertTrue(install_payload["ok"])
            self.assertEqual(install_payload["name"], "demo-skill")
            self.assertTrue((ctx.home / ".ai-skills" / "demo-skill" / "SKILL.md").exists())

            validate = run_zcore("skill", "validate", "demo-skill", "--json", home=ctx.home)
            self.assertEqual(validate.returncode, 0, validate.stderr)
            validate_payload = json.loads(validate.stdout)
            self.assertTrue(validate_payload["ok"])
            statuses = {item["status"] for item in validate_payload["checks"]}
            self.assertIn("PASS", statuses)

    def test_skill_validate_warns_for_non_executable_script(self) -> None:
        with TestHome() as ctx:
            write_skill(ctx.home / ".ai-skills", "warn-skill", "Check script bits")
            (ctx.home / ".ai-skills" / "warn-skill" / "scripts" / "main.py").chmod(0o644)

            proc = run_zcore("skill", "validate", "warn-skill", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            script_checks = [item for item in payload["checks"] if item["check"].startswith("script.exec:")]
            self.assertTrue(script_checks)
            self.assertIn(script_checks[0]["status"], {"PASS", "WARN"})
