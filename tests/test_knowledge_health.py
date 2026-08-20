from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from tests.helpers import run_zcore


def _manifest(
    *,
    status: str = "healthy",
    last_successful_ingest_at: datetime | None = None,
    serving_generation: str | None = None,
    serving_revision: str | None = None,
    serving_complete: bool = False,
) -> dict[str, object]:
    return {
        "schema_version": "zcore.knowledge.health/v1",
        "provider": "agent-os-knowledge-base",
        "status": status,
        "corpus": {
            "id": "l3-governed",
            "root": "/home/private-user/knowledge-base",
            "revision": "sha256:revision-20260806",
            "document_count": 12,
        },
        "index": {
            "indexed_document_count": 12,
            "chunk_count": 28,
            "last_successful_ingest_at": (last_successful_ingest_at or datetime.now(UTC)).isoformat(),
            "serving_generation": serving_generation,
            "serving_revision": serving_revision,
            "serving_complete": serving_complete,
            "embedding_model": "BAAI/bge-small-zh-v1.5",
            "embedding_model_version": "1.5",
        },
        "capabilities": ["fts", "semantic", "hybrid"],
        "last_failure": None,
        "document_preview": "private document content must never reach health output",
    }


def _configure_manifest(home, manifest_path) -> None:
    config_path = home / ".zcore" / "config.toml"
    config_text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        config_text.replace('health_manifest_path = ""', f'health_manifest_path = "{manifest_path}"'),
        encoding="utf-8",
    )


def test_knowledge_health_reports_sanitized_healthy_external_manifest(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert run_zcore("init", "--json", home=home).returncode == 0
    manifest_path = tmp_path / "external" / "knowledge-health.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps(_manifest(), ensure_ascii=False), encoding="utf-8")
    _configure_manifest(home, manifest_path)

    proc = run_zcore("knowledge", "health", "--json", home=home)

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["provider"] == "external_readonly"
    assert payload["index_owner"] == "agent-os-knowledge-base"
    assert payload["status"] == "healthy"
    assert payload["freshness"] == "current"
    assert payload["manifest_schema_version"] == "zcore.knowledge.health/v1"
    assert payload["provider_capabilities"] == ["health_readonly"]
    assert payload["corpus"]["document_count"] == 12
    assert payload["index"]["chunk_count"] == 28
    assert str(manifest_path) not in proc.stdout
    assert "/home/private-user/knowledge-base" not in proc.stdout
    assert "private document content" not in proc.stdout


def test_knowledge_health_marks_missing_and_invalid_manifest_as_failed(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    missing = run_zcore("knowledge", "health", "--json", home=home)

    assert missing.returncode == 0, missing.stderr
    missing_payload = json.loads(missing.stdout)
    assert missing_payload["status"] == "failed"
    assert missing_payload["freshness"] == "unknown"
    assert missing_payload["diagnostic_code"] == "manifest_missing"
    assert missing_payload["warnings"] == ["knowledge health manifest is missing"]

    assert run_zcore("init", "--json", home=home).returncode == 0
    manifest_path = tmp_path / "external" / "bad-manifest.json"
    manifest_path.parent.mkdir()
    invalid_manifest = _manifest()
    invalid_manifest["schema_version"] = "zcore.knowledge.health/v2"
    manifest_path.write_text(json.dumps(invalid_manifest), encoding="utf-8")
    _configure_manifest(home, manifest_path)

    invalid = run_zcore("knowledge", "health", "--json", home=home)

    assert invalid.returncode == 0, invalid.stderr
    invalid_payload = json.loads(invalid.stdout)
    assert invalid_payload["status"] == "failed"
    assert invalid_payload["diagnostic_code"] == "manifest_invalid"
    assert invalid_payload["warnings"] == ["knowledge health manifest is invalid"]
    assert str(manifest_path) not in invalid.stdout


def test_knowledge_health_remains_available_without_registry_command(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert run_zcore("init", "--json", home=home).returncode == 0

    health = run_zcore("knowledge", "health", "--json", home=home)

    assert health.returncode == 0, health.stderr
    assert json.loads(health.stdout)["diagnostic_code"] == "manifest_missing"

    registry = run_zcore("knowledge", "registry", "validate", "--json", home=home)

    assert registry.returncode == 2
    assert "invalid choice: 'registry'" in registry.stderr
    assert "corpus_registry_path" not in (home / ".zcore" / "config.toml").read_text(encoding="utf-8")


def test_knowledge_health_only_allows_stale_with_verified_serving_generation(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert run_zcore("init", "--json", home=home).returncode == 0
    manifest_path = tmp_path / "external" / "knowledge-health.json"
    manifest_path.parent.mkdir()
    _configure_manifest(home, manifest_path)
    stale_time = datetime.now(UTC) - timedelta(days=2)

    unverified = _manifest(last_successful_ingest_at=stale_time)
    manifest_path.write_text(json.dumps(unverified), encoding="utf-8")
    unsafe_stale = run_zcore("knowledge", "health", "--json", home=home)

    assert unsafe_stale.returncode == 0, unsafe_stale.stderr
    unsafe_payload = json.loads(unsafe_stale.stdout)
    assert unsafe_payload["status"] == "failed"
    assert unsafe_payload["freshness"] == "unknown"
    assert unsafe_payload["diagnostic_code"] == "unverified_serving_generation"

    in_place = _manifest(
        last_successful_ingest_at=stale_time,
        serving_generation="generation-20260806",
        serving_revision="sha256:revision-20260806",
        serving_complete=True,
    )
    manifest_path.write_text(json.dumps(in_place), encoding="utf-8")
    in_place_stale = run_zcore("knowledge", "health", "--json", home=home)

    assert in_place_stale.returncode == 0, in_place_stale.stderr
    in_place_payload = json.loads(in_place_stale.stdout)
    assert in_place_payload["status"] == "failed"
    assert in_place_payload["freshness"] == "unknown"

    verified = _manifest(
        last_successful_ingest_at=stale_time,
        serving_generation="generation-20260806",
        serving_revision="sha256:revision-20260805",
        serving_complete=True,
    )
    manifest_path.write_text(json.dumps(verified), encoding="utf-8")
    safe_stale = run_zcore("knowledge", "health", "--json", home=home)

    assert safe_stale.returncode == 0, safe_stale.stderr
    safe_payload = json.loads(safe_stale.stdout)
    assert safe_payload["status"] == "degraded"
    assert safe_payload["freshness"] == "stale"
    assert safe_payload["index"]["serving_complete"] is True
    assert safe_payload["index"]["serving_generation"] == "generation-20260806"


def test_knowledge_health_failed_owner_can_only_fall_back_to_verified_generation(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert run_zcore("init", "--json", home=home).returncode == 0
    manifest_path = tmp_path / "external" / "knowledge-health.json"
    manifest_path.parent.mkdir()
    _configure_manifest(home, manifest_path)

    failed_manifest = _manifest(status="failed")
    failed_manifest["last_failure"] = {"code": "embedding_failure"}
    manifest_path.write_text(json.dumps(failed_manifest), encoding="utf-8")
    failed = run_zcore("knowledge", "health", "--json", home=home)

    failed_payload = json.loads(failed.stdout)
    assert failed_payload["status"] == "failed"
    assert failed_payload["last_failure_code"] == "embedding_failure"

    no_successful_ingest_manifest = _manifest(
        status="failed",
        serving_generation="generation-20260806",
        serving_revision="sha256:revision-20260805",
        serving_complete=True,
    )
    no_successful_ingest_manifest["index"]["last_successful_ingest_at"] = None
    no_successful_ingest_manifest["last_failure"] = {"code": "embedding_failure"}
    manifest_path.write_text(json.dumps(no_successful_ingest_manifest), encoding="utf-8")
    no_successful_ingest = run_zcore("knowledge", "health", "--json", home=home)

    no_successful_ingest_payload = json.loads(no_successful_ingest.stdout)
    assert no_successful_ingest_payload["status"] == "failed"
    assert no_successful_ingest_payload["freshness"] == "unknown"

    safe_failed_manifest = _manifest(
        status="failed",
        serving_generation="generation-20260806",
        serving_revision="sha256:revision-20260805",
        serving_complete=True,
    )
    safe_failed_manifest["last_failure"] = {"code": "embedding_failure"}
    manifest_path.write_text(json.dumps(safe_failed_manifest), encoding="utf-8")
    safe_failed = run_zcore("knowledge", "health", "--json", home=home)

    safe_payload = json.loads(safe_failed.stdout)
    assert safe_payload["status"] == "degraded"
    assert safe_payload["freshness"] == "stale"


def test_external_readonly_freezes_index_writes_and_automatic_l2_admission(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert run_zcore("init", "--json", home=home).returncode == 0

    private_source = tmp_path / "private-source"
    index = run_zcore("knowledge", "index", "--path", str(private_source), "--json", home=home)

    assert index.returncode == 1
    index_payload = json.loads(index.stdout)
    assert index_payload["provider"] == "external_readonly"
    assert "disabled" in index_payload["error"]
    assert str(private_source) not in index.stdout
    assert not (home / ".lancedb" / "knowledge").exists()

    config_path = home / ".zcore" / "config.toml"
    config_text = config_path.read_text(encoding="utf-8")
    config_text = config_text.replace("auto_admit_threshold = 0.8", "auto_admit_threshold = 0.0")
    config_text = config_text.replace("pending_threshold = 0.5", "pending_threshold = 0.99")
    config_path.write_text(config_text, encoding="utf-8")
    messages_path = tmp_path / "messages.json"
    messages_path.write_text(
        json.dumps(
            [
                {"role": "user", "content": "[decision] Keep automatic admissions in candidates."},
                {"role": "assistant", "content": "Acknowledged."},
                {"role": "user", "content": "Do not bypass the freeze."},
            ]
        ),
        encoding="utf-8",
    )

    extracted = run_zcore(
        "memory",
        "extract",
        "--input",
        str(messages_path),
        "--model",
        "test",
        "--json",
        home=home,
    )

    assert extracted.returncode == 0, extracted.stderr
    extraction_payload = json.loads(extracted.stdout)
    assert extraction_payload["admitted"] == 0
    assert extraction_payload["pending"] == 1
    pending = run_zcore("memory", "pending", "--json", home=home)
    pending_payload = json.loads(pending.stdout)
    assert len(pending_payload) == 1
    assert not (home / ".ai-memory" / "topics" / "general.md").exists()

    manual = run_zcore("memory", "write", "Explicit writes remain allowed.", "--json", home=home)
    assert manual.returncode == 0, manual.stderr
    assert (home / ".ai-memory" / "topics" / "general.md").exists()
    confirmed = run_zcore("memory", "pending", "--confirm", pending_payload[0]["id"], "--json", home=home)
    assert confirmed.returncode == 0, confirmed.stderr


def test_admission_safety_freeze_has_no_local_provider_bypass(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert run_zcore("init", "--json", home=home).returncode == 0
    config_path = home / ".zcore" / "config.toml"
    config_text = config_path.read_text(encoding="utf-8")
    config_text = config_text.replace('provider = "external_readonly"', 'provider = "local"')
    config_text = config_text.replace("auto_admit_threshold = 0.8", "auto_admit_threshold = 0.0")
    config_text = config_text.replace("pending_threshold = 0.5", "pending_threshold = 0.99")
    config_path.write_text(config_text, encoding="utf-8")
    messages_path = tmp_path / "messages.json"
    messages_path.write_text(
        json.dumps(
            [
                {"role": "user", "content": "[decision] Local provider cannot bypass admission safety."},
                {"role": "assistant", "content": "Acknowledged."},
                {"role": "user", "content": "Keep it pending."},
            ]
        ),
        encoding="utf-8",
    )

    extracted = run_zcore(
        "memory",
        "extract",
        "--input",
        str(messages_path),
        "--model",
        "test",
        "--json",
        home=home,
    )

    assert extracted.returncode == 0, extracted.stderr
    payload = json.loads(extracted.stdout)
    assert payload["admitted"] == 0
    assert payload["pending"] == 1
    assert not (home / ".ai-memory" / "topics" / "general.md").exists()


def test_session_end_keeps_automatic_high_confidence_entry_out_of_l2(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert run_zcore("init", "--json", home=home).returncode == 0
    config_path = home / ".zcore" / "config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("auto_admit_threshold = 0.8", "auto_admit_threshold = 0.0"),
        encoding="utf-8",
    )

    baseline = run_zcore("memory", "write", "Existing L2 entry.", "--json", home=home)
    assert baseline.returncode == 0, baseline.stderr
    l2_path = home / ".ai-memory" / "topics" / "general.md"
    l2_hash_before = hashlib.sha256(l2_path.read_bytes()).hexdigest()
    started = run_zcore("session", "start", "--project", "zcore", "--agent", "codex", "--json", home=home)
    assert started.returncode == 0, started.stderr
    session_id = json.loads(started.stdout)["session_id"]
    messages_path = tmp_path / "messages.json"
    messages_path.write_text(
        json.dumps(
            [
                {"role": "user", "content": "[decision] Session end must not admit automatically."},
                {"role": "assistant", "content": "Acknowledged."},
                {"role": "user", "content": "Freeze the automatic L2 path."},
            ]
        ),
        encoding="utf-8",
    )

    ended = run_zcore(
        "session",
        "end",
        "--session-id",
        session_id,
        "--messages",
        str(messages_path),
        "--no-compact",
        "--json",
        home=home,
    )

    assert ended.returncode == 0, ended.stderr
    session_memories = json.loads((home / ".zcore" / "sessions" / session_id / "memories.json").read_text(encoding="utf-8"))
    assert session_memories["admitted"] == 0
    assert session_memories["pending"] == 1
    assert hashlib.sha256(l2_path.read_bytes()).hexdigest() == l2_hash_before
    pending = run_zcore("memory", "pending", "--json", home=home)
    assert len(json.loads(pending.stdout)) == 1
