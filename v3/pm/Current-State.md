---
project: Z-Core-V3
stage: V3.1 Sprint — 扩展 Adapter + 搜索索引化
owner: yangyy
last_updated: 2026-04-29
status_source: single-source-of-truth
---

# Current State

## 当前阶段目标

完成 V3.1：将 Harvester 收割机扩展到 OpenClaw / Codex / Gemini 三大本地 Agent，并将 Session 搜索升级为 sqlite-fts5 索引模式，让跨 Agent 数据收割和极速检索成为现实。

## 本阶段成功标准

- [ ] OpenClaw Adapter：可以 discover + ingest `~/.openclaw/agents/*/sessions/` 所有事件流
- [ ] Codex Adapter：可以 discover + ingest `~/.codex/sessions/` 所有 JSONL 会话
- [ ] Gemini Adapter：可以 discover + ingest `~/.gemini/history/` 按项目分组的会话
- [ ] SearchEngine FTS：索引模式搜索延迟 < 100ms（基线 JSON 扫描 < 2s）
- [ ] 回归：现有 101 个测试全部通过
- [ ] 新增 ≥ 20 个测试用例

## 里程碑总结（V3.0 完成）

| 里程碑 | 状态 | 提交 | 测试 |
|--------|:----:|------|:----:|
| M1 Harvester 收割机 | 🟢 完成 | `25c7645` + `4d07b39` | 15 |
| M2 GhostAgent 角色切换 | 🟢 完成 | `25c7645` + `4d07b39` | 5 |
| M3 隐私脱敏管线 | 🟢 完成 | `731c5ae` | 11 |
| M4 Session 全文搜索 | 🟢 完成 | `367fee9` | 7 |

## V3.1 里程碑（进行中）

| 里程碑 | 状态 | 负责方 |
|--------|:----:|--------|
| M5 OpenClaw Adapter | ⚪ 待启动 | Codex |
| M6 Codex Adapter | ⚪ 待启动 | Codex |
| M7 Gemini Adapter | ⚪ 待启动 | Codex |
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
- Planner / Evaluator / Dispatcher → V3.1+
- TUI Dashboard → V3.2
- Web Dashboard → V3.2
- SearchEngine 索引化自动 hook（post-ingest 自动触发）→ V3.2

## 技术快照

- **分支**: `v3/develop`
- **HEAD**: `e96e26d`
- **测试基线**: 101 pass / 0 fail / 1 skip
- **Python**: ≥3.11, 零外部依赖（M8 允许引入 stdlib sqlite3）
