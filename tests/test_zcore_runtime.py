from pathlib import Path

from zcore.compat.legacy_skills import resolve_legacy_script
from zcore.config import config_permissions_ok
from zcore.runtime import RuntimePaths


def test_runtime_paths_follow_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ZCORE_HOME", raising=False)
    monkeypatch.delenv("KITCLAW_HOME", raising=False)
    monkeypatch.setenv("AI_MEMORY_DIR", str(home / ".ai-memory"))
    monkeypatch.setenv("AI_SKILLS_DIR", str(home / ".ai-skills"))

    paths = RuntimePaths.discover()

    assert paths.base_dir == home / ".zcore"
    assert paths.memory_dir == home / ".ai-memory"


def test_legacy_script_resolves_from_ai_skills(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    skill_script = home / ".ai-skills" / "memory-manager" / "scripts" / "memory-search.py"
    skill_script.parent.mkdir(parents=True)
    skill_script.write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_SKILLS_DIR", str(home / ".ai-skills"))

    resolved = resolve_legacy_script("memory-manager", "memory-search.py")

    assert resolved == skill_script


def test_config_permissions_ok_detects_private_mode(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ZCORE_HOME", str(home / ".zcore"))
    paths = RuntimePaths.discover()
    paths.ensure_runtime_dirs()
    paths.config_path.write_text("[core]\nversion = \"2.0\"\n", encoding="utf-8")
    paths.config_path.chmod(0o600)

    assert config_permissions_ok(paths) is True
