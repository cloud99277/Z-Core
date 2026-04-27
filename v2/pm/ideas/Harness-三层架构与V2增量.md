# Harness 三层架构 × KitClaw V2 增量构思

> 来源：微信公众号《大家别急 Harness 你到底应该怎么理解》（架构师 JiaGouX）
> 讨论日期：2026-04-10
> 对照：OpenAI《工程技术：在智能体优先的世界中利用 Codex》+ Anthropic《Harness design for long-running application development》

---

## 一、文章核心论点

**同一模型、同一 Prompt，只换 Harness 系统，产出质量天壤之别：**
- 裸跑：20 分钟 / $9 / 核心功能是废的
- 完整 Harness：6 小时 / $200 / 精灵动画、行为模板、音效系统、AI 辅助关卡全做完，角色真的能跑能跳

**Harness 不是 Prompt，不是工具集，是一个上位系统问题。** 它管的是：模型该看到什么、允许做什么、做完之后谁来验、跑偏了怎么纠正。

---

## 二、三层结构拆解

### 第一层：知识层（模型该看什么）

**OpenAI 的做法：**
- AGENTS.md 不再是百科全书，改成轻量目录（~100 行），只告诉 Agent 去哪里找什么
- 真正知识进 docs/ 版本化管理：design-docs/、exec-plans/、product-specs/、references/
- 定期跑 "doc-gardening" Agent 扫描过时文档，自动发起修复 PR
- 核心判断：**对 Agent 来说，看不见的知识就等于不存在**

**关键原则：**
- 别把确定性逻辑塞进上下文 → 交给 Hooks、代码规则、工具权限
- 上下文只承载当前任务真正需要推理的信息
- 隐性知识（Slack 讨论、Google Docs 共识、工程师脑中判断）必须编码进仓库

### 第二层：约束与流程层（任务怎么拆）

**Anthropic 的做法：**
- Planner / Generator / Evaluator 三角色分离
- 拆分目的不是"并行更快"，而是"别一边生成一边自我表扬"
- Sprint 契约：每个 Sprint 开始前，Generator 和 Evaluator 先谈好验收标准（单 Sprint 27 条）
- Planner 只聚焦产品上下文和高层设计，不规定细粒度实现细节（避免错误级联）

**关键机制：context reset**
- 长任务中 compaction（原地压缩历史）不够
- 模型会出现"上下文焦虑"——提前收尾、失去一致性
- 解法：定期清空上下文，通过结构化工件把状态交接给新会话

### 第三层：反馈与运行时层（做完谁来验）

**两种运行模式：**
- hook-based（事件驱动）：适合实时纠错、权限控制
- scheduler-based（定时循环）：适合持续质量监控、定期校验

**评估原则：**
- 外部评估替代自评——模型给自己打分往往偏正面
- Evaluator 用 Playwright 真去点页面、跑功能、看结果，不是读代码打分

---

## 三、对照 KitClaw V2 现状

| Harness 层 | 文章要求 | V2 现状 | 缺口 |
|-----------|---------|---------|------|
| 知识层 | AGENTS.md 做轻量目录，知识进 docs/ 版本化 | AGENTS.md 仍较重（用户画像+技能系统+L2/L3 路由全塞一起）；L3 Obsidian 已搭好 | AGENTS.md 和 L3 之间的导航关系没建立 |
| 知识层 | doc-gardening 定期扫描过时文档 | 无 | 缺自动知识健康检查 |
| 约束层 | Planner/Generator/Evaluator 三分 | Phase 3 Skill Router + Governance + Hooks 已完成 | Hooks 做的是执行前后静态检查，缺独立评估角色 |
| 约束层 | Sprint 契约（做到什么算完成） | 无对应机制 | skill 执行完没有"验收契约"概念 |
| 约束层 | context reset 对抗长任务失真 | Phase 2 Memory Engine 有 session end 自动提取 | 缺主动的上下文清空+状态交接机制 |
| 反馈层 | 外部评估替代自评 | Observability 日志已记录 | 日志记了但没人读日志做二次评估 |
| 反馈层 | hook-based + scheduler-based 混合 | 只有 hook-based（事件驱动） | 缺 scheduler-based 持续质量监控循环 |

---

## 四、V2 增量构思

### 提案 A：AGENTS.md 轻量化 + 知识导航

**目标：** AGENTS.md 从"规则手册"变成"导航地图"

**方案：**
- AGENTS.md 只保留：用户画像（~5 行）、核心约定（~5 行）、导航索引（"遇到 X 问题去 L3 哪个路径找"）
- 详细规则迁移到 L3 的结构化文档中
- 新增 `~/.ai-memory/config.json` 中增加知识路径映射配置

**影响范围：** 所有 Agent 的上下文注入量会减少，但决策精准度应提升

### 提案 B：Evaluator 独立角色（Skill 质量评估）

**目标：** skill 执行完有独立验收，不靠自评

**方案：**
- Hooks 框架增加 post-evaluate hook 类型
- Evaluator 不是 LLM 自评，而是基于预定义的验收标准做机械检查
- 类似 Anthropic 的 Sprint 契约：skill 定义时声明验收条件，执行后自动验证
- 结果写入 Observability 日志，供 scheduler-based 循环消费

**影响范围：** skill SKILL.md schema 需要扩展（增加 `verification` 字段），hooks/builtin.py 需新增评估器

### 提案 C：Scheduler-based 知识健康检查

**目标：** 定期扫描 L2/L3 知识是否过时、自洽

**方案：**
- 利用现有的 cronjob 能力，定期执行知识校验任务
- 检查项：L2 白板条目是否过期、L3 文档最后更新时间、cross-reference 是否断裂
- 类似 OpenAI 的 doc-gardening：自动标记过时内容，提供建议修复

**影响范围：** 新增一个 scheduled task + 对应 skill

### 提案 D：Context Reset 机制

**目标：** 长任务中主动清空上下文，通过结构化工件交接状态

**方案：**
- Memory Engine 的 session end 提取已有基础
- 增加"上下文健康度"检测：当 token 使用超过阈值或任务跨度超过 N 轮时，触发 context reset
- reset 前自动提取当前状态到 L2，新 session 从 L2 恢复上下文

**影响范围：** runtime.py 需增加上下文监控逻辑，Memory Engine 需支持增量恢复

---

## 五、优先级建议

| 提案 | 优先级 | 理由 |
|------|--------|------|
| A. AGENTS.md 轻量化 | P1 | 最低成本、最快见效，直接影响每次对话的上下文质量 |
| B. Evaluator 独立角色 | P2 | 工程量中等，但对 skill 生态质量有系统性提升 |
| D. Context Reset | P2 | 长任务刚需，Memory Engine 已有基础可复用 |
| C. 知识健康检查 | P3 | 重要但不紧急，可等 A/B 落地后再启动 |

---

## 六、Planner 定位讨论（2026-04-10 补充，经修正）

### 架构定位：Zcore 是主控大脑，不是后勤工具箱

**修正前错误判断**："Zcore 不调 LLM，是纯 CLI 基础设施，Planner 应该是 skill。"

**实际情况**：Zcore 已有 `GhostAgent`（`zcore/engines/ghost_agent.py`），可以直接调用 LLM：
- 支持多 provider（Google/Gemini、Anthropic、OpenAI、Ollama）
- 有 fallback、重试、token 估算、成本追踪
- 已集成 ContextEngine（`compact_messages`）和 MemoryEngine（`extract_memories`）
- 默认模型 `gemini-2.5-flash`

**Zcore 已经在路径 A 上了**——它不是等待 Agent 调度的工具箱，而是有自己 LLM 调用能力的运行时。

### Zcore 主控架构

```
用户
 ↓ 负责
Zcore（主控大脑）
 ├── GhostAgent   — LLM 调用层（已有）
 ├── Planner      — 需求展开（新增，用 GhostAgent 调强模型）
 ├── Evaluator    — 质量验收（新增，用 GhostAgent 调中等模型）
 ├── Router       — Agent 选择（已有）
 ├── Context      — 上下文管理（已有）
 ├── Memory       — 记忆管理（已有）
 └── Hooks        — 质量门禁（已有）
     ↓ 派任务
Claude / Codex / Gemini / Hermes（执行 Agent，工具人）
```

**关键转变**：Zcore 对用户负责，其他 Agent 给 Zcore 当工具人。规划能力集中在 Zcore，Agent 只管执行。

### Planner 和 Evaluator 是 GhostAgent 的应用层角色

Planner 和 Evaluator 本质上就是 GhostAgent 的两个"应用层"角色——用 GhostAgent 的 `generate()` 去调 LLM，但 prompt 模板和输出解析不同：

| 角色 | 用 GhostAgent 调什么 | 推理强度 |
|------|-------------------|---------|
| Planner | 模糊需求 → 结构化执行计划 + 验收契约 | ⭐⭐⭐⭐⭐ 需要强模型 |
| Evaluator | 按验收标准检查 Agent 产出质量 | ⭐⭐⭐ 中等模型够用 |
| Router | Agent 选择判断 | ⭐⭐ 规则引擎为主，不一定需要 LLM |

### 待定：按角色切换模型

GhostAgent 当前默认 `gemini-2.5-flash`，做 Planner 是否够用待验证。可能需要支持按角色配置不同模型：

```yaml
llm_backend:
  planner:
    provider: anthropic
    model: claude-sonnet-4    # 强推理
  evaluator:
    provider: google
    model: gemini-2.5-flash   # 够用且便宜
  default:
    provider: google
    model: gemini-2.5-flash
```

### 现有 skill 体系中与 Planner 相关的

| Skill | 定位 | 对应文章概念 | 在新架构下的关系 |
|-------|------|------------|----------------|
| `project-planner` | 从灵感到项目（全链路，太重） | Planner 全能力但粒度太粗 | 保留作为项目级规划，Zcore Planner 做任务级 |
| `delegated-sprint` | 跨 Agent 增量开发（Plan→Dispatch→Review→Commit） | 最接近 Anthropic 的 Plan/Generator/Evaluator 循环 | 其 Plan→Dispatch→Review 流程应下沉到 Zcore 主控层 |
| `agent-orchestrator` | 线性链验证 + 执行计划生成 | 偏技术编排 | 保留做链验证，执行编排由 Zcore Router 接管 |
| `project-manager` | Scrum Master，日常推进 | 运营层面 | 保留做日常推进，Sprint 级编排由 Zcore 主控 |
| `full-cycle-builder` | 单 Agent 0→1 全生命周期 | 全链路编排 | 可作为 Zcore 的一个高级 workflow 模式 |

**缺口：** Zcore 层面缺 Planner engine 和 Evaluator engine。`delegated-sprint` 的 Plan→Dispatch→Review 流程已经有了，但跑在 Agent 上下文里——需要下沉到 Zcore。

### 建议方案

1. **Zcore 新增 `engines/planner.py`** — 基于 GhostAgent，专注需求展开 + 验收契约生成
2. **Zcore 新增 `engines/evaluator.py`** — 基于 GhostAgent，按契约验收 Agent 产出
3. **GhostAgent 扩展按角色切换模型的能力** — planner 用强模型，evaluator 用 flash
4. **`delegated-sprint` 的 Plan/Review 逻辑迁移到 Zcore** — skill 变成薄封装层，调 Zcore CLI

## 七、V2 实际状态（2026-04-10 审计）

### Phase 交付进度

| Phase | 状态 | 提交 | 内容 |
|-------|------|------|------|
| Phase 0 | ✅ 已提交 (41660e7) | ✅ | CLI skeleton, runtime bootstrap |
| Phase 1 | ✅ 已提交 (6f3f16a) | ✅ | Context Engine, Ghost Agent real API, Session |
| Phase 2 | ✅ 已提交 (96b7875) | ✅ | Memory Engine, auto-extraction, dedup, topics, migration |
| Phase 3 | ✅ 已提交 (b28c422) | ✅ | Skill Router, Governance, Hook Framework |
| Phase 4 | ✅ 已提交 (14e4f22) | ✅ | Observability, Agent Setup, Config CLI, Governance 扩展 |
| Phase 5 | ✅ 代码完成，⏳ 审查待执行 | ❌ 未提交 | Skill info/install/validate, Session show/cleanup, Memory write/topics/stats, Governance audit, 历史测试整治 |

### 测试状态

- 78 tests collected, 70 passed, 4 failed, 4 skipped
- 4 个 failure：
  - `test_discover_skills_reads_frontmatter` — mcp_export 接口变了（str vs Path）
  - `test_skill_to_tool_builds_input_schema` — mcp_export 缺 `skill_to_tool` 方法
  - `test_parse_frontmatter_extracts_metadata_and_body` — md_chunker tags 解析问题
  - `test_runtime_paths_follow_home` — 测试环境 tmpdir 隔离问题

### 待办

1. 修 4 个测试 failure
2. Gemini 独立审查（delegated-sprint Step 3）
3. git commit + PM 文件同步
4. V2 收口

### 延期到 Phase 6+

- Persona Engine (RFC-003)
- YAML Workflow 编排执行器
- session pause/resume
- memory expire-check
- 零信任签名验签
- Embedding 语义去重

### V2 定位确认

V2 保持**辅助引擎**定位——对 Agent 负责，提供 Context/Memory/Router/Hooks/GhostAgent 基础设施。不做主控。

---

## 八、V3 构思：Zcore 主控大脑

### V2 → V3 分界线

```
V2（辅助引擎）= 对 Agent 负责 ✅ 已交付
├── Context Engine
├── Memory Engine
├── Skill Router
├── Governance + Hooks
├── GhostAgent（轻量 LLM 调用）
├── Observability
└── CLI 工具集

V3（主控大脑）= 对用户负责 🔮 规划中
├── V2 全部继承
├── Planner Engine      ← 新增核心
├── Evaluator Engine    ← 新增核心
├── Agent 调度层         ← 新增（派任务给 Claude/Codex/Gemini）
├── GhostAgent 增强     ← 按角色切换模型
└── Plan→Dispatch→Review 闭环 ← 从 delegated-sprint 下沉
```

### V3 核心架构：三层 Harness 映射

| Harness 层 | 对应模块 | V2 现状 | V3 目标 |
|-----------|---------|---------|---------|
| 知识层 | Ingest + Context + Memory | 被动式：Agent 手写 JSON，记录残缺（一问一答） | **The Harvester (主动收割)**：自动接入 Claude/Hermes 日志，确保数据完整性 |
| 约束与流程层 | Planner + Router + Hooks | Hooks 已有，缺 Planner | Planner Engine（需求展开 + 验收契约）；复杂度检测自动触发 |
| 反馈与运行时层 | Evaluator + Observability | Observability 已有，缺 Evaluator | Evaluator Engine（独立验收，不靠 Agent 自评）；context reset 机制 |

### V3 模块设计草案

#### 8.1 Ingest Engine (The Harvester)

**职责**：跨 Agent 原始日志收割，消除 Agent 的导出负担

**功能**：
- **Source Adapters**: 适配不同 Agent 的私有存储格式。
- **Auto-Sync**: 检测到 Agent 会话结束时自动触发收割。
- **Integrity Check**: 确保收割的历史记录包含完整的交互流，而非仅单轮对话。

#### 8.2 Planner Engine（`engines/planner.py`）

**职责**：接收用户模糊需求，输出结构化执行计划 + 验收契约

**输入**：用户原始需求（一句话或一段话）

**输出**：
```python
@dataclass
class ExecutionPlan:
    plan_id: str
    goal: str                          # 一句话目标
    milestones: list[Milestone]         # 拆解后的里程碑
    acceptance_criteria: list[str]      # 验收契约（做到什么算完成）
    suggested_agent: str                # 推荐执行 Agent
    estimated_complexity: int           # 1-5
    context_needed: list[str]           # 需要注入的上下文路径

@dataclass
class Milestone:
    name: str
    deliverable: str                    # 具体交付物
    acceptance: list[str]               # 该里程碑的验收标准
    depends_on: list[str]               # 前置里程碑
```

**实现**：基于 GhostAgent.generate()，使用强推理模型（Claude Sonnet/GPT-4o）

**触发条件**：
- Skill Router 检测到多步骤任务（>1 milestone）
- 用户显式要求规划
- 任务涉及多个 Agent 协作

#### 8.2 Evaluator Engine（`engines/evaluator.py`）

**职责**：按验收契约检查 Agent 产出质量，不靠自评

**输入**：ExecutionPlan + Agent 执行结果

**输出**：
```python
@dataclass
class EvaluationResult:
    plan_id: str
    milestone_results: list[MilestoneEvaluation]
    overall: str                       # "pass" / "partial" / "fail"
    feedback: str                      # 具体反馈，可直接给 Agent 打回重做
    retry_recommended: bool

@dataclass
class MilestoneEvaluation:
    milestone_name: str
    criteria_met: list[bool]            # 每条验收标准是否通过
    issues: list[str]                   # 具体问题描述
```

**实现**：基于 GhostAgent.generate()，使用中等模型（Gemini Flash 就够）

**关键原则**（来自文章）：
- Evaluator 不读代码打分，而是真正去验证（执行命令、检查文件、跑测试）
- 每条验收标准独立判断，不给整体印象分
- 不通过就打回，附带具体修改建议

#### 8.3 Agent 调度层（`engines/dispatcher.py`）

**职责**：把任务分派给合适的 Agent，收集结果

**核心接口**：
```python
class AgentDispatcher:
    def dispatch(self, task: str, agent: str, context: dict) -> DispatchResult
    def available_agents(self) -> list[AgentInfo]
    def health_check(self, agent: str) -> bool
```

**支持的 Agent**：
- Claude Code（via ACP subprocess）
- Codex CLI（via ACP subprocess）
- Gemini CLI（via ACP subprocess）
- Hermes（via 内部调用）
- OpenClaw（via gateway）

**任务规格文件**：从 delegated-sprint 的 `tasks/Phase{N}-Codex-Task.md` 演化而来，格式标准化

#### 8.4 GhostAgent 增强：按角色切换模型

```toml
[llm_backend]
default_provider = "google"
default_model = "gemini-2.5-flash"

[llm_backend.roles.planner]
provider = "anthropic"
model = "claude-sonnet-4"       # 强推理，做需求展开

[llm_backend.roles.evaluator]
provider = "google"
model = "gemini-2.5-flash"     # 够用且便宜，做验收判断

[llm_backend.roles.compact]
provider = "google"
model = "gemini-2.5-flash"     # 上下文压缩不需要强推理
```

#### 8.5 知识健康检查（scheduler-based）

利用 cronjob 定期执行：
- L2 白板条目是否过期（超过 N 天未引用）
- L3 文档最后更新时间
- cross-reference 是否断裂
- 类似 OpenAI 的 doc-gardening

### V3 流程示例

```
用户："帮我把知识库整理一下，顺便做个搜索功能"

         ↓
   Zcore Planner Engine
   - 展开为 3 个 Milestone：
     M1: 知识库目录结构整理（验收：目录层级 ≤ 3，无空目录）
     M2: 搜索索引重建（验收：查询 < 500ms，召回率 > 90%）
     M3: 搜索 API 封装（验收：REST 接口可调通，有测试）
   - 验收契约：7 条标准
   - 推荐 Agent：Codex（纯代码任务）

         ↓
   Zcore Dispatcher → 派给 Codex
   - 注入上下文：知识库路径、现有索引配置、API 设计规范
   - 任务规格文件写入 L2

         ↓
   Codex 执行 → 返回结果

         ↓
   Zcore Evaluator Engine
   - 逐条检查 7 条验收标准
   - M1 ✅ M2 ✅ M3 ❌（测试没写）
   - 反馈："M3 缺少单元测试，按契约需要补 test_search_api.py"

         ↓
   Zcore Dispatcher → 再次派给 Codex（附带反馈）

         ↓
   Codex 补测试 → 返回

         ↓
   Evaluator → 全部通过 → 写入 L2 + Observability → 用户收到完成通知
```

### V3 与现有 skill 的关系

| Skill | V2 角色 | V3 角色变化 |
|-------|---------|------------|
| `delegated-sprint` | 编排层 skill | Plan/Review 逻辑下沉到 Zcore，skill 退化为薄 CLI 封装 |
| `project-planner` | 项目级全链路规划 | 保留，但任务级规划由 Zcore Planner 接管 |
| `project-manager` | Scrum Master 日常推进 | 保留，Sprint 级编排由 Zcore 主控 |
| `agent-orchestrator` | 链验证 | 保留做链验证，执行编排由 Dispatcher 接管 |
| `full-cycle-builder` | 0→1 全生命周期 | 可注册为 Zcore 的一个高级 workflow 模式 |
| `code-review` | 代码审查 | Evaluator 可调用它做技术验收 |
| `skill-observability` | 日志记录 | 与 Zcore Observability Engine 合并 |

### V3 未知数

1. **Planner 用什么模型够用？** Gemini Flash 能做需求展开吗？还是必须 Sonnet/Opus？
2. **Evaluator 的"真正验证"怎么做？** 文章说 Playwright 跑页面——Zcore 场景下是跑 shell 命令？跑测试？检查文件？
3. **Agent 调度层的协议？** ACP subprocess 是最佳选择吗？还是需要自定义协议？
4. **Context reset 的时机？** token 阈值？任务跨度轮数？怎么判断"该清了"？
5. **V2 的 4 个测试 failure 是否阻塞 V3？** 应该先修完再做 V3

---

## 九、参考资源

- 原文：https://mp.weixin.qq.com/s/tTjhHOrCslCW7vG14WFn3A
- OpenAI：《工程技术：在智能体优先的世界中利用 Codex》
- Anthropic：《Harness design for long-running application development》
- KitClaw V2 RFCs：~/projects/kitclaw/v2/rfcs/
- KitClaw V2 设计文档：~/projects/kitclaw/v2/design/
- 现有规划相关 skill：project-planner, delegated-sprint, agent-orchestrator, project-manager, full-cycle-builder
- Zcore GhostAgent 源码：~/projects/kitclaw/zcore/engines/ghost_agent.py
