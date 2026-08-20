# Z-Core Knowledge Governance and Retrieval Repair Plan

> Status: Phase 0A-0C implemented and verified on 2026-08-07; Phase 1 has a planning-only execution plan; live watcher changes remain unapproved
> Date: 2026-08-06
> Scope: Z-Core knowledge and memory integration; no production changes in this document
> Basis: L2/L3 architecture audit and open-source research completed on 2026-08-06

## 1. Decision Summary

Z-Core will not replace the existing Markdown L3 corpus or make an agent-managed
memory database the new source of truth. Markdown remains the reviewed, versionable
knowledge source. Search indexes, embeddings, and any future graph are rebuildable
derivatives.

The immediate product gap is a governed retrieval path, not a graph database. The
implementation sequence is therefore:

1. Make the existing corpus and index health observable and honest.
2. Define one read contract for L2 and L3, plus a bounded context-pack format.
3. Pilot project-local retrieval routing without automatic writes.
4. Promote only proven generic interfaces into Z-Core.

QMD is a later, optional shadow-index experiment. It is not a replacement decision
and must pass a Chinese retrieval evaluation before it can be offered as a provider.
Graphiti, Letta, Mem0, and Cognee are reference designs only for this plan.

## 2. Problem Statement

The current runtime has separate L2/L3 retrieval and indexing paths:

- `memory-manager` performs literal L3 grep and owns the configured L3 root.
- `knowledge-search` uses an external LanceDB indexer and search wrapper.
- Z-Core has an optional RAG path but is not the active index owner.
- The L3 watcher applies inferred frontmatter and retries failed indexing without a
  health contract that tells consumers whether results are fresh.

The result is neither proactive retrieval nor a reliable basis for making retrieval
proactive. A live watcher process can coexist with a stale index, while no common
policy determines when a task should retrieve, what corpus it may access, or how
much context it may inject.

## 3. Constraints and Invariants

### Required invariants

- L3 Markdown is the canonical, reviewable source. Derived stores are disposable.
- Automatic retrieval is read-only. L2 and L3 writes remain explicit confirmation
  actions or human-reviewed candidates.
- A failed, stale, incomplete, or privacy-restricted corpus must never be represented
  as a successful empty search.
- Returned context must contain source, retrieval reason, freshness state, and a
  bounded excerpt. Raw documents are never injected wholesale.
- Project trigger policy, corpus membership, and privacy labels remain project-local.
- Z-Core retains its no-daemon, optional-RAG, stdlib-first core. External providers
  are adapters rather than mandatory dependencies.

### Explicit non-goals

- No automatic promotion of chat transcripts, Inbox notes, or agent output into L3.
- No migration of project-private skills or rules into global Z-Core behavior.
- No introduction of a graph database, hosted memory service, or QMD dependency in
  the first two phases.
- No broad `zcore setup all` rewrite or hidden prompt interception. A stateless CLI
  cannot reliably intercept every GUI/agent request; the project pilot must invoke
  retrieval through explicit local routing rules.
- No source-document rewrite by the watcher during this repair plan without a
  separately approved metadata migration.

## 4. Target Architecture

```text
Reviewed L3 Markdown             L2 decisions and actions
        |                                 |
        +---------- Corpus Registry -------+
                              |
                    Knowledge Health Report
                    (freshness, coverage, errors)
                              |
                    Context Retrieval Gate
              task kind + project + query + policy
                              |
                     Attributed Context Pack
                              |
                  project-local agent/skill routing

Conversation and task output -> candidate queue -> human review -> L2 or L3
```

The gate is a Z-Core capability. It decides whether retrieval may proceed and formats
the result; it does not decide that a fact is permanently worth storing.

## 5. Work Phases

### Phase 0A: Admission Safety Freeze

**Goal:** Establish a hard boundary before any new provider can observe or consume
the pilot corpus: Z-Core has no authority to automatically admit, rewrite, or
rebuild L2, L3, or an external derived index.

**Authorized implementation**

- Make `external_readonly` the explicit knowledge-provider mode for the pilot.
  In that mode Z-Core may read a provider-owned health manifest only; it must not
  create, update, delete, or compact an L3 index or source document.
- Freeze L2/L3 automatic admission in the runtime. Every automatic conversation
  extraction becomes a pending candidate regardless of confidence or legacy
  `auto_admit_threshold` values. `zcore memory write` and
  `zcore memory pending --confirm` remain the only L2 admission paths.
- Freeze knowledge-index admission in the runtime configuration. `zcore knowledge
  index` must reject mutation while `external_readonly` is selected, with a
  machine-readable reason rather than silently falling back to the built-in indexer.
- Preserve `zcore knowledge search` and `zcore memory search` as documented legacy
  compatibility paths. They are not evidence that the external pilot corpus is
  healthy, fresh, or owned by Z-Core.
- This freezes only Z-Core-owned automatic paths. It does not claim to freeze the
  separately deployed watcher; its service unit, external indexer, L2/L3 data, and
  source Markdown remain out of scope until the watcher handover is approved.

**Acceptance criteria**

- A fresh Z-Core runtime defaults to the `external_readonly` provider and an
  admission state of `frozen`; automatic extraction never writes L2, even when an
  existing configuration has a high-confidence threshold.
- A write-index request in that mode fails before optional RAG dependencies or an
  index path are touched.
- Explicit L2 writes and pending confirmations still work; existing read-only
  compatibility commands keep their current behavior.
- The implementation does not write outside an isolated Z-Core runtime in tests.

**Rollback:** an operator must explicitly select a separately documented legacy
provider. Re-enabling a writer is not an implicit fallback and requires a new
approval for the target corpus.

### Phase 0B: Versioned Health Manifest and Health Facade

**Goal:** Make external corpus health observable without granting Z-Core ownership
of the corpus or index.

**Authorized implementation**

- Define a versioned JSON health-manifest contract, initially
  `zcore.knowledge.health/v1`. It identifies the corpus by a non-sensitive root
  reference, observed revision/hash, and a verified serving generation/revision;
  it reports document/index/chunk counts, successful-ingest time, embedding
  model/version, supported capabilities, freshness, and the last failure summary.
- Add a Z-Core model and read-only adapter that validate the manifest, distinguish
  `healthy`, `degraded`, and `failed`, and make staleness explicit. Missing,
  malformed, unsupported-version, or unavailable manifests are failed states, never
  successful empty health reports.
- Add `zcore knowledge health --json`. Its public output must omit document text,
  secrets, and absolute private paths, including paths that arrive in an external
  failure message.

**Acceptance criteria**

- A valid fresh manifest reports `healthy`. A `stale`/`degraded` result is allowed
  only when the manifest attests that a complete serving generation remains intact
  while the observed source revision differs. An in-place or otherwise unverified
  failed update reports `failed`, never a usable stale result. An invalid or absent
  manifest reports `failed` with a diagnostic code.
- The manifest schema is versioned and rejects unknown required semantics rather
  than guessing.
- CLI fixtures prove that no absolute corpus path or document body is emitted.

**Rollback:** remove the adapter and manifest path. The corpus and derived index are
unmodified because the adapter is read-only.

### Phase 0C: External Read-Only Provider and Watcher Audit-Only Rollout Contract

**Goal:** Define the handoff from the external owner to the health facade without
performing a watcher deployment.

**Authorized implementation**

- Register `external_readonly` as the provider identity in configuration and public
  health results. Its Phase 0 responsibility is health consumption only; it does
  not search, index, repair metadata, or write admission decisions.
- Prepare the repository watcher for an audit-only default: it may inspect
  frontmatter without `--apply`, must not call index update, and emits only a
  minimized audit event. This is exercised only against temporary fixtures.
- Document the producer contract for a future external watcher: it must publish an
  atomic `v1` health manifest for each attempted ingest. A failed ingest may report
  `stale` only when it preserves and verifies a complete serving generation;
  otherwise it records a redacted failure with `failed` freshness/state.
- Treat this as rollout readiness, not deployment authorization. It does not
  authorize modifying the live `~/.ai-skills` watcher, starting/stopping/reinstalling
  its service, or switching any currently running watcher.

**Deployment gate (not implemented in Phase 0A-0C)**

The actual watcher switch requires separate explicit confirmation after: a service
and script hash inventory, backups of the service/configuration, a single-corpus
`--once` audit run, manifest validation by `zcore knowledge health --json`, and an
observed rollback drill. The production change must be limited to the verified live
watcher path; a repository copy is not assumed to be the deployed script.

**Acceptance criteria**

- The provider is named in every health response and declares read-only capability.
- Documentation gives the watcher producer an atomic, audit-only manifest contract
  and a deployment gate, without presenting it as already active.
- No process, service unit, live watcher script, index, source Markdown, L2, or L3
  data changes during Phase 0C. Repository-only watcher code may change solely to
  support the temporary-fixture audit rehearsal.

**Rollback:** none is needed for the contract itself. A future live rollout must
restore its backed-up watcher/service configuration if its manifest validation fails.

### Phase 1: Define the Knowledge Contract

**Goal:** Make collection, retrieval, and write admission separate operations.

**Tasks**

- Introduce a corpus registry. Each entry specifies an ID, root, owner, allowed
  project(s), default inclusion, sensitivity ceiling, and search-provider adapter.
- Define approved-document metadata:
  `id`, `title`, `type`, `project`, `scope`, `status`, `source`, `sensitivity`,
  `owner`, `created_at`, `reviewed_at`, `expires_at`, `supersedes`, and `confidence`.
- Define document states: `inbox`, `candidate`, `approved`, `archived`, and
  `excluded`. Only `approved` is default-searchable; `inbox` requires an explicit
  collection selection.
- Define a read-only L2 provider contract. It must declare its store, parser status,
  result freshness, and source IDs instead of silently mixing whiteboard and topic
  storage.
- Define `ContextPack`: retrieval reason, corpus health, query, task kind, result
  IDs, source locations, excerpts, and degradation warnings.

**Important compatibility decision**

Do not migrate `whiteboard.json` or topic Markdown automatically. Phase 1 reads them
through explicit adapters and records which source produced each item. A migration is
a separately approved data operation.

**Likely implementation surface after approval**

- Extend the Phase 0 knowledge models, provider package, and health facade with a
  corpus registry and read contract.
- `zcore/engines/memory.py` (provider interface only; no reintroduction of
  automatic admission)
- `docs/knowledge-governance.md`
- `tests/test_knowledge_contract.py` (new)

**Acceptance criteria**

- A retrieval request names the corpus and result provenance for every returned item.
- `excluded` and over-sensitivity documents cannot be returned by default.
- Any malformed or unavailable L2 source becomes a visible provider warning.
- Existing `zcore memory search` behavior remains backwards-compatible until a
  documented replacement command is ready.

### Phase 2: Build the Bounded Retrieval Gate

**Goal:** Expose a deterministic, read-only interface that project-local rules can
call for high-value tasks without mentioning L3 explicitly.

**Proposed interface**

```text
zcore context retrieve \
  --project <project-id> \
  --task-kind <planning|architecture|strategy|retrospective|sop|history> \
  --query <query> \
  --l2-limit 3 --l3-limit 3 --json
```

**Gate behavior**

1. Validate task kind, project policy, corpus access, and index health.
2. Read a bounded L2 set first when the policy permits it.
3. Query approved L3 collections only when needed and healthy enough.
4. Produce an attributed `ContextPack`, including `not_searched`, `no_match`,
   `stale`, `degraded`, and `failed` as distinct outcomes.
5. Do not write to L2, L3, pending memory, or source Markdown.

**Likely implementation surface after approval**

- `zcore/engines/knowledge.py`
- `zcore/models/knowledge.py`
- `zcore/cli/main.py`
- `zcore/engines/observability.py`
- `tests/test_context_retrieval.py` (new)
- `tests/test_context_retrieval_cli.py` (new)

**Acceptance criteria**

- Unrelated chat/task kinds return `not_searched` without incurring a search.
- Each successful pack contains at most 3 L2 and 3 L3 excerpts and no full document.
- Policy denial, stale data, provider failure, and no-match produce distinct JSON
  statuses.
- Retrieval does not modify any file except its append-only operational log.

### Phase 3: Project-Private Pilot and Evaluation

**Goal:** Validate usefulness and safety in the personal-business project before any
global admission.

**Tasks**

- Add a project-local retrieval rule for only: planning, strategy, retrospective,
  business diagnosis, workflow/SOP changes, and historical-decision questions.
- Exclude casual chat, single-sentence rewriting, image/video creation, and raw
  private asset work unless the user asks to search history.
- Build a 20-30 question Chinese evaluation set: exact terms, paraphrases,
  cross-document answers, superseded decisions, sensitive-document exclusions, and
  intentional no-match cases.
- Record gate decision, provider, corpus health, result IDs, latency, and a human
  verdict (`useful`, `irrelevant`, `missed`, `unsafe`) without logging private
  content.
- Run a QMD shadow-index comparison only after baseline health is stable. Test its
  Chinese retrieval performance and collection exclusion rules; do not route real
  tasks through it unless it passes the preset criteria.

**Pilot success criteria**

- `Precision@3 >= 0.80` for the approved question set.
- No sensitive or excluded document appears in default retrieval.
- No retrieval operation produces an unapproved L2/L3 write.
- All failed or stale searches are visible in the log.
- Human review marks at least 70% of triggered packs as useful; otherwise tighten
  trigger policy before widening scope.

**Rollback:** remove the project-local routing rule. The gate and corpus remain
read-only, so no knowledge data must be restored.

### Phase 4: Limited Z-Core Admission

**Goal:** Promote only stable generic interfaces after the pilot, not this project's
content policy.

**Promotion candidates**

- corpus registry schema and provider protocol
- health manifest and `zcore knowledge health`
- bounded context-pack schema and retrieval audit log
- task-kind gate contract and test fixture format

**Do not promote**

- personal-business corpus membership, tags, triggers, privacy classifications, or
  write-admission policy
- QMD as a core dependency
- Graphiti or any graph database
- automatic L2/L3 writes

**Admission gate:** a design review confirms the Phase 3 evaluation, privacy review,
operational cost, and rollback behavior. Only then may a release plan be created.

## 6. Dependencies and Ordering

```text
Phase 0A admission safety freeze
        -> Phase 0B versioned health manifest
        -> Phase 0C external-readonly health consumer + audit rehearsal
        -> Phase 1 knowledge contract
        -> Phase 2 retrieval gate
        -> Phase 3 project pilot + Chinese evaluation
        -> Phase 4 generic Z-Core admission
```

No phase may start until the preceding acceptance criteria pass. The live watcher
handover is a separate approval after Phase 0C, not a Phase 0C completion condition.
In particular, Phase 2 cannot consume a corpus without a Phase 0 health state, and
Phase 3 cannot enable automatic reads until Phase 1 establishes sensitivity and
corpus membership.

## 7. Risks and Controls

| Risk | Control |
| --- | --- |
| Stale index yields plausible but outdated advice | Freshness is mandatory in `ContextPack`; stale semantic search is never silent. |
| Auto-collection pollutes L3 | Candidate and approved states stay separate; watcher metadata writes are not automatic. |
| Project privacy leaks into generic infrastructure | Corpus and policy stay project-local; Z-Core holds only generic protocols. |
| Retrieval adds noise or cost | Gate has narrow task kinds, bounded limits, and no-search outcomes. |
| New provider creates dependency pressure | QMD is optional, external, and evaluated only as a shadow index. |
| Legacy L2 stores disagree | Read through attributed adapters first; migrate only after a separate approved plan. |
| In-place external update loses the last serving index | Report `failed` unless a complete serving generation is independently attested; do not infer stale availability from a PID or log line. |

## 8. Authorization and Next Confirmation

The 2026-08-07 authorization covers only Phase 0A-0C implementation inside this
repository: candidate-only automatic extraction, the external-readonly health
consumer, versioned manifest contract, repository watcher audit rehearsal, and
documentation alignment. It does not authorize Phase 1-4, data migration, a new
external indexer, or a live watcher deployment.

Before the live watcher handover, explicitly confirm all of the following:

1. The exact live watcher and external-indexer versions/hashes to change.
2. The manifest producer's atomic-generation or rollback guarantees.
3. Backups and the single-corpus audit rehearsal result.
4. Permission to modify/install/restart the watcher service.
5. Permission to switch its frontmatter or indexing mode.

## 9. Evidence Links

- Existing Z-Core memory behavior: `zcore/engines/memory.py`
- Existing optional RAG package: `zcore/rag/`
- Existing configuration: `zcore/config.py` and `~/.zcore/config.toml`
- External watcher reference (not a Z-Core worktree file; live changes require
  separate approval): `~/.ai-skills/memory-manager/scripts/watch-knowledge-base.py`
- External indexer reference (not a Z-Core worktree file; provider work requires
  separate approval): `~/projects/agent-os-knowledge-base/src/rag/knowledge_index.py`
- Existing architecture direction: `v3/pm/Analysis-V3-Make-vs-Buy.md`
