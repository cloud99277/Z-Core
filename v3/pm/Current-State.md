---
project: Z-Core-V3
stage: V3.1 M7 — Gemini format evidence gate
owner: yangyy
last_updated: 2026-08-20
status_source: Current-State plus pm/status-snapshots/2026-08-20-s0-baseline.md
---

# Current State

## Current Evidence Status (2026-08-20)

The repository is on `v3/develop` at `3a712c9`. The G0A-G0C boundary plus M5
OpenClaw and M6 Codex adapters are committed; the remaining dirty worktree
contains unapproved Phase 1 candidates and unrelated V3 planning material. No
candidate below is a release or deployment claim.

| Work item | State | Evidence / boundary |
| --- | --- | --- |
| G0A candidate-only admission | `committed` (`094803b`) | Automatic extraction remains pending-only; explicit write or pending confirmation is required for L2 admission. |
| G0B external-readonly health | `committed` (`094803b`) | Health reads a versioned manifest; index writes are frozen before optional-RAG imports. |
| G0C watcher audit rehearsal | `committed` (`094803b`) | Repository fixture audit only; no live watcher, service, index, source, L2, or L3 change. |
| Phase 1 knowledge contract | `candidate`, unapproved | Candidate modules remain outside the active CLI surface; no retrieval, migration, or external search is enabled. |
| V3.1 M5 OpenClaw Adapter | `committed` (`bd0a767`) | Read-only JSON/JSONL ingestion, path-safe IDs, error visibility, ingest-ignore, and redaction are covered by isolated tests. |
| V3.1 M6 Codex Adapter | `committed` (`3a712c9`) | Read-only rollout JSONL ingestion, stable UUID identity, source isolation, and redacted error reporting are covered by isolated tests. |
| V3.1 M7 Gemini Adapter | `blocked_by_evidence` | A desensitized inner-history format fixture or explicit approval to inspect one is required before implementation. |
| V3.1 M8 FTS | `planned` | Remains a rebuildable session-derived index, not L2/L3 ownership. |

Current test evidence is `181 passed, 1 skipped`; the focused G0/M5/M6 suite is
`73 passed, 1 skipped`. Source rebuild remains unverified because the current
virtual environment lacks the declared `setuptools.build_meta` backend.

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

- [ ] OpenClaw Adapter：可以 discover + ingest `~/.openclaw/agents/*/sessions/` 所有事件流
- [ ] Codex Adapter：可以 discover + ingest `~/.codex/sessions/` 所有 JSONL 会话
- [ ] Gemini Adapter：可以 discover + ingest `~/.gemini/history/` 按项目分组的会话
- [ ] SearchEngine FTS：索引模式搜索延迟 < 100ms（基线 JSON 扫描 < 2s）
- [ ] 回归：当前 181 个非跳过测试全部通过
- [ ] 新增 ≥ 20 个测试用例

## 里程碑总结（V3.0 完成）

| 里程碑 | 状态 | 提交 | 测试 |
|--------|:----:|------|:----:|
| M1 Harvester 收割机 | 🟢 完成 | `25c7645` + `4d07b39` | 15 |
| M2 GhostAgent 角色切换 | 🟢 完成 | `25c7645` + `4d07b39` | 5 |
| M3 隐私脱敏管线 | 🟢 完成 | `731c5ae` | 11 |
| M4 Session 全文搜索 | 🟢 完成 | `367fee9` | 7 |

## V3.1 里程碑（M7 等待格式证据）

| 里程碑 | 状态 | 负责方 |
|--------|:----:|--------|
| M5 OpenClaw Adapter | 🟢 完成 | Codex |
| M6 Codex Adapter | 🟢 完成 | Codex |
| M7 Gemini Adapter | 🔴 等待格式证据 | Codex |
| M8 SearchEngine 索引化 | ⚪ 待启动 | Codex |

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
- **HEAD**: `3a712c9`（G0A-G0C, M5, and M6 committed; remaining worktree candidates are unapproved）
- **测试基线**: 181 pass / 0 fail / 1 skip
- **构建状态**: blocked — current `.venv` cannot import `setuptools.build_meta`
- **Python**: ≥3.11, 零外部依赖（M8 允许引入 stdlib sqlite3）
