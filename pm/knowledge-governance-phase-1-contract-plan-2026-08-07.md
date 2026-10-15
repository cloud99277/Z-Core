# Phase 1 Knowledge Contract Execution Plan

> Status: DRAFT - planning only; implementation requires separate approval
> Date: 2026-08-07
> Parent: `pm/knowledge-governance-remediation-plan-2026-08-06.md`

## Objective

Phase 1 defines a governed read-only contract before any retrieval gate. It
separates corpus authorization, document eligibility, L2 parsing, and ContextPack
representation. It does not retrieve external documents, migrate data, or change a
live watcher.

## Baseline

- Automatic extraction is candidate-only. Only `memory write` and pending
  confirmation admit L2 entries.
- `external_readonly` is health-only. It does not own or search the external index.
- The repository watcher is audit-only; the live watcher and indexer remain
  unmodified.
- This machine currently has no manifest, so health returns `manifest_missing`.
  That must not cause a legacy-RAG fallback.
- Existing `memory search` and `knowledge search` are compatibility surfaces and
  remain unchanged in Phase 1.

## Scope

### In Scope

1. Strict models for a corpus registry, document metadata, L2 provider reports,
   attributed source items, and ContextPack.
2. `zcore knowledge registry validate --path <registry.json> --json` only.
3. Independent read-only parsers for topic Markdown and `whiteboard.json`.
4. A restricted metadata reader, default eligibility predicate, tests, and docs.

### Non-Goals

- `zcore context retrieve`, ranking, real-corpus excerpts, and retrieval audit logs.
- Search/index capability for `external_readonly`.
- L2/L3 migration, source metadata writes, indexer work, or live watcher changes.
- Project policy in global defaults, new dependencies, QMD, hosted memory, or graph.

## Contract Design

### Corpus Registry

The registry is project-local and explicitly supplied. A global configuration may
point at it, but cannot contain project policy or absolute roots.

```json
{
  "schema_version": "zcore.knowledge.registry/v1",
  "corpora": [{
    "id": "project-l3",
    "root_ref": "project-l3-root",
    "owner": "external-index-owner",
    "allowed_projects": ["project-id"],
    "default_inclusion": false,
    "sensitivity_ceiling": "internal",
    "search_provider": "external_readonly"
  }]
}
```

- IDs are unique. `root_ref` is opaque and must never be emitted as a path.
- `allowed_projects` is a non-empty explicit allow-list; wildcards are invalid.
- Sensitivity ordering is `public < internal < confidential < restricted`.
- `default_inclusion` declares only a future Phase 2 candidate, never present access.
- A registry/manifest corpus-ID mismatch is diagnostic and never grants access.

### Document Metadata

The reader accepts a restricted frontmatter subset without synthesizing or writing
fields. Required fields are `schema`, `id`, `title`, `type`, `project`, `scope`,
`status`, `source`, `sensitivity`, `owner`, `created_at`, `reviewed_at`,
`expires_at`, `supersedes`, and `confidence`.

```text
inbox | candidate | approved | archived | excluded
```

Only `approved` documents within the corpus sensitivity ceiling and project
allow-list are eligible by default. Missing/invalid metadata, unknown values, and
all other states are denied. `source.location` must be corpus-relative; absolute
locations are rejected. Phase 1 does not bulk-scan a real corpus.

### Independent L2 Providers

| Provider | Store | Source ID | Boundary |
| --- | --- | --- | --- |
| `TopicMarkdownL2Provider` | `topics/*.md` | `l2:topic:<topic>:<id>` | Parses `MemoryEntry`; never reads whiteboard. |
| `WhiteboardL2Provider` | `whiteboard.json` | `l2:whiteboard:<stable-id>` | Preserves legacy `action` items; never coerces them into `MemoryEntry`. |

Both return this read-only report:

```text
L2ReadReport {
  provider, store_kind, parser_status, freshness, observed_at,
  source_revision, items, warnings
}
```

Providers do not merge, deduplicate, write, or silently hide malformed input. A
missing/unreadable/invalid store produces an attributed warning. Project filtering
requires an explicitly matching project; unscoped historical entries are excluded.

### ContextPack

ContextPack is a model, not a retrieval command.

```json
{
  "schema_version": "zcore.context-pack/v1",
  "status": "not_searched",
  "reason": {"code": "contract_validation"},
  "project": "project-id",
  "task_kind": "planning",
  "query": "optional query",
  "corpora": [], "l2": [], "l3": [], "warnings": []
}
```

Allowed statuses are `not_searched`, `ready`, `no_match`, `degraded`, `failed`, and
`policy_denied`. Each item requires result ID, corpus ID, source ID, logical
relative locator, sensitivity, provenance, and excerpt. The model enforces at most
three items per layer and 1000 characters per excerpt. Future logs may keep only a
query hash and result IDs, never a query or excerpt body.

## Work Packages

```text
1A models + registry validation
   +-- 1B independent L2 providers
   +-- 1C metadata reader + eligibility
           +-- 1D ContextPack validation, compatibility locks, documentation
```

### 1A: Models and Registry

Add immutable models, safe serialization, registry loading, and validation-only
CLI output. Do not create a default registry or read a corpus as a side effect.

### 1B: L2 Providers

Use separate temporary fixtures for topic and whiteboard stores. Keep
`MemoryEngine.search`, `search_all`, writing, confirmation, and migration unchanged.

### 1C: Metadata Reader

Reuse the existing stdlib-capable frontmatter utility for a narrow schema. Reject
unsupported values instead of adding YAML. Return diagnostics only; do not scan,
alter, or index a corpus.

### 1D: ContextPack and Compatibility

Add structural validation and `not_searched` construction. Snapshot legacy search
JSON. Update the installed memory-manager guidance to describe audit-only watcher
behavior and the existing live deployment gate, without changing the live watcher.

## Acceptance

| Area | Evidence |
| --- | --- |
| Registry | Reject bad schema, duplicate ID, unsafe root, empty/wildcard allow-list, invalid provider, and invalid sensitivity. |
| Metadata | Permit complete approved metadata; deny all other states, bad schema, path escape, sensitivity excess, and project mismatch. |
| L2 | Distinct provenance; malformed/missing stores warn; L2 directory hashes remain unchanged. |
| ContextPack | Reject missing provenance, absolute locations, excess results, and large excerpts; `not_searched` calls no provider. |
| Compatibility | Legacy search JSON does not change; external_readonly never imports `zcore.rag`. |
| Regression | Phase 0 health, admission, session-end, and watcher-audit tests remain green. |

```bash
.venv/bin/python -m pytest -q tests/test_knowledge_contract.py tests/test_l2_readonly_provider.py tests/test_context_pack.py tests/test_knowledge_health.py tests/test_knowledge_watcher_audit.py tests/test_zcore_memory.py tests/test_rag_integration.py
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q zcore tests
git diff --check
```

## Approval Gates

Implementation starts only after this plan is approved. Phase 2 cannot start until
Phase 1 acceptance passes, a project-local registry/metadata policy is approved, a
valid manifest exists for each proposed corpus, and task-kind plus log-privacy
policy are reviewed. Live watcher handover remains a distinct approval requiring
version inventory, backups, an atomic manifest producer, a single-corpus audit, and
a rollback drill.
