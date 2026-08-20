from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from zcore.config import get_nested, load_config
from zcore.models.knowledge import KnowledgeHealthManifest, KnowledgeHealthReport
from zcore.runtime import RuntimePaths


EXTERNAL_READONLY_PROVIDER = "external_readonly"
DEFAULT_HEALTH_MAX_AGE_SECONDS = 24 * 60 * 60
_PROVIDER_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class KnowledgeWriteFrozenError(PermissionError):
    """Raised when Z-Core is not the configured knowledge index owner."""


def knowledge_provider(config: dict[str, object]) -> str:
    value = get_nested(config, "knowledge", "provider", default=EXTERNAL_READONLY_PROVIDER)
    provider = str(value).strip().lower()
    if not _PROVIDER_RE.fullmatch(provider):
        return "invalid"
    return provider


def assert_knowledge_index_write_allowed(config: dict[str, object]) -> None:
    if knowledge_provider(config) == EXTERNAL_READONLY_PROVIDER:
        raise KnowledgeWriteFrozenError(
            "Knowledge index writes are disabled while knowledge.provider=external_readonly. "
            "Use the configured external index owner."
        )


class ExternalReadonlyProvider:
    """Read-only adapter for an externally owned knowledge health manifest.

    This adapter deliberately has no dependency on ``zcore.rag``. The external
    index owner is the only component permitted to create or refresh its index.
    """

    provider_name = EXTERNAL_READONLY_PROVIDER
    capabilities = ("health_readonly",)

    def __init__(self, paths: RuntimePaths, config: dict[str, object]):
        self.paths = paths
        self.config = config

    def health(self, *, now: datetime | None = None) -> KnowledgeHealthReport:
        manifest_path = self._manifest_path()
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return KnowledgeHealthReport(
                provider=self.provider_name,
                status="failed",
                freshness="unknown",
                warnings=("knowledge health manifest is missing",),
                provider_capabilities=self.capabilities,
                diagnostic_code="manifest_missing",
            )
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return KnowledgeHealthReport(
                provider=self.provider_name,
                status="failed",
                freshness="unknown",
                warnings=("knowledge health manifest is invalid",),
                provider_capabilities=self.capabilities,
                diagnostic_code="manifest_invalid",
            )

        try:
            manifest = KnowledgeHealthManifest.from_dict(payload)
        except ValueError:
            return KnowledgeHealthReport(
                provider=self.provider_name,
                status="failed",
                freshness="unknown",
                warnings=("knowledge health manifest is invalid",),
                provider_capabilities=self.capabilities,
                diagnostic_code="manifest_invalid",
            )

        return self._report_from_manifest(manifest, now=now)

    def _manifest_path(self) -> Path:
        configured_path = get_nested(self.config, "knowledge", "health_manifest_path", default="")
        if not isinstance(configured_path, str) or not configured_path.strip():
            return self.paths.knowledge_health_manifest_path or self.paths.base_dir / "knowledge-health.json"
        candidate = Path(configured_path).expanduser()
        return candidate if candidate.is_absolute() else self.paths.base_dir / candidate

    def _report_from_manifest(
        self,
        manifest: KnowledgeHealthManifest,
        *,
        now: datetime | None,
    ) -> KnowledgeHealthReport:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        status = manifest.status
        freshness = "current"
        warnings: list[str] = []
        diagnostic_code: str | None = None

        if manifest.status == "failed":
            if manifest.can_serve_stale:
                status = "degraded"
                freshness = "stale"
                warnings.append("external index owner failed while serving a verified stale generation")
            else:
                status = "failed"
                freshness = "unknown"
                warnings.append("external index owner reports failed without a verified serving generation")
                diagnostic_code = "external_owner_failed"
        elif manifest.last_successful_ingest_at is None:
            status = "failed"
            freshness = "unknown"
            warnings.append("knowledge index has no recorded successful ingest")
            diagnostic_code = "missing_successful_ingest"
        elif current - manifest.last_successful_ingest_at > timedelta(seconds=self._max_age_seconds()):
            if manifest.can_serve_stale:
                status = "degraded"
                freshness = "stale"
                warnings.append("knowledge index health manifest is stale")
            else:
                status = "failed"
                freshness = "unknown"
                warnings.append("knowledge index is stale without a verified serving generation")
                diagnostic_code = "unverified_serving_generation"
        elif manifest.status == "degraded":
            warnings.append("external index owner reports degraded")

        if manifest.last_failure_code:
            warnings.append("external index owner recorded a failure")

        return KnowledgeHealthReport(
            provider=self.provider_name,
            status=status,
            freshness=freshness,
            warnings=tuple(warnings),
            manifest_schema_version=manifest.schema_version,
            index_owner=manifest.provider,
            corpus_id=manifest.corpus_id,
            corpus_revision=manifest.corpus_revision,
            document_count=manifest.document_count,
            indexed_document_count=manifest.indexed_document_count,
            chunk_count=manifest.chunk_count,
            last_successful_ingest_at=(
                manifest.last_successful_ingest_at.isoformat() if manifest.last_successful_ingest_at else None
            ),
            serving_generation=manifest.serving_generation,
            serving_revision=manifest.serving_revision,
            serving_complete=manifest.serving_complete,
            embedding_model=manifest.embedding_model,
            embedding_model_version=manifest.embedding_model_version,
            capabilities=manifest.capabilities,
            provider_capabilities=self.capabilities,
            last_failure_code=manifest.last_failure_code,
            diagnostic_code=diagnostic_code,
        )

    def _max_age_seconds(self) -> int:
        configured_age = get_nested(
            self.config,
            "knowledge",
            "health_max_age_seconds",
            default=DEFAULT_HEALTH_MAX_AGE_SECONDS,
        )
        if isinstance(configured_age, bool):
            return DEFAULT_HEALTH_MAX_AGE_SECONDS
        try:
            age = int(configured_age)
        except (TypeError, ValueError):
            return DEFAULT_HEALTH_MAX_AGE_SECONDS
        return age if age >= 0 else DEFAULT_HEALTH_MAX_AGE_SECONDS


class KnowledgeHealthEngine:
    """Health facade that selects the configured read-only provider."""

    def __init__(
        self,
        paths: RuntimePaths | None = None,
        *,
        config: dict[str, object] | None = None,
    ):
        self.paths = paths or RuntimePaths.discover()
        self.config = load_config(self.paths) if config is None else config

    def health(self, *, now: datetime | None = None) -> KnowledgeHealthReport:
        provider = knowledge_provider(self.config)
        if provider != EXTERNAL_READONLY_PROVIDER:
            return KnowledgeHealthReport(
                provider=provider,
                status="failed",
                freshness="unknown",
                warnings=("knowledge health manifests require knowledge.provider=external_readonly",),
                provider_capabilities=(),
                diagnostic_code="provider_not_external_readonly",
            )
        return ExternalReadonlyProvider(self.paths, self.config).health(now=now)
