# Knowledge Governance

## Scope

This document defines the Phase 0A-0C safety boundary for Z-Core knowledge and
memory integration.

- L3 Markdown remains canonical and owner-managed. Derived indexes are
  disposable.
- Z-Core is an `external_readonly` consumer for the pilot corpus. It reads a
  health manifest; it does not invoke an external indexer, mutate its database,
  rewrite source Markdown, or make a retrieval result appear fresh.
- The repository watcher is prepared for an audit-only rehearsal. That is not a
  change to a live watcher, service, cron job, L2 store, L3 corpus, or indexer.

## Admission Freeze

Automatic extraction creates reviewable pending candidates only. Confidence scores
and legacy `auto_admit_threshold` values cannot directly admit a candidate.

The only L2 admission commands are:

```bash
zcore memory write "approved fact" --topic <topic>
zcore memory pending --confirm <candidate-id>
```

When `knowledge.provider = "external_readonly"`, `zcore knowledge index` returns a
structured refusal before it loads optional RAG dependencies or chooses an index
path. The existing `knowledge search` and `memory search` commands remain legacy
compatibility paths; they do not attest to the health, ownership, or freshness of
the external pilot corpus.

## Health Manifest

An external index owner may publish a JSON manifest. The consumer accepts only
`schema_version: "zcore.knowledge.health/v1"` and requires this shape:

```json
{
  "schema_version": "zcore.knowledge.health/v1",
  "provider": "external-index-owner",
  "status": "healthy",
  "corpus": {
    "id": "l3-governed",
    "root": "l3-governed-root",
    "revision": "sha256:content-revision",
    "document_count": 42
  },
  "index": {
    "indexed_document_count": 42,
    "chunk_count": 128,
    "last_successful_ingest_at": "2026-08-07T00:00:00+00:00",
    "serving_generation": "generation-42",
    "serving_revision": "sha256:content-revision",
    "serving_complete": true,
    "embedding_model": "BAAI/bge-small-zh-v1.5",
    "embedding_model_version": "1.5"
  },
  "capabilities": ["fts", "semantic", "hybrid"],
  "last_failure": null
}
```

`corpus.root` is an opaque, non-sensitive reference. It must not contain an
absolute private path. The health CLI deliberately omits it. `last_failure` may
only expose a machine-readable `code`; diagnostic text, document contents,
credentials, and filesystem paths do not belong in the manifest.

Configure the consumer with a manifest path owned by the external producer:

```toml
[knowledge]
provider = "external_readonly"
health_manifest_path = "knowledge-health.json"
health_max_age_seconds = 86400
```

The default relative path resolves below `ZCORE_HOME`; an absolute producer path
can be configured locally. Do not commit a private path.

## Health Semantics

```bash
zcore knowledge health --json
```

The response contains the provider, status, freshness, redacted counts and
identifiers, capabilities, and a machine-readable last-failure code. It does not
contain the raw corpus root, document bodies, or raw external error text.

| State | Meaning | Retrieval consequence |
| --- | --- | --- |
| `healthy` / `current` | The manifest is valid and within its freshness window. | Eligible for a future governed retrieval gate. |
| `degraded` / `stale` | A complete serving generation is attested and differs from the current corpus revision. | A future gate must display a stale warning. |
| `failed` / `unknown` | Manifest missing, invalid, unsupported, stale without a verified serving generation, or owner-reported failure without one. | Treat the corpus as unavailable; never turn this into a successful empty search. |

An in-place index update is not evidence that an old index is usable. The producer
may report `stale` only when it preserves and verifies a complete serving generation
separately from the observed corpus revision.

## Watcher Audit Rehearsal

The repository watcher defaults to audit-only behavior for Phase 0C. An audit run
may inspect frontmatter and emit a minimized event, but it does not use
frontmatter `--apply` or invoke an index update. Exercise it only with a temporary
corpus fixture before requesting deployment approval.

The live watcher is a separate artifact. Before a switch, obtain explicit approval
and collect: the exact live script and service hashes, backups, one `--once`
fixture or single-corpus audit result, a valid manifest read by
`zcore knowledge health --json`, and a rollback drill. Do not install, restart,
stop, or rewrite the live service as part of Phase 0A-0C.

## Next Phase

Phase 1 may add a corpus registry, L2 read provider, approved-document metadata,
and a bounded `ContextPack`. It may not restore automatic L2/L3 admission or use
this manifest as a reason to take ownership of an external index.
