from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


CORPUS_REGISTRY_SCHEMA_VERSION = "zcore.knowledge.registry/v1"
DOCUMENT_SCHEMA_VERSION = "zcore.knowledge.document/v1"
L2_REPORT_SCHEMA_VERSION = "zcore.knowledge.l2-provider-report/v1"
CONTEXT_PACK_SCHEMA_VERSION = "zcore.context-pack/v1"

CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")
DOCUMENT_STATUSES = frozenset({"inbox", "candidate", "approved", "archived", "excluded"})
L2_REPORT_STATUSES = frozenset({"healthy", "partial", "failed", "unavailable"})
CONTEXT_PACK_STATUSES = frozenset({"not_searched", "ready", "no_match", "degraded", "failed", "policy_denied"})

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_OPAQUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_LOCATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/#-]{0,511}$")
_FIELD_RE = re.compile(r"^([a-z_][a-z0-9_]*):[ \t]*(.+)$")


class KnowledgeContractError(ValueError):
    """Raised when a read-contract value is incomplete, ambiguous, or unsafe."""


def _opaque(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _OPAQUE_RE.fullmatch(value.strip()):
        raise KnowledgeContractError(f"invalid {field_name}")
    return value.strip()


def _identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value.strip()):
        raise KnowledgeContractError(f"invalid {field_name}")
    return value.strip()


def _classification_rank(value: str) -> int:
    try:
        return CLASSIFICATIONS.index(value)
    except ValueError as exc:
        raise KnowledgeContractError("invalid classification") from exc


def _timestamp(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeContractError(f"invalid {field_name}")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise KnowledgeContractError(f"invalid {field_name}") from exc
    if parsed.tzinfo is None:
        raise KnowledgeContractError(f"invalid {field_name}")
    return parsed.astimezone(UTC).isoformat()


def _logical_location(value: object) -> str:
    if not isinstance(value, str) or not _LOCATION_RE.fullmatch(value):
        raise KnowledgeContractError("invalid logical location")
    if value.startswith(("/", "\\")) or ":" in value or ".." in value.split("/"):
        raise KnowledgeContractError("invalid logical location")
    return value


def _strict_frontmatter(content: str) -> dict[str, str]:
    text = content.removeprefix("\ufeff")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise KnowledgeContractError("missing document frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise KnowledgeContractError("unterminated document frontmatter") from exc

    fields: dict[str, str] = {}
    for line in lines[1:end]:
        match = _FIELD_RE.fullmatch(line)
        if match is None:
            raise KnowledgeContractError("invalid document frontmatter")
        key, value = match.groups()
        value = value.strip()
        if key in fields or not value or value.startswith(("[", "{", "|", ">", "&", "*", "!")):
            raise KnowledgeContractError("invalid document frontmatter")
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        fields[key] = value
    return fields


@dataclass(frozen=True)
class CorpusRegistryEntry:
    corpus_id: str
    root_ref: str
    owner: str
    allowed_projects: tuple[str, ...]
    default_inclusion: bool
    sensitivity_ceiling: str
    search_provider: str

    @classmethod
    def from_dict(cls, payload: object) -> "CorpusRegistryEntry":
        if not isinstance(payload, dict):
            raise KnowledgeContractError("invalid corpus registry entry")
        projects = payload.get("allowed_projects")
        if not isinstance(projects, list) or not projects:
            raise KnowledgeContractError("invalid allowed_projects")
        allowed_projects = tuple(_opaque(item, "project") for item in projects)
        if len(set(allowed_projects)) != len(allowed_projects):
            raise KnowledgeContractError("duplicate allowed_projects")
        default_inclusion = payload.get("default_inclusion")
        if not isinstance(default_inclusion, bool):
            raise KnowledgeContractError("invalid default_inclusion")
        ceiling = _identifier(payload.get("sensitivity_ceiling"), "sensitivity_ceiling")
        _classification_rank(ceiling)
        provider = _opaque(payload.get("search_provider"), "search_provider")
        if provider != "external_readonly":
            raise KnowledgeContractError("unsupported search_provider")
        return cls(
            corpus_id=_opaque(payload.get("id"), "corpus id"),
            root_ref=_opaque(payload.get("root_ref"), "root_ref"),
            owner=_opaque(payload.get("owner"), "owner"),
            allowed_projects=allowed_projects,
            default_inclusion=default_inclusion,
            sensitivity_ceiling=ceiling,
            search_provider=provider,
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "id": self.corpus_id,
            "owner": self.owner,
            "allowed_projects": list(self.allowed_projects),
            "default_inclusion": self.default_inclusion,
            "sensitivity_ceiling": self.sensitivity_ceiling,
            "search_provider": self.search_provider,
        }


@dataclass(frozen=True)
class CorpusRegistry:
    entries: tuple[CorpusRegistryEntry, ...]
    schema_version: str = CORPUS_REGISTRY_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: object) -> "CorpusRegistry":
        if not isinstance(payload, dict) or payload.get("schema_version") != CORPUS_REGISTRY_SCHEMA_VERSION:
            raise KnowledgeContractError("unsupported corpus registry schema")
        corpora = payload.get("corpora")
        if not isinstance(corpora, list):
            raise KnowledgeContractError("invalid corpora")
        entries = tuple(CorpusRegistryEntry.from_dict(item) for item in corpora)
        if len({entry.corpus_id for entry in entries}) != len(entries):
            raise KnowledgeContractError("duplicate corpus id")
        return cls(entries=entries)

    def to_public_dict(self) -> dict[str, object]:
        return {
            "ok": True,
            "schema_version": self.schema_version,
            "corpora": [entry.to_public_dict() for entry in self.entries],
        }


@dataclass(frozen=True)
class DocumentEligibility:
    eligible: bool
    code: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DocumentMetadata:
    document_id: str
    title: str
    document_type: str
    project: str
    scope: str
    status: str
    source: str
    classification: str
    owner: str
    entity_id: str
    created_at: str
    reviewed_at: str
    expires_at: str | None
    supersedes: tuple[str, ...]
    confidence: float
    schema_version: str = DOCUMENT_SCHEMA_VERSION

    @classmethod
    def from_frontmatter(cls, content: str) -> "DocumentMetadata":
        fields = _strict_frontmatter(content)
        required = {
            "schema", "id", "title", "type", "project", "scope", "status", "source",
            "classification", "owner", "entity_id", "created_at", "reviewed_at", "expires_at",
            "supersedes", "confidence",
        }
        if set(fields) != required or fields["schema"] != DOCUMENT_SCHEMA_VERSION:
            raise KnowledgeContractError("unsupported document metadata")
        status = fields["status"]
        if status not in DOCUMENT_STATUSES:
            raise KnowledgeContractError("invalid document status")
        classification = fields["classification"]
        _classification_rank(classification)
        try:
            confidence = float(fields["confidence"])
        except ValueError as exc:
            raise KnowledgeContractError("invalid confidence") from exc
        if not 0.0 <= confidence <= 1.0:
            raise KnowledgeContractError("invalid confidence")
        expires_at = None if fields["expires_at"] in {"null", ""} else _timestamp(fields["expires_at"], "expires_at")
        supersedes = () if fields["supersedes"] in {"[]", ""} else tuple(
            _opaque(value.strip(), "supersedes") for value in fields["supersedes"].split(",") if value.strip()
        )
        if fields["supersedes"] not in {"[]", ""} and not supersedes:
            raise KnowledgeContractError("invalid supersedes")
        title = fields["title"].strip()
        if not title or len(title) > 256:
            raise KnowledgeContractError("invalid title")
        return cls(
            document_id=_opaque(fields["id"], "document id"),
            title=title,
            document_type=_opaque(fields["type"], "type"),
            project=_opaque(fields["project"], "project"),
            scope=_opaque(fields["scope"], "scope"),
            status=status,
            source=_opaque(fields["source"], "source"),
            classification=classification,
            owner=_opaque(fields["owner"], "owner"),
            entity_id=_opaque(fields["entity_id"], "entity_id"),
            created_at=_timestamp(fields["created_at"], "created_at"),
            reviewed_at=_timestamp(fields["reviewed_at"], "reviewed_at"),
            expires_at=expires_at,
            supersedes=supersedes,
            confidence=confidence,
        )

    def eligibility_for(self, corpus: CorpusRegistryEntry, project: str) -> DocumentEligibility:
        if self.status != "approved":
            return DocumentEligibility(False, "status_not_approved")
        if self.project != project or project not in corpus.allowed_projects:
            return DocumentEligibility(False, "project_not_allowed")
        if self.classification == "restricted":
            return DocumentEligibility(False, "privacy_restricted")
        if _classification_rank(self.classification) > _classification_rank(corpus.sensitivity_ceiling):
            return DocumentEligibility(False, "classification_exceeds_ceiling")
        return DocumentEligibility(True, "eligible")


@dataclass(frozen=True)
class L2ProviderWarning:
    code: str
    subject_id: str

    def __post_init__(self) -> None:
        _opaque(self.subject_id, "warning subject")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class L2AttributedItem:
    source_id: str
    provider_id: str
    entry_type: str
    content: str
    project: str | None

    def __post_init__(self) -> None:
        if not self.source_id.startswith("l2:") or len(self.content) > 1000:
            raise KnowledgeContractError("invalid l2 item")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class L2ReadReport:
    provider_id: str
    status: str
    items: tuple[L2AttributedItem, ...] = ()
    warnings: tuple[L2ProviderWarning, ...] = ()
    source_revision: str | None = None
    observed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema_version: str = L2_REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.provider_id not in {"topic_markdown", "legacy_whiteboard"}:
            raise KnowledgeContractError("invalid l2 provider")
        if self.status not in L2_REPORT_STATUSES:
            raise KnowledgeContractError("invalid l2 provider status")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "provider_id": self.provider_id,
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "source_revision": self.source_revision,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True)
class AttributedContextItem:
    result_id: str
    corpus_id: str
    source_id: str
    location: str
    classification: str
    provenance: str
    excerpt: str

    def __post_init__(self) -> None:
        _identifier(self.result_id, "result id")
        _identifier(self.corpus_id, "corpus id")
        _identifier(self.source_id, "source id")
        _logical_location(self.location)
        _classification_rank(self.classification)
        _opaque(self.provenance, "provenance")
        if len(self.excerpt) > 1000:
            raise KnowledgeContractError("context excerpt too large")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ContextPack:
    status: str
    reason_code: str
    project: str
    task_kind: str
    query: str | None
    l2: tuple[AttributedContextItem, ...] = ()
    l3: tuple[AttributedContextItem, ...] = ()
    warnings: tuple[L2ProviderWarning, ...] = ()
    health_status: str | None = None
    health_diagnostic_code: str | None = None
    schema_version: str = CONTEXT_PACK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in CONTEXT_PACK_STATUSES:
            raise KnowledgeContractError("invalid context pack status")
        if len(self.l2) > 3 or len(self.l3) > 3:
            raise KnowledgeContractError("context pack result limit exceeded")
        if self.health_status == "failed" and self.status == "ready":
            raise KnowledgeContractError("failed health cannot produce ready context")

    @classmethod
    def unavailable(cls, *, project: str, task_kind: str, diagnostic_code: str) -> "ContextPack":
        return cls(
            status="failed",
            reason_code="knowledge_unavailable",
            project=project,
            task_kind=task_kind,
            query=None,
            health_status="failed",
            health_diagnostic_code=diagnostic_code,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason": {"code": self.reason_code},
            "project": self.project,
            "task_kind": self.task_kind,
            "query": self.query,
            "l2": [item.to_dict() for item in self.l2],
            "l3": [item.to_dict() for item in self.l3],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "health": {"status": self.health_status, "diagnostic_code": self.health_diagnostic_code},
        }
