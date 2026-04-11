"""Tests for core skill management: list_available, install_core, uninstall."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zcore.engines.router import SkillRouter, _bundled_skills_dir
from zcore.runtime import RuntimePaths


class TestBundledSkillsDir(unittest.TestCase):
    def test_bundled_skills_dir_path(self):
        """_bundled_skills_dir() should return <repo>/skills/core."""
        result = _bundled_skills_dir()
        self.assertTrue(str(result).endswith("skills/core") or str(result).endswith("skills\\core"))
        self.assertTrue(result.exists(), f"Expected bundled skills dir to exist: {result}")

    def test_bundled_skills_contains_skills(self):
        """Bundled skills dir should contain at least 10 skills."""
        bundled = _bundled_skills_dir()
        skill_dirs = [d for d in bundled.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
        self.assertGreaterEqual(len(skill_dirs), 10, f"Expected >=10 skills, found {len(skill_dirs)}")


class TestListAvailable(unittest.TestCase):
    def setUp(self):
        self.paths = RuntimePaths.discover()
        self.router = SkillRouter(self.paths)

    def test_list_available_returns_all_core(self):
        """list_available() should return exactly the 17 core skills."""
        available = self.router.list_available()
        self.assertEqual(len(available), 17, f"Expected 17, got {len(available)}: {[s['name'] for s in available]}")

    def test_list_available_has_status(self):
        """Every item in list_available should have a status field."""
        for item in self.router.list_available():
            self.assertIn("status", item)
            self.assertIn(item["status"], {"installed", "available"})

    def test_list_available_json_structure(self):
        """Each item should have name, description, source_path, status."""
        for item in self.router.list_available():
            self.assertIn("name", item)
            self.assertIn("description", item)
            self.assertIn("source_path", item)
            self.assertIn("status", item)


class TestInstallCoreSkills(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.skills_dir = Path(self.tmp) / "ai-skills"
        self.skills_dir.mkdir()
        # Create a RuntimePaths clone with temp skills_dir
        real = RuntimePaths.discover()
        # Use dataclasses.replace-like approach via __class__ constructor
        fields = {f.name: getattr(real, f.name) for f in real.__dataclass_fields__.values()}
        fields["skills_dir"] = self.skills_dir
        self.paths = RuntimePaths(**fields)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_install_core_to_empty_dir(self):
        """install_core_skills() into empty dir should install all 17."""
        router = SkillRouter(self.paths)
        result = router.install_core_skills()
        self.assertTrue(result["ok"])
        self.assertEqual(result["total"], 17)
        self.assertEqual(result["installed"], 17)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["errors"], 0)


class TestUninstallSkill(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.skills_dir = Path(self.tmp) / "ai-skills"
        self.skills_dir.mkdir()
        # Create a fake installed skill
        fake_skill = self.skills_dir / "test-skill"
        fake_skill.mkdir()
        (fake_skill / "SKILL.md").write_text("---\nname: test-skill\n---\n# Test Skill\n")
        self.paths = RuntimePaths.discover()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_uninstall_nonexistent_raises(self):
        """uninstall_skill() on missing skill should raise FileNotFoundError."""
        router = SkillRouter(self.paths)
        with self.assertRaises(FileNotFoundError):
            router.uninstall_skill("does-not-exist-xyz-12345")


if __name__ == "__main__":
    unittest.main()
