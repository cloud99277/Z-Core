---
title: "Z-Core V3 路线图"
status: draft
created: 2026-04-11
scope: v3-planning
---

# Z-Core V3 路线图

> V2 已于 2026-04-11 收官（9 Engine / 35 CLI / 39 Tests / 0 Dependencies）。
> 本文档汇总 V3 的规划方向，供后续构思和优先级排序。

---

## 🖥️ Dashboard — 可视化 UI 仪表盘（重大特性）

**定位**：`zcore dashboard` 启动本地 Web 仪表盘，提供 Z-Core 全部运行时数据的可视化。

**核心页面构想**：

| 页面 | 数据来源 | 可视化形式 |
|------|---------|-----------|
| **记忆浏览器** | `~/.ai-memory/topics/*.md` | 按主题分组、时间线、搜索高亮、类型筛选（decision/fact/lesson） |
| **会话时间线** | `~/.zcore/sessions/index.json` | 时间线视图、Agent 切换轨迹、会话状态色标（active/paused/completed） |
| **执行统计** | `~/.zcore/logs/executions.jsonl` | 趋势折线图、技能使用热力图、每日/周/月聚合 |
| **成本追踪** | `~/.zcore/logs/costs.jsonl` | 费用曲线、按 provider/model 分类、预算使用率 |
| **MCP 管理** | `~/.zcore/mcp-servers.toml` + Agent configs | 跨 Agent 同步状态矩阵、一键同步操作 |
| **治理审计** | governance rules + executions | 权限规则列表、违规事件高亮、allow/deny 规则管理 |
| **系统概览** | `zcore status/doctor` 数据 | 健康状态卡片、引擎状态指示灯、版本信息 |

**技术约束（待讨论）**：
- 前端方案：单 HTML 文件 vs 轻量框架（Vue/React CDN）vs 完整构建
- 后端方案：stdlib `http.server` + 自定义 handler vs 轻量框架
- 零依赖原则是否保持——Dashboard 可能是第一个需要例外的场景
- 数据刷新：轮询 vs WebSocket vs 手动刷新
- 部署模式：`zcore dashboard` 临时启动 vs 持久化服务

**设计要点**：
- 现代、精美的 UI 设计（暗色主题、渐变、微动画）
- 响应式布局（桌面优先，兼容平板）
- 交互式数据探索（记忆搜索、时间范围选择、筛选）
- 实时状态反馈（活跃会话、Ghost Agent 可用性）

**优先级**：高 — 这是 Z-Core 从"开发者工具"到"可管理平台"的关键一步。

---

## 🧠 Planner Engine — 需求展开与结构化计划

从 Codex 在 Phase 6 中提出的构思（见 `Harness-三层架构与V2增量.md`）。

**定位**：将模糊的用户需求展开为结构化的执行计划（Task Graph）。

- 输入："帮我给项目加上用户认证"
- 输出：结构化 Task 列表，每个 Task 带有前置依赖、预计工作量、所需技能

**与 V2 的关系**：复用 SkillRouter（知道有哪些技能可用）、MemoryEngine（查询历史决策）。

---

## 🔄 The Harvester — 自动化记忆收割（重大特性）

**定位**：解决 Agent “默写” JSON 导致的记录残缺（一问一答）问题，实现全量对话接入。

**核心构思**：
- **主动接入 (Active Ingestion)**: 废弃“求 Agent 导出 JSON”的模式，改为由 Z-Core 自动解析本地 Agent 日志（如 `.claude/sessions/`、`.hermes/sessions/`、Cursor 缓存）。
- **收割器指令**: `zcore session ingest --source <claude|hermes|cursor>`。
- **中间件角色**: Z-Core 不重复存储原始大文本，而是将其加工为结构化 Markdown 报告后，同步给其他执行 Agent。

**优先级**：极高 — 这是保证 V3 Planner 和 Evaluator 拥有高质量数据输入的前提。

---

## 📊 Evaluator Engine — 独立验收

**定位**：独立于执行者的质量评估引擎，不靠 Agent 自评。

- 代码质量检查（静态分析、测试覆盖率）
- 设计合规检查（是否符合历史架构决策）
- 交付完整性检查（是否遗漏需求）

---

## 🚀 Agent Dispatcher — 任务分派

**定位**：将 Planner 产出的 Task Graph 分派给最合适的 Agent 执行。

- Claude Code：复杂推理、架构设计
- Codex CLI：批量代码生成、重构
- Gemini CLI：审查、文档、分析

**与 V2 的关系**：复用 SessionManager（跨 Agent 会话交接）、ObservabilityEngine（追踪分派结果）。

---

## 其他 V3 候选

| 特性 | 说明 | 优先级 |
|------|------|--------|
| **预测性记忆推送** | 收割机接入数据后，主动向执行 Agent 注入相关的历史决策和 Bug 预警 | 高 |
| **分歧审计器** | 跨 Agent 协作时，自动对比并发现不同 Agent 对架构决策的理解偏差 | 中 |
| **会话钱包 (Context Wallet)** | 将 Session、记忆、快照封装为 `.zcore` 文件，支持心智模型的冷冻与分享 | 中 |
| GhostAgent 按角色切换模型 | 压缩用 Flash，提取用 Haiku，分析用 Sonnet | 中 |
| Context Reset 机制 | 主动重置并恢复上下文，而非被动等待窗口爆满 | 中 |
| Persona Engine (RFC-003) | 统一人格同步到各 Agent（行为模式、偏好、语调） | 低 |
| 零信任签名验签 | 技能包签名验证，防止供应链攻击 | 低 |
| Embedding 语义去重 | 用向量相似度替代 difflib 做记忆去重 | 低 |
| AGENTS.md 轻量化 | 自动生成、知识导航、最小化 L1 注入 | 低 |

---

*本文档为构思阶段，优先级和范围待进一步讨论。*

> **[2026-04-27 更新]** V3.0 MVP 范围已定义，详见 `V3-MVP-Scope.md`。
> 本文档继续作为 V3 全量特性池保留，MVP 之外的特性按 V3.1/V3.2/V3.5+ 分批交付。

