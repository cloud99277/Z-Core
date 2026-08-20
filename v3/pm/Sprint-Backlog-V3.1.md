---
sprint: V3.1-Adapters+Search-Index
start: 2026-04-29
end: 2026-05-16
goal: 扩展 Harvester 收割机支持 OpenClaw/Codex/Gemini 三大本地 Agent，并将 Session 搜索升级为 sqlite-fts5 索引模式
---

# Sprint Backlog — V3.1

## Governance Gates (0A-0C)

| Gate | Scope | Status | Boundary |
|------|-------|:------:|----------|
| G0A | Candidate-only automatic extraction | `committed` (`094803b`) | No high-confidence auto-admission to L2/L3. |
| G0B | `external_readonly` health manifest | `committed` (`094803b`) | External index remains owner-managed. |
| G0C | Watcher audit-only rehearsal | `committed` (`094803b`) | Repository fixture only; no live watcher switch. |

G0A-G0C are prerequisites for any automatic L2/L3 admission. M8 remains a
rebuildable, session-derived FTS index and must not be treated as L2/L3 source
admission or ownership.

The three G0 gates were committed without Phase 1 candidate code or unrelated
V3 roadmap material. The commit is not a release or deployment claim. See
`pm/status-snapshots/2026-08-20-s0-baseline.md`.

## 里程碑

| 里程碑 | 目标 | 准出标准 | 预计工作量 | 依赖 | 状态 |
|--------|------|---------|-----------|------|:----:|
| **M5** | OpenClaw Adapter | discover `~/.openclaw/agents/*/sessions/` 下所有 JSON 事件流；正确提取 `user`/`assistant` 消息对；过滤 `toolResult`/`toolCall` 等噪声；≥5 个测试 | 2-3 天 | G0A-G0C committed | 🟢 `bd0a767` |
| **M6** | Codex Adapter | discover `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`；提取 `response_item` 类型中的 user/assistant 消息；≥5 个测试 | 2-3 天 | M5 committed | 🟢 `3a712c9` |
| **M7** | Gemini Adapter | discover `~/.gemini/history/<project>/` 目录；读取 `.project_root` 文件获取项目路径；提取对话消息；≥5 个测试 | 2-3 天 | Desensitized format fixture or explicit source-read approval | 🔴 evidence gate |
| **M8** | SearchEngine 索引化 | 引入 sqlite-fts5 索引；搜索延迟从 <2s 降至 <100ms；向后兼容无索引降级；≥5 个测试 | 3-4 天 | M5 数据量验证 | ⚪ 待启动 |

## M5 任务拆解：OpenClaw Adapter

- [ ] 实现 `zcore/adapters/openclaw_adapter.py`，继承 `SourceAdapter`
- [ ] `discover()`：扫描 `~/.openclaw/agents/*/sessions/`，支持按 project（agent name）过滤
- [ ] `ingest()`：解析换行分隔 JSON 事件流，提取 `type=="message"` 且 `role in [user, assistant]` 的消息
- [ ] 处理 `content` 为 list（含 `type:text`/`type:toolCall` 混合）的情况，只提取文本
- [ ] 注册到 `HarvesterEngine` 默认适配器列表
- [ ] 新增测试（≥5 用例）

## M6 任务拆解：Codex Adapter

- [ ] 实现 `zcore/adapters/codex_adapter.py`，继承 `SourceAdapter`
- [ ] `discover()`：遍历 `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`，提取 session_id 和时间
- [ ] `ingest()`：解析 JSONL，过滤 `type=="response_item"` + `payload.type=="message"`，提取 user/assistant 消息
- [ ] 从 `turn_context` 提取 `cwd` 作为 project 字段
- [ ] 注册到 `HarvesterEngine` 默认适配器列表
- [ ] 新增测试（≥5 用例）

## M7 任务拆解：Gemini Adapter

- [ ] 实现 `zcore/adapters/gemini_adapter.py`，继承 `SourceAdapter`
- [ ] `discover()`：遍历 `~/.gemini/history/<project>/`，读取 `.project_root` 文件获取项目路径
- [ ] `ingest()`：解析 Gemini 对话格式（待 M5/M6 完成后实测确认格式）
- [ ] 注册到 `HarvesterEngine` 默认适配器列表
- [ ] 新增测试（≥5 用例）

## M8 任务拆解：SearchEngine 索引化

- [ ] 新建 `zcore/engines/search_index.py`：管理 `~/.zcore/search.db`（sqlite-fts5 表）
- [ ] 实现增量索引：`ingest()` 完成后自动写入 FTS 表
- [ ] SearchEngine 优先查 FTS 索引，索引不存在时降级为全文扫描
- [ ] 新增 `zcore index rebuild` CLI 命令（全量重建索引）
- [ ] 向后兼容：现有 101 个测试不受影响
- [ ] 新增索引测试（≥5 用例）

## MVP 阶段明确不做

- ❌ Vision Bridge (全局视觉解释) → V3.2
- ❌ Voice Bridge (双向语音交互) → V3.2（RFC-006 已提出，config.toml 预留空区块）
- ❌ Planner / Evaluator / Dispatcher → V3.1+
- ❌ TUI Dashboard → V3.2
- ❌ Web Dashboard → V3.2
- ❌ 具身伴侣表现层 → V3.5+ / 独立仓库
