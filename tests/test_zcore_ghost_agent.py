import json

from zcore.engines.ghost_agent import GhostAgent
from zcore.runtime import RuntimePaths


def test_ghost_agent_openai_call_uses_urllib_and_redacts_prompt(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ZCORE_HOME", str(home / ".zcore"))
    monkeypatch.setenv("KITCLAW_LLM_API_KEY", "test-key")

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
                "[privacy]",
                "redact_before_send = true",
                "redact_file_paths = true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "hello from API"}}]}).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["timeout"] = timeout
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("zcore.engines.ghost_agent.request.urlopen", fake_urlopen)

    agent = GhostAgent(paths)
    text = agent.call("token=secret\nPath: /home/alice/project\nSay hello")

    assert text == "hello from API"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["timeout"] == 1
    body = captured["body"]
    assert "[REDACTED]" in body["messages"][0]["content"]
    assert "/home/[USER]/project" in body["messages"][0]["content"]


def test_ghost_agent_falls_back_when_api_key_missing(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ZCORE_HOME", str(home / ".zcore"))

    paths = RuntimePaths.discover()
    paths.ensure_runtime_dirs()
    paths.config_path.write_text(
        "\n".join(
            [
                "[llm_backend]",
                "enabled = true",
                'provider = "openai"',
                'model = "gpt-4o-mini"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    agent = GhostAgent(paths)
    response = agent.generate("summarize this", fallback_text="fallback summary")

    assert response["mode"] == "fallback"
    assert response["reason"] == "missing_api_key"
    assert response["text"] == "fallback summary"


def test_ghost_agent_trims_prompt_before_request(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ZCORE_HOME", str(home / ".zcore"))
    monkeypatch.setenv("KITCLAW_LLM_API_KEY", "test-key")

    paths = RuntimePaths.discover()
    paths.ensure_runtime_dirs()
    paths.config_path.write_text(
        "\n".join(
            [
                "[llm_backend]",
                "enabled = true",
                'provider = "openai"',
                'model = "gpt-4o"',
                "timeout = 1",
                "retry_max = 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "trimmed ok"}}]}).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("zcore.engines.ghost_agent.request.urlopen", fake_urlopen)
    agent = GhostAgent(paths)
    monkeypatch.setattr(agent, "max_prompt_tokens", lambda: 500)

    prompt = "HEADER\n" + ("A" * 10000) + "\nTAIL\n" + ("B" * 10000)
    text = agent.call(prompt)

    assert text == "trimmed ok"
    sent_prompt = captured["body"]["messages"][0]["content"]
    assert "[Prompt trimmed to fit Ghost Agent context window.]" in sent_prompt
    assert "HEADER" in sent_prompt
    assert "TAIL" in sent_prompt
