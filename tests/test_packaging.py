from zcore.engines.router import _bundled_skills_dir


def test_bundled_core_skills_are_packaging_visible():
    bundled = _bundled_skills_dir()

    assert bundled.exists()
    assert (bundled / "memory-manager" / "SKILL.md").exists()
    assert len(list(bundled.glob("*/SKILL.md"))) == 17
