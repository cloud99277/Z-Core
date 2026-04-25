import json
import os
import subprocess
import sys
from pathlib import Path

from tests.helpers import run_zcore


def test_init_creates_runtime_files(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    proc = run_zcore("init", "--json", home=home)

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert (home / ".zcore" / "config.toml").exists()
    assert (home / ".zcore" / "shared-rules.yaml").exists()


def test_status_reports_missing_init_then_present_after_bootstrap(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    before = run_zcore("status", "--json", home=home)
    assert before.returncode == 0, before.stderr
    before_payload = json.loads(before.stdout)
    assert before_payload["needs_init"] is True
    assert before_payload["ghost_agent"]["mode"] == "fallback"

    init_proc = run_zcore("init", "--json", home=home)
    assert init_proc.returncode == 0, init_proc.stderr

    after = run_zcore("status", "--json", home=home)
    assert after.returncode == 0, after.stderr
    after_payload = json.loads(after.stdout)
    assert after_payload["needs_init"] is False
    assert after_payload["config_exists"] is True
    assert after_payload["file_locking"]["available"] is True


def test_doctor_reports_healthy_after_init(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    init_proc = run_zcore("init", "--json", home=home)
    assert init_proc.returncode == 0, init_proc.stderr

    doctor = run_zcore("doctor", "--json", home=home)
    assert doctor.returncode == 0, doctor.stderr
    payload = json.loads(doctor.stdout)
    assert payload["healthy"] is True


def test_session_start_and_end_write_index_and_snapshot(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    init_proc = run_zcore("init", "--json", home=home)
    assert init_proc.returncode == 0, init_proc.stderr

    start = run_zcore(
        "session",
        "start",
        "--project",
        "kitclaw",
        "--agent",
        "codex",
        "--json",
        home=home,
    )
    assert start.returncode == 0, start.stderr
    session = json.loads(start.stdout)
    session_id = session["session_id"]

    messages_path = tmp_path / "messages.json"
    messages_path.write_text(
        json.dumps(
            [
                {"role": "user", "content": "[decision] Use zcore as the package root."},
                {"role": "assistant", "content": "Captured."},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    end = run_zcore(
        "session",
        "end",
        "--session-id",
        session_id,
        "--messages",
        str(messages_path),
        "--json",
        home=home,
    )
    assert end.returncode == 0, end.stderr
    payload = json.loads(end.stdout)
    assert payload["status"] == "completed"

    session_dir = home / ".zcore" / "sessions" / session_id
    assert (session_dir / "context.json.gz").exists()
    assert (session_dir / "context.md").exists()
    assert (session_dir / "memories.json").exists()


def test_governance_check_fails_fast_without_tty(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    proc = run_zcore(
        "governance-check",
        "--action",
        "file.write",
        "--target",
        "src/app.py",
        "--json",
        home=home,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert "mode=non_tty" in payload["error"]


def test_context_analyze_and_compact_cli_fallback(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    init_proc = run_zcore("init", "--json", home=home)
    assert init_proc.returncode == 0, init_proc.stderr

    messages_path = tmp_path / "messages.json"
    messages_path.write_text(
        json.dumps(
            [
                {"role": "user", "content": "Implement compact flow."},
                {"role": "assistant", "content": "[decision] Use fallback summary when no API key."},
                {"role": "assistant", "content": "TODO: add CLI smoke tests."},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    analyze = run_zcore(
        "context",
        "analyze",
        "--input",
        str(messages_path),
        "--model",
        "sonnet",
        "--json",
        home=home,
    )
    assert analyze.returncode == 0, analyze.stderr
    analyze_payload = json.loads(analyze.stdout)
    assert analyze_payload["total_tokens"] > 0
    assert analyze_payload["urgency"] in {"normal", "warning", "critical"}

    compact = run_zcore(
        "compact",
        "--input",
        str(messages_path),
        "--model",
        "sonnet",
        "--json",
        home=home,
    )
    assert compact.returncode == 0, compact.stderr
    compact_payload = json.loads(compact.stdout)
    assert compact_payload["metadata"]["mode"] == "fallback"
    assert "## 1. Primary Request and Intent" in compact_payload["summary"]


def test_session_resume_latest_list_and_handoff(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    init_proc = run_zcore("init", "--json", home=home)
    assert init_proc.returncode == 0, init_proc.stderr

    start = run_zcore(
        "session",
        "start",
        "--project",
        "kitclaw",
        "--agent",
        "codex",
        "--json",
        home=home,
    )
    assert start.returncode == 0, start.stderr
    session_id = json.loads(start.stdout)["session_id"]

    messages_path = tmp_path / "messages.json"
    messages_path.write_text(
        json.dumps(
            [
                {"role": "user", "content": "Continue the v2 coding phase."},
                {"role": "assistant", "content": "[decision] Use urllib for Ghost Agent transport."},
                {"role": "assistant", "content": "Current state: implementing session handoff."},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    end = run_zcore(
        "session",
        "end",
        "--session-id",
        session_id,
        "--messages",
        str(messages_path),
        "--json",
        home=home,
    )
    assert end.returncode == 0, end.stderr
    end_payload = json.loads(end.stdout)
    assert end_payload["summary"]

    resumed = run_zcore(
        "session",
        "start",
        "--project",
        "kitclaw",
        "--agent",
        "gemini",
        "--resume-latest",
        "--json",
        home=home,
    )
    assert resumed.returncode == 0, resumed.stderr
    resumed_payload = json.loads(resumed.stdout)
    assert resumed_payload["resume_from"] == session_id
    assert "Key Technical Decisions" in resumed_payload["resume_context"]

    listed = run_zcore(
        "session",
        "list",
        "--project",
        "kitclaw",
        "--json",
        home=home,
    )
    assert listed.returncode == 0, listed.stderr
    list_payload = json.loads(listed.stdout)
    assert len(list_payload) == 2

    handoff = run_zcore(
        "session",
        "handoff",
        "--session-id",
        session_id,
        "--to",
        "gemini",
        "--note",
        "Please continue from the latest coding state.",
        "--json",
        home=home,
    )
    assert handoff.returncode == 0, handoff.stderr
    handoff_payload = json.loads(handoff.stdout)
    assert "### Context Summary" in handoff_payload["document"]
    assert "Please continue from the latest coding state." in handoff_payload["document"]


def test_memory_extract_list_search_pending_and_migrate_cli(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    init_proc = run_zcore("init", "--json", home=home)
    assert init_proc.returncode == 0, init_proc.stderr

    messages_path = tmp_path / "messages.json"
    messages_path.write_text(
        json.dumps(
            [
                {"role": "user", "content": "We need a durable decision."},
                {"role": "assistant", "content": "[decision] Use zcore memory CLI"},
                {"role": "assistant", "content": "[fact] Python >=3.11 is required"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    extract = run_zcore(
        "memory",
        "extract",
        "--input",
        str(messages_path),
        "--model",
        "sonnet",
        "--project",
        "kitclaw",
        "--json",
        home=home,
    )
    assert extract.returncode == 0, extract.stderr
    extract_payload = json.loads(extract.stdout)
    assert extract_payload["pending"] == 2

    pending = run_zcore("memory", "pending", "--json", home=home)
    assert pending.returncode == 0, pending.stderr
    pending_payload = json.loads(pending.stdout)
    assert len(pending_payload) == 2

    confirm = run_zcore("memory", "pending", "--confirm", pending_payload[0]["id"], "--json", home=home)
    assert confirm.returncode == 0, confirm.stderr
    confirm_payload = json.loads(confirm.stdout)
    assert confirm_payload["topic"] == "kitclaw"

    listed = run_zcore("memory", "list", "--topic", "kitclaw", "--json", home=home)
    assert listed.returncode == 0, listed.stderr
    listed_payload = json.loads(listed.stdout)
    assert listed_payload[0]["content"]

    search = run_zcore("memory", "search", "--query", "Python", "--json", home=home)
    assert search.returncode == 0, search.stderr
    search_payload = json.loads(search.stdout)
    assert search_payload["l2"] == [] or "Python" in search_payload["l2"][0]["content"]

    whiteboard_path = home / ".ai-memory" / "whiteboard.json"
    whiteboard_path.write_text(
        json.dumps({"entries": [{"type": "fact", "content": "Migrated fact", "project": "kitclaw"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    dry_run = run_zcore("migrate", "--dry-run", "--json", home=home)
    assert dry_run.returncode == 0, dry_run.stderr
    dry_payload = json.loads(dry_run.stdout)
    assert dry_payload["dry_run"] is True


def test_session_end_honors_auto_extract_and_compact_config(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    init_proc = run_zcore("init", "--json", home=home)
    assert init_proc.returncode == 0, init_proc.stderr

    config_path = home / ".zcore" / "config.toml"
    config_text = config_path.read_text(encoding="utf-8")
    config_text = config_text.replace("auto_extract = true", "auto_extract = false")
    config_text = config_text.replace("auto_compact = true", "auto_compact = false")
    config_path.write_text(config_text, encoding="utf-8")

    start = run_zcore("session", "start", "--project", "kitclaw", "--agent", "codex", "--json", home=home)
    session_id = json.loads(start.stdout)["session_id"]
    messages_path = tmp_path / "messages.json"
    messages_path.write_text(
        json.dumps([{"role": "user", "content": "[decision] Config disables automation."}]),
        encoding="utf-8",
    )

    end = run_zcore(
        "session",
        "end",
        "--session-id",
        session_id,
        "--messages",
        str(messages_path),
        "--json",
        home=home,
    )
    assert end.returncode == 0, end.stderr
    session_dir = home / ".zcore" / "sessions" / session_id
    assert (session_dir / "context.json.gz").exists()
    assert not (session_dir / "context.md").exists()
    assert not (session_dir / "memories.json").exists()


def test_json_errors_do_not_emit_tracebacks(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    init_proc = run_zcore("init", "--json", home=home)
    assert init_proc.returncode == 0, init_proc.stderr

    proc = run_zcore("session", "show", "missing-session", "--json", home=home)

    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert "Session not found" in payload["error"]
