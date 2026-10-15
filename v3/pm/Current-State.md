---
project: Z-Core-V3
stage: V3.1 M8 — tests_verified search-index candidate
owner: yangyy
last_updated: 2026-08-23
status_source: Current-State plus current repository and test evidence
---

# Current State

## Current Evidence Status (2026-08-23)

The repository is on `v3/develop` at `95e2cac`. The G0A-G0C boundary plus M5
OpenClaw and M6 Codex adapters are committed. M8 is an uncommitted
`tests_verified` candidate; the dirty worktree also contains unapproved Phase 1
candidates and unrelated V3 planning material. No candidate below is committed,
released, or deployed.

| Work item | State | Evidence / boundary |
| --- | --- | --- |
| G0A candidate-only admission | `committed` (`094803b`) | Automatic extraction remains pending-only; explicit write or pending confirmation is required for L2 admission. |
| G0B external-readonly health | `committed` (`094803b`) | Health reads a versioned manifest; index writes are frozen before optional-RAG imports. |
| G0C watcher audit rehearsal | `committed` (`094803b`) | Repository fixture audit only; no live watcher, service, index, source, L2, or L3 change. |
| Phase 1 knowledge contract | `candidate`, unapproved | Candidate modules remain outside the active CLI surface; no retrieval, migration, or external search is enabled. |
| V3.1 M5 OpenClaw Adapter | `committed` (`bd0a767`) | Read-only JSON/JSONL ingestion, path-safe IDs, error visibility, ingest-ignore, and redaction are covered by isolated tests. |
| V3.1 M6 Codex Adapter | `committed` (`3a712c9`) | Read-only rollout JSONL ingestion, stable UUID identity, source isolation, and redacted error reporting are covered by isolated tests. |
| V3.1 M7 Gemini Adapter | `blocked_by_evidence` | A desensitized inner-history format fixture or explicit approval to inspect one is required before implementation. |
| V3.1 M8 FTS | `tests_verified`, uncommitted candidate | Manual `zcore index rebuild`; a fresh contentless SQLite FTS5 trigram index is preferred, while missing, corrupt, wrong-version, stale, or unsafe state falls back to the legacy scan with a compatible output schema and matching behavior. `elapsed_ms` remains backend-specific. Automatic post-ingest indexing remains deferred to V3.2. |

M8 focused plus legacy and Harvester evidence is `36 passed` plus `14` subtests;
the full suite is `203 passed, 1 skipped` plus `14` subtests. The skip is the
optional `lancedb` path. `compileall` and `git diff --check` pass. Build remains
unverified because `setuptools.build_meta` is missing; `ruff`, `pyright`, and
`mypy` are unavailable.

The synthetic M8 benchmark used 1,000 generated sessions, five warmups, and 31
measured searches: median `61.062 ms`, p95 `64.615 ms`, max `65.291 ms`. It did
not read or write real sessions or `~/.zcore`.

M8 indexes only `.zcore/sessions` and already-local `.zcore/harvested`; raw
adapter sources, L2/L3, and external knowledge remain excluded. Reads use
descriptor-level `O_NOFOLLOW`, and the database is mode `0600`. Contentless FTS
reduces stored text duplication but remains a sensitive derivative index; it is
not encryption or secure erase.

## Knowledge Governance Remediation (2026-08-07)

- Phase 0A: automatic extraction is candidate-only; explicit confirmation remains
  the L2 admission path.
- Phase 0B: Z-Core consumes a versioned external health manifest through
  `external_readonly`; it does not own the external L3 index.
- Phase 0C: the repository watcher is prepared for an audit-only fixture rehearsal.
  The active external watcher has not been switched, restarted, or reinstalled.
- This remediation is a prerequisite for any automatic L2/L3 admission and is not
  part of the M8 session-derived FTS index.

## 当前阶段目标

完成 V3.1：将 Harvester 收割机扩展到 OpenClaw / Codex / Gemini 三大本地 Agent，并将 Session 搜索升级为 sqlite-fts5 索引模式，让跨 Agent 数据收割和极速检索成为现实。

## 本阶段成功标准

- [x] OpenClaw Adapter：已提交为 `bd0a767`
- [x] Codex Adapter：已提交为 `3a712c9`
- [ ] Gemini Adapter：可以 discover + ingest `~/.gemini/history/` 按项目分组的会话
- [x] SearchEngine FTS：`tests_verified` candidate 的 1,000-session synthetic benchmark < 100ms
- [x] 回归：M8 candidate full suite `203 passed, 1 skipped` + `14` subtests
- [x] 新增测试：M8 `tests_verified` candidate 将 full suite 从 181 增至 203 个 non-skipped tests（+22）

## 里程碑总结（V3.0 完成）

| 里程碑 | 状态 | 提交 | 测试 |
|--------|:----:|------|:----:|
| M1 Harvester 收割机 | 🟢 完成 | `25c7645` + `4d07b39` | 15 |
| M2 GhostAgent 角色切换 | 🟢 完成 | `25c7645` + `4d07b39` | 5 |
| M3 隐私脱敏管线 | 🟢 完成 | `731c5ae` | 11 |
| M4 Session 全文搜索 | 🟢 完成 | `367fee9` | 7 |

## V3.1 里程碑（M7 等待证据，M8 候选已验证）

| 里程碑 | 状态 | 负责方 |
|--------|:----:|--------|
| M5 OpenClaw Adapter | 🟢 完成 | Codex |
| M6 Codex Adapter | 🟢 完成 | Codex |
| M7 Gemini Adapter | 🔴 等待格式证据 | Codex |
| M8 SearchEngine 索引化 | 🟡 `tests_verified` candidate（未提交） | Codex |

## 数据格式快照（已探明）

| Source | 格式 | 路径 |
|--------|------|------|
| OpenClaw | 换行分隔 JSON，`type:"message"` 事件流，多 agent | `~/.openclaw/agents/<agent>/sessions/` |
| Codex | 事件流 JSONL，`type:"response_item"` 含 user/assistant | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` |
| Gemini | 按 project 分组，`.project_root` 映射项目路径 | `~/.gemini/history/<project>/` |

## 阻塞点

- Gemini 会话文件格式需 M5/M6 完成后实测确认（`.project_root` 已知，内层文件格式待探）

## 当前最大风险

- 三大 Agent 的会话格式随版本更新可能变化（与 M1 Claude/Hermes 同类风险）
- Gemini history 内层格式尚未完整确认，M7 可能需要调整

## 明确延期

- Vision Bridge → V3.2
- Voice Bridge → V3.2（RFC-006 已提出，见 `v3/pm/rfc-006-voice-bridge.md` + `v3/pm/Addendum-Voice-Bridge.md`）
- Planner / Evaluator / Dispatcher → V3.1+
- TUI Dashboard → V3.2
- Web Dashboard → V3.2
- SearchEngine 索引化自动 hook（post-ingest 自动触发）→ V3.2

## 技术快照

- **分支**: `v3/develop`
- **HEAD**: `95e2cac`（G0A-G0C, M5, and M6 committed; M8 remains an uncommitted candidate）
- **测试证据**: 203 pass / 0 fail / 1 skip + 14 subtests（M8 candidate）
- **构建状态**: blocked — current `.venv` cannot import `setuptools.build_meta`
- **静态工具**: unavailable — `ruff`, `pyright`, `mypy`
- **Python**: ≥3.11, 零外部依赖（M8 允许引入 stdlib sqlite3）
