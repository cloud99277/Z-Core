import json

from zcore.engines.memory import ExtractionResult, MemoryEngine, TopicStore
from zcore.models.memory import MemoryEntry
from zcore.runtime import RuntimePaths


def test_memory_entry_roundtrip_and_markdown():
    entry = MemoryEntry(type="fact", content="Python >=3.11", topic="kitclaw")

    payload = entry.to_dict()
    restored = MemoryEntry.from_dict(payload)

    assert restored.type == "fact"
    assert restored.to_markdown_line().startswith("- [fact] Python >=3.11")


def test_memory_entry_markdown_roundtrip_preserves_structured_fields():
    entry = MemoryEntry(
        type="decision",
        content="Keep source metadata",
        topic="zcore",
        source="codex",
        source_session="session-1",
        project="Z-Core",
        id="memory-1",
        updated_at="2026-04-25T00:00:00+00:00",
    )

    parsed = MemoryEntry.from_markdown_line(entry.to_markdown_line(), topic="fallback")

    assert parsed is not None
    assert parsed.id == "memory-1"
    assert parsed.topic == "zcore"
    assert parsed.project == "Z-Core"
    assert parsed.source_session == "session-1"
    assert parsed.updated_at == "2026-04-25T00:00:00+00:00"


def test_topic_store_write_read_roundtrip(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ZCORE_HOME", str(home / ".zcore"))
    monkeypatch.setenv("AI_MEMORY_DIR", str(home / ".ai-memory"))

    paths = RuntimePaths.discover()
    paths.ensure_runtime_dirs()
    store = TopicStore(paths)
    entry = MemoryEntry(type="fact", content="Python >=3.11", topic="kitclaw", source="test")

    store.write_entry(entry)
    entries = store.read_topic("kitclaw")

    assert len(entries) == 1
    assert entries[0].content == "Python >=3.11"


def test_memory_engine_dedup_and_auto_topic(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ZCORE_HOME", str(home / ".zcore"))
    monkeypatch.setenv("AI_MEMORY_DIR", str(home / ".ai-memory"))

    paths = RuntimePaths.discover()
    paths.ensure_runtime_dirs()
    engine = MemoryEngine(paths)

    existing = [MemoryEntry(type="fact", content="Python >=3.11 required", topic="kitclaw")]
    candidate = MemoryEntry(
        type="fact",
        content="Python >= 3.11 is required",
        topic="general",
        project="kitclaw",
    )

    assert engine.dedup(candidate, existing) is True
    assert engine.auto_topic(candidate) == "kitclaw"


def test_extract_from_conversation_heuristic_and_pending(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ZCORE_HOME", str(home / ".zcore"))
    monkeypatch.setenv("AI_MEMORY_DIR", str(home / ".ai-memory"))

    paths = RuntimePaths.discover()
    paths.ensure_runtime_dirs()
    config = (
        "[memory_extraction]\n"
        "min_turns_for_extraction = 3\n"
        "auto_admit_threshold = 0.8\n"
        "pending_threshold = 0.5\n"
        "dedup_threshold = 0.85\n"
    )
    paths.config_path.write_text(config, encoding="utf-8")

    engine = MemoryEngine(paths)
    messages = [
        {"role": "user", "content": "Let's settle the runtime."},
        {"role": "assistant", "content": "[fact] Python >=3.11 is required"},
        {"role": "assistant", "content": "[decision] Use zcore package for the CLI"},
    ]

    result = engine.extract_from_conversation(messages, project="kitclaw", agent="codex", session_id="sess-1")

    assert isinstance(result, ExtractionResult)
    assert result.mode == "heuristic"
    assert result.pending == 2
    pending = engine.list_pending()
    assert len(pending) == 2
    assert paths.extraction_log_path.exists()


def test_confirm_pending_and_migrate_v1(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ZCORE_HOME", str(home / ".zcore"))
    monkeypatch.setenv("AI_MEMORY_DIR", str(home / ".ai-memory"))

    paths = RuntimePaths.discover()
    paths.ensure_runtime_dirs()
    paths.config_path.write_text(
        "[memory_extraction]\nauto_admit_threshold = 0.8\npending_threshold = 0.5\ndedup_threshold = 0.85\n",
        encoding="utf-8",
    )
    engine = MemoryEngine(paths)
    pending_entry = MemoryEntry(type="decision", content="Use zcore package", topic="kitclaw", confidence=0.7)
    engine._write_pending([pending_entry.to_dict()])

    confirmed = engine.confirm_pending(pending_entry.id)
    assert confirmed.content == "Use zcore package"
    assert engine.list_entries(topic="kitclaw")[0].content == "Use zcore package"

    paths.whiteboard_path.write_text(
        json.dumps(
            {
                "entries": [
                    {"type": "fact", "content": "KitClaw uses Python", "project": "kitclaw"},
                    {"type": "learning", "content": "Prefer atomic writes", "project": "kitclaw"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    payload = engine.migrate_v1(dry_run=False)
    assert payload["migrated"] == 2
    assert (paths.memory_dir / "whiteboard.v1.json.bak").exists()
