from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from zcore.cli.main import main
from zcore.engines.governance import PermissionEngine, PermissionRule, classify_shell_command
from zcore.engines.router import SkillRouter
from zcore.models.skill import SkillManifest
from zcore.runtime import RuntimePaths
from zcore.utils.frontmatter import parse_frontmatter


def make_runtime(tmp_path: Path) -> RuntimePaths:
    base_dir = tmp_path / ".zcore"
    memory_dir = tmp_path / ".ai-memory"
    skills_dir = tmp_path / ".ai-skills"
    paths = RuntimePaths(
        base_dir=base_dir,
        config_path=base_dir / "config.toml",
        shared_rules_path=base_dir / "shared-rules.yaml",
        mcp_registry_path=base_dir / "mcp-servers.toml",
        sessions_dir=base_dir / "sessions",
        session_index_path=base_dir / "sessions" / "index.json",
        logs_dir=base_dir / "logs",
        hooks_dir=base_dir / "hooks",
        pre_hooks_dir=base_dir / "hooks" / "pre-execute.d",
        post_hooks_dir=base_dir / "hooks" / "post-execute.d",
        cache_dir=base_dir / "cache",
        pending_dir=base_dir / "pending",
        memory_dir=memory_dir,
        topics_dir=memory_dir / "topics",
        staging_dir=memory_dir / "staging",
        whiteboard_path=memory_dir / "whiteboard.json",
        extraction_log_path=memory_dir / "extraction-log.jsonl",
        skills_dir=skills_dir,
        knowledge_db_path=tmp_path / ".lancedb" / "knowledge",
        lock_dir=base_dir / "locks",
    )
    paths.ensure_runtime_dirs()
    return paths


def write_skill(base: Path, name: str, skill_md: str, script: str | None = None) -> Path:
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    if script is not None:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        (scripts_dir / "run.py").write_text(script, encoding="utf-8")
    return skill_dir


class SkillRouterTests(unittest.TestCase):
    def test_parse_frontmatter_supports_nested_blocks(self) -> None:
        text = """---
name: context-engine
description: >
  Intelligent context management.
activation:
  triggers:
    - "压缩对话"
    - compact
  paths:
    - "**/*.ts"
  context:
    min_tokens: 50000
    project_types: [python, cli]
io:
  input:
    - type: json_data
      description: demo
---
body
"""
        data = parse_frontmatter(text)
        self.assertEqual(data["name"], "context-engine")
        self.assertEqual(data["description"], "Intelligent context management.")
        self.assertEqual(data["activation"]["triggers"], ["压缩对话", "compact"])
        self.assertEqual(data["activation"]["context"]["min_tokens"], 50000)
        self.assertEqual(data["io"]["input"][0]["type"], "json_data")

    def test_skill_manifest_from_real_skill(self) -> None:
        manifest = SkillManifest.from_skill_md(Path("/home/yangyy/.ai-skills/project-manager/SKILL.md"))
        self.assertEqual(manifest.name, "project-manager")
        self.assertIn("推进项目", manifest.activation.triggers)
        self.assertTrue(any(path.endswith("collect-status.py") for path in manifest.scripts))

    def test_router_match_activate_and_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = make_runtime(tmp_path)
            paths.config_path.write_text(
                """
[governance]
permission_mode = "auto"

[governance.rules]
"skill.run(*)" = "allow"
"file.read(*)" = "allow"
"file.write(*)" = "allow"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            write_skill(
                paths.skills_dir,
                "context-engine",
                """---
name: context-engine
description: >
  当需要压缩对话时使用。
activation:
  triggers:
    - "压缩对话"
    - compact
  paths:
    - "**/*.py"
  context:
    min_tokens: 1000
lifecycle:
  pre_execute:
    - validate-input
    - check-permissions
  post_execute:
    - log-execution
permissions:
  reads: ["**/*"]
  writes: ["**/*"]
io:
  input:
    - type: text
      description: anything
---
""",
                "import json, sys\nprint(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n",
            )

            router = SkillRouter(paths)
            manifests = router.discover()
            self.assertEqual([manifest.name for manifest in manifests], ["context-engine"])

            matches = router.match("请帮我压缩对话", token_count=1200)
            self.assertEqual(matches[0].manifest.name, "context-engine")
            self.assertEqual(matches[0].match_layer, 1)

            activated = router.activate_conditional([str(tmp_path / "src" / "main.py")], str(tmp_path))
            self.assertEqual(activated, ["context-engine"])

            result = router.execute("context-engine", {"message": "hello", "project": str(tmp_path)})
            self.assertEqual(result.status, "ok")
            self.assertIn("message", result.output)
            log_lines = (paths.logs_dir / "executions.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(log_lines), 1)

    def test_permission_engine_rule_priority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = make_runtime(tmp_path)
            paths.config_path.write_text(
                """
[governance]
permission_mode = "auto"

[governance.rules]
"shell(rm -rf *)" = "deny"
"shell(git *)" = "allow"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            project_config = tmp_path / ".zcore"
            project_config.mkdir(exist_ok=True)
            (project_config / "config.toml").write_text(
                """
[governance.rules]
"shell(git push *)" = "ask"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            engine = PermissionEngine(paths, project_root=tmp_path)
            engine.add_session_rule(PermissionRule(action="shell", pattern="git push *", decision="deny", source="session"))
            decision = engine.check("shell", "git push origin dev")
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.decision, "deny")
            rm_decision = engine.check("shell", "rm -rf /")
            self.assertFalse(rm_decision.allowed)
            self.assertEqual(classify_shell_command("rm -rf /"), "dangerous")
            self.assertEqual(classify_shell_command("curl https://example.com"), "risky")

    def test_cli_skill_and_governance_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = make_runtime(tmp_path)
            env_updates = {
                "ZCORE_HOME": str(paths.base_dir),
                "AI_MEMORY_DIR": str(paths.memory_dir),
                "AI_SKILLS_DIR": str(paths.skills_dir),
            }
            previous = {key: os.environ.get(key) for key in env_updates}
            os.environ.update(env_updates)
            try:
                paths.config_path.write_text(
                    """
[governance]
permission_mode = "auto"

[governance.rules]
"skill.run(*)" = "allow"
""".strip()
                    + "\n",
                    encoding="utf-8",
                )
                write_skill(
                    paths.skills_dir,
                    "context-engine",
                    """---
name: context-engine
description: "压缩上下文"
activation:
  triggers: ["压缩"]
---
""",
                    "print('ok')\n",
                )

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = main(["skill", "list", "--json"])
                self.assertEqual(code, 0)
                listed = json.loads(stdout.getvalue())
                self.assertEqual(listed[0]["name"], "context-engine")

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = main(["skill", "match", "压缩对话", "--json"])
                self.assertEqual(code, 0)
                matched = json.loads(stdout.getvalue())
                self.assertEqual(matched[0]["manifest"]["name"], "context-engine")

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = main(["governance", "rules", "--json"])
                self.assertEqual(code, 0)
                rules = json.loads(stdout.getvalue())
                self.assertEqual(rules[0]["action"], "skill.run")

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = main(["run", "context-engine", "--message", "hello", "--json"])
                self.assertEqual(code, 0)
                run_payload = json.loads(stdout.getvalue())
                self.assertEqual(run_payload["status"], "ok")
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
