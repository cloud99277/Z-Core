import json

from zcore.engines.context import ContextEngine


def test_context_engine_should_compact_thresholds(monkeypatch):
    engine = ContextEngine()
    messages = [{"role": "user", "content": "hello"}]

    monkeypatch.setattr(engine, "_estimate_messages_tokens", lambda _messages, _model: 50_000)
    assert engine.should_compact(messages, "sonnet") is False

    monkeypatch.setattr(engine, "_estimate_messages_tokens", lambda _messages, _model: 150_000)
    assert engine.should_compact(messages, "sonnet") is True


def test_context_engine_prompt_contains_required_sections():
    engine = ContextEngine()
    prompt = engine.get_compact_prompt(
        [
            {"role": "user", "content": "Please summarize the project state."},
            {"role": "assistant", "content": "Working on it."},
        ]
    )

    assert "## 1. Primary Request and Intent" in prompt
    assert "## 6. Immediate Next Steps" in prompt
    assert "## Conversation Transcript" in prompt


def test_context_engine_compact_fallback_returns_structured_summary():
    engine = ContextEngine()
    result = engine.apply_compact(
        [
            {"role": "user", "content": "Implement the CLI flow."},
            {"role": "assistant", "content": "[decision] Use argparse first."},
            {"role": "assistant", "content": "TODO: add smoke tests."},
        ],
        model="sonnet",
    )

    assert result.metadata["mode"] == "fallback"
    assert "## 1. Primary Request and Intent" in result.summary
    assert "## 4. Open Issues and Blockers" in result.summary
    assert result.original_token_count > 0
    assert result.compacted_token_count > 0
    assert json.loads(json.dumps(result.to_dict(), ensure_ascii=False))["metadata"]["mode"] == "fallback"


def test_context_engine_trims_compact_prompt_to_budget():
    engine = ContextEngine()
    messages = [
        {"role": "user", "content": f"head-{index} " + ("A" * 4000)}
        for index in range(20)
    ]

    prompt = engine.get_compact_prompt(messages, max_prompt_tokens=1200, target_model="gpt-4o")

    assert "Transcript trimmed to fit Ghost Agent context window" in prompt
    assert "head-0" in prompt
    assert "head-19" in prompt
    assert len(prompt) < sum(len(item["content"]) for item in messages)
