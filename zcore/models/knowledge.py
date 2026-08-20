from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


HEALTH_MANIFEST_SCHEMA_VERSION = "zcore.knowledge.health/v1"
HEALTH_STATUSES = frozenset({"healthy", "degraded", "failed"})
KNOWLEDGE_CAPABILITIES = frozenset({"fts", "semantic", "hybrid"})

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*(?:/[A-Za-z0-9][A-Za-z0-9_.:-]*)?$")


@dataclass(frozen=True)
class KnowledgeHealthManifest:
    """Validated public health facts published by an external index owner.

    ``corpus_root`` is retained only while parsing the external contract. It is
    deliberately excluded from all report payloads because a health command
    must not reveal a private filesystem layout.
    """

    schema_version: str
    provider: str
    status: str
    corpus_id: str
    corpus_root: str
    corpus_revision: str
    document_count: int
    indexed_document_count: int
    chunk_count: int
    last_successful_ingest_at: datetime | None
    serving_generation: str | None
    serving_revision: str | None
    serving_complete: bool
    embedding_model: str
    embedding_model_version: str
    capabilities: tuple[str, ...]
    last_failure_code: str | None

    @classmethod
    def from_dict(cls, payload: object) -> "KnowledgeHealthManifest":
        if not isinstance(payload, dict):
            raise ValueError("knowledge health manifest must be a JSON object")

        schema_version = _required_string(payload, "schema_version")
        if schema_version != HEALTH_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported knowledge health manifest schema version")

        status = _required_identifier(payload, "status")
        if status not in HEALTH_STATUSES:
            raise ValueError("knowledge health manifest has an invalid status")

        provider = _required_identifier(payload, "provider")
        corpus = _required_object(payload, "corpus")
        index = _required_object(payload, "index")
        corpus_id = _required_identifier(corpus, "id")
        corpus_root = _required_string(corpus, "root")
        corpus_revision = _required_identifier(corpus, "revision")
        document_count = _required_nonnegative_int(corpus, "document_count")
        indexed_document_count = _required_nonnegative_int(index, "indexed_document_count")
        chunk_count = _required_nonnegative_int(index, "chunk_count")
        last_successful_ingest_at = _optional_timestamp(index, "last_successful_ingest_at")
        serving_generation = _optional_identifier(index, "serving_generation")
        serving_revision = _optional_identifier(index, "serving_revision")
        serving_complete = _optional_bool(index, "serving_complete", default=False)
        embedding_model = _required_model_identifier(index, "embedding_model")
        embedding_model_version = _required_identifier(index, "embedding_model_version")
        capabilities = _required_capabilities(payload)
        last_failure_code = _optional_failure_code(payload.get("last_failure"))

        if status == "healthy" and last_successful_ingest_at is None:
            raise ValueError("healthy knowledge health manifests require last_successful_ingest_at")

        return cls(
            schema_version=schema_version,
            provider=provider,
            status=status,
            corpus_id=corpus_id,
            corpus_root=corpus_root,
            corpus_revision=corpus_revision,
            document_count=document_count,
            indexed_document_count=indexed_document_count,
            chunk_count=chunk_count,
            last_successful_ingest_at=last_successful_ingest_at,
            serving_generation=serving_generation,
            serving_revision=serving_revision,
            serving_complete=serving_complete,
            embedding_model=embedding_model,
            embedding_model_version=embedding_model_version,
            capabilities=capabilities,
            last_failure_code=last_failure_code,
        )

    @property
    def can_serve_stale(self) -> bool:
        return (
            self.last_successful_ingest_at is not None
            and self.serving_complete
            and self.serving_generation is not None
            and self.serving_revision is not None
            and self.serving_revision != self.corpus_revision
        )


@dataclass(frozen=True)
class KnowledgeHealthReport:
    """Sanitized health report emitted by ``zcore knowledge health``."""

    provider: str
    status: str
    freshness: str
    warnings: tuple[str, ...]
    manifest_schema_version: str | None = None
    index_owner: str | None = None
    corpus_id: str | None = None
    corpus_revision: str | None = None
    document_count: int | None = None
    indexed_document_count: int | None = None
    chunk_count: int | None = None
    last_successful_ingest_at: str | None = None
    serving_generation: str | None = None
    serving_revision: str | None = None
    serving_complete: bool = False
    embedding_model: str | None = None
    embedding_model_version: str | None = None
    capabilities: tuple[str, ...] = ()
    provider_capabilities: tuple[str, ...] = ("health_readonly",)
    last_failure_code: str | None = None
    diagnostic_code: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.status != "failed",
            "provider": self.provider,
            "status": self.status,
            "freshness": self.freshness,
            "manifest_schema_version": self.manifest_schema_version,
            "index_owner": self.index_owner,
            "corpus": {
                "id": self.corpus_id,
                "revision": self.corpus_revision,
                "document_count": self.document_count,
            },
            "index": {
                "indexed_document_count": self.indexed_document_count,
                "chunk_count": self.chunk_count,
                "last_successful_ingest_at": self.last_successful_ingest_at,
                "embedding_model": self.embedding_model,
                "embedding_model_version": self.embedding_model_version,
                "serving_generation": self.serving_generation,
                "serving_revision": self.serving_revision,
                "serving_complete": self.serving_complete,
            },
            "capabilities": list(self.capabilities),
            "provider_capabilities": list(self.provider_capabilities),
            "last_failure_code": self.last_failure_code,
            "diagnostic_code": self.diagnostic_code,
            "warnings": list(self.warnings),
        }


def _required_object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"knowledge health manifest requires an object for {key}")
    return value


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"knowledge health manifest requires a non-empty {key}")
    return value.strip()


def _required_identifier(payload: dict[str, Any], key: str) -> str:
    value = _required_string(payload, key)
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"knowledge health manifest has an unsafe {key}")
    return value


def _required_model_identifier(payload: dict[str, Any], key: str) -> str:
    value = _required_string(payload, key)
    if not _MODEL_RE.fullmatch(value):
        raise ValueError(f"knowledge health manifest has an unsafe {key}")
    return value


def _optional_identifier(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value.strip()):
        raise ValueError(f"knowledge health manifest has an unsafe {key}")
    return value.strip()


def _optional_bool(payload: dict[str, Any], key: str, *, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"knowledge health manifest has an invalid {key}")
    return value


def _required_nonnegative_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"knowledge health manifest requires a non-negative integer for {key}")
    return value


def _optional_timestamp(payload: dict[str, Any], key: str) -> datetime | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"knowledge health manifest has an invalid {key}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"knowledge health manifest has an invalid {key}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"knowledge health manifest has an invalid {key}")
    return parsed.astimezone(UTC)


def _required_capabilities(payload: dict[str, Any]) -> tuple[str, ...]:
    value = payload.get("capabilities")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("knowledge health manifest requires a capabilities list")
    capabilities = tuple(dict.fromkeys(item.strip() for item in value if item.strip()))
    if any(item not in KNOWLEDGE_CAPABILITIES for item in capabilities):
        raise ValueError("knowledge health manifest has an unsupported capability")
    return capabilities


def _optional_failure_code(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("knowledge health manifest has an invalid last_failure")
    return _required_identifier(value, "code")
