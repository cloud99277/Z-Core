"""Regression tests for TOML rendering of runtime paths in config.toml."""

from __future__ import annotations

import dataclasses
import tomllib
import unittest
from pathlib import Path, PurePath

from zcore.config import render_default_config
from zcore.runtime import RuntimePaths

from tests.helpers import TestHome, run_zcore


class ConfigRenderTests(unittest.TestCase):
    """Windows paths contain backslashes, which TOML treats as escape
    introducers. An unescaped path made ``zcore init`` emit a config that
    ``tomllib`` could not read back.
    """

    def _paths_with_windows_roots(self) -> RuntimePaths:
        return dataclasses.replace(
            RuntimePaths.discover(),
            memory_dir=Path("D:\\AIdata\\Z-CORE\\memory"),
            skills_dir=Path("D:\\AIdata\\Z-CORE\\skills"),
            knowledge_db_path=Path("D:\\AIdata\\Z-CORE\\knowledge.db"),
        )

    def test_windows_backslash_paths_round_trip(self) -> None:
        with TestHome():
            text = render_default_config(self._paths_with_windows_roots())

            parsed = tomllib.loads(text)

            self.assertEqual(
                PurePath(parsed["paths"]["memory_dir"]),
                PurePath("D:\\AIdata\\Z-CORE\\memory"),
            )
            self.assertEqual(
                PurePath(parsed["paths"]["skills_dir"]),
                PurePath("D:\\AIdata\\Z-CORE\\skills"),
            )
            self.assertEqual(
                PurePath(parsed["paths"]["knowledge_db"]),
                PurePath("D:\\AIdata\\Z-CORE\\knowledge.db"),
            )

    def test_path_with_quote_is_escaped(self) -> None:
        with TestHome():
            paths = dataclasses.replace(
                RuntimePaths.discover(),
                memory_dir=Path('/tmp/we"ird/memory'),
            )

            parsed = tomllib.loads(render_default_config(paths))

            self.assertEqual(parsed["paths"]["memory_dir"], '/tmp/we"ird/memory')

    def test_plain_posix_paths_are_not_altered(self) -> None:
        with TestHome() as ctx:
            paths = RuntimePaths.discover()

            text = render_default_config(paths)

            self.assertIn(f'memory_dir = "{paths.memory_dir.as_posix()}"', text)
            self.assertIn(f'skills_dir = "{paths.skills_dir.as_posix()}"', text)
            self.assertIn(f'knowledge_db = "{paths.knowledge_db_path.as_posix()}"', text)
            self.assertIsNotNone(ctx.home)

    def test_init_config_is_readable_by_tomllib(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            config_path = ctx.home / ".zcore" / "config.toml"
            with config_path.open("rb") as handle:
                parsed = tomllib.load(handle)

            self.assertIn("paths", parsed)
            self.assertTrue(
                str(parsed["paths"]["memory_dir"]).startswith(str(ctx.home)),
                parsed["paths"]["memory_dir"],
            )

    def test_config_set_escapes_windows_path_value(self) -> None:
        with TestHome() as ctx:
            init_proc = run_zcore("init", "--json", home=ctx.home)
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            proc = run_zcore(
                "config",
                "set",
                "knowledge.source_dir",
                "D:\\AIdata\\kb",
                "--json",
                home=ctx.home,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            config_path = ctx.home / ".zcore" / "config.toml"
            with config_path.open("rb") as handle:
                parsed = tomllib.load(handle)

            self.assertEqual(
                PurePath(parsed["knowledge"]["source_dir"]),
                PurePath("D:\\AIdata\\kb"),
            )


if __name__ == "__main__":
    unittest.main()
