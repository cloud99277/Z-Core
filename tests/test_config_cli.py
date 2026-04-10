import json
import unittest

from tests.helpers import TestHome, run_zcore


class ConfigCliTests(unittest.TestCase):
    def test_config_show_masks_sensitive_fields(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            config_path = ctx.home / ".zcore" / "config.toml"
            original = config_path.read_text(encoding="utf-8")
            config_path.write_text(original + '\n[secrets]\napi_key = "abc123"\n', encoding="utf-8")

            proc = run_zcore("config", "show", "--section", "secrets", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["api_key"], "***")

    def test_config_set_updates_dot_notation(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            proc = run_zcore("config", "set", "governance.permission_mode", "yolo", "--json", home=ctx.home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["key"], "governance.permission_mode")

            shown = run_zcore("config", "show", "--section", "governance", "--json", home=ctx.home)
            self.assertEqual(shown.returncode, 0, shown.stderr)
            section = json.loads(shown.stdout)
            self.assertEqual(section["permission_mode"], "yolo")

    def test_config_reset_section_and_force_full_reset(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            changed = run_zcore("config", "set", "llm_backend.monthly_budget", "12.5", "--json", home=ctx.home)
            self.assertEqual(changed.returncode, 0, changed.stderr)

            reset_section = run_zcore("config", "reset", "--section", "llm_backend", "--json", home=ctx.home)
            self.assertEqual(reset_section.returncode, 0, reset_section.stderr)
            payload = json.loads(reset_section.stdout)
            self.assertEqual(payload["scope"], "llm_backend")

            shown = run_zcore("config", "show", "--section", "llm_backend", "--json", home=ctx.home)
            section = json.loads(shown.stdout)
            self.assertEqual(section["monthly_budget"], 5.0)

            fail = run_zcore("config", "reset", "--json", home=ctx.home)
            self.assertNotEqual(fail.returncode, 0)

            reset_all = run_zcore("config", "reset", "--force", "--json", home=ctx.home)
            self.assertEqual(reset_all.returncode, 0, reset_all.stderr)
            all_payload = json.loads(reset_all.stdout)
            self.assertEqual(all_payload["scope"], "all")
