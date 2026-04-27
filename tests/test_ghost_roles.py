import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib import error

from tests.helpers import run_zcore
from zcore.engines.ghost_agent import GhostAgent
from zcore.runtime import RuntimePaths


class FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps({"choices": [{"message": {"content": self.text}}]}).encode("utf-8")


class GhostRoleTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.home = Path(self.tempdir.name) / "home"
        self.home.mkdir()
        self.env = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "ZCORE_HOME": str(self.home / ".zcore"),
                "KITCLAW_LLM_API_KEY": "test-key",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tempdir.cleanup()

    def _agent(self) -> GhostAgent:
        paths = RuntimePaths.discover()
        paths.ensure_runtime_dirs()
        paths.config_path.write_text(
            "\n".join(
                [
                    "[llm_backend]",
                    "enabled = true",
                    'provider = "openai"',
                    'model = "gpt-4o-mini"',
                    "timeout = 1",
                    "retry_max = 0",
                    "fallback_on_failure = true",
                    "",
                    "[llm_backend.roles]",
                    'compact = "gpt-role-compact"',
                    'planner = "gpt-role-planner"',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return GhostAgent(paths)

    def test_generate_without_role_uses_default_model(self):
        captured: list[str] = []

        def fake_urlopen(req, timeout):
            body = json.loads(req.data.decode("utf-8"))
            captured.append(body["model"])
            return FakeResponse("default ok")

        with mock.patch("zcore.engines.ghost_agent.request.urlopen", fake_urlopen):
            response = self._agent().generate("hello")

        self.assertEqual(response["text"], "default ok")
        self.assertEqual(response["mode"], "llm")
        self.assertIsNone(response["role"])
        self.assertEqual(captured, ["gpt-4o-mini"])

    def test_generate_with_role_uses_role_model(self):
        captured: list[str] = []

        def fake_urlopen(req, timeout):
            body = json.loads(req.data.decode("utf-8"))
            captured.append(body["model"])
            return FakeResponse("role ok")

        with mock.patch("zcore.engines.ghost_agent.request.urlopen", fake_urlopen):
            response = self._agent().generate("hello", role="compact")

        self.assertEqual(response["text"], "role ok")
        self.assertEqual(response["mode"], "llm")
        self.assertEqual(response["role"], "compact")
        self.assertEqual(captured, ["gpt-role-compact"])

    def test_generate_with_unknown_role_falls_back_to_default_model(self):
        captured: list[str] = []

        def fake_urlopen(req, timeout):
            body = json.loads(req.data.decode("utf-8"))
            captured.append(body["model"])
            return FakeResponse("fallback default ok")

        with mock.patch("zcore.engines.ghost_agent.request.urlopen", fake_urlopen):
            response = self._agent().generate("hello", role="missing")

        self.assertEqual(response["text"], "fallback default ok")
        self.assertEqual(response["mode"], "llm")
        self.assertEqual(response["role"], "missing")
        self.assertEqual(captured, ["gpt-4o-mini"])

    def test_generate_with_failed_role_request_falls_back_to_default_model(self):
        captured: list[str] = []

        def fake_urlopen(req, timeout):
            body = json.loads(req.data.decode("utf-8"))
            captured.append(body["model"])
            if body["model"] == "gpt-role-planner":
                raise error.URLError("role model unavailable")
            return FakeResponse("default after role failure")

        with mock.patch("zcore.engines.ghost_agent.request.urlopen", fake_urlopen):
            response = self._agent().generate("hello", role="planner")

        self.assertEqual(response["text"], "default after role failure")
        self.assertEqual(response["mode"], "llm")
        self.assertEqual(response["role"], "planner")
        self.assertEqual(captured, ["gpt-role-planner", "gpt-4o-mini"])

    def test_ghost_roles_cli_outputs_json(self):
        (self.home / ".zcore").mkdir(parents=True)
        (self.home / ".zcore" / "config.toml").write_text(
            "\n".join(
                [
                    "[llm_backend]",
                    'model = "gpt-4o-mini"',
                    "",
                    "[llm_backend.roles]",
                    'compact = "gpt-role-compact"',
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        proc = run_zcore("ghost", "roles", "--json", home=self.home)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["default_model"], "gpt-4o-mini")
        self.assertEqual(payload["roles"], {"compact": "gpt-role-compact"})


if __name__ == "__main__":
    unittest.main()
