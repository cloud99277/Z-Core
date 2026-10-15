---
title: "V3 技术选型分析：造轮子 vs 用轮子 — 数字生命架构"
status: analysis
created: 2026-04-29
updated: 2026-04-29
scope: v3-planning
---

# V3 技术选型分析：数字生命架构

> **定位**：本文档是技术景观分析，不是决策文件。不修改现有规划。
> **核心结论**：Z-Core 是数字生命，不是工具集。器官用最好的开源方案，Z-Core 做灵魂和集成。

---

## 分析背景

RFC-006（Voice Bridge）在评估过程中发现，Pipecat 框架已经完整实现了自研三段式方案想做的全部工作。
这引发了一个系统性问题：**V3 其他模块是否也存在类似的"已有成熟轮子"的情况？**

本文档逐模块扫描 V3 Roadmap 中的所有特性，评估自研价值与开源替代方案。

---

## 模块逐项分析

### 1. Harvester 收割机（M1）— 无替代

**自研价值：⭐⭐⭐⭐⭐**

Agent 会话格式各不相同，没有通用工具能直接解析：

| Source | 格式 | 特殊性 |
|--------|------|--------|
| Claude | JSONL，`type:"message"` | 项目目录结构特殊 |
| Hermes | JSON，SQLite 历史 | 自有 schema |
| OpenClaw | 换行分隔 JSON 事件流 | 多 agent 混合 |
| Codex | rollout-*.jsonl | `response_item` 嵌套 |
| Gemini | 按 project 分组 | `.project_root` 映射 |

**结论**：这是 Z-Core 最独特的价值，必须自研。已完成（V3.0 M1）。

---

### 2. 隐私脱敏管线（M3）— 有成熟替代

**自研现状**：`zcore/utils/privacy.py`，5 种 regex 模式（API key / password / IP / email / token）。

**开源替代：Microsoft Presidio**

- GitHub: `microsoft/presidio`（Apache-2.0）
- NLP 实体识别 + regex 双引擎
- 内置 40+ 种 PPI 类型（姓名、身份证、银行卡、地址...）
- 支持多语言（中文需加载 zh 模型）
- 可自定义识别器（`sk-*` 等自定义模式可注册）

```python
from presidio_analyzer import AnalyzerEngine, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine

# 添加自定义模式
sk_recognizer = PatternRecognizer(
    supported_entity="OPENAI_KEY",
    patterns=[{"regex": "sk-[a-zA-Z0-9]{20,}", "score": 0.95}],
)
analyzer = AnalyzerEngine()
analyzer.registry.add_recognizer(sk_recognizer)

results = analyzer.analyze(text="key: sk-abc123xyz", language="en")
```

**对比**：

| 维度 | Z-Core 自研 regex | Presidio |
|------|------------------|----------|
| PII 类型数 | 5 | 40+ |
| 识别方式 | 纯 regex | NLP + regex |
| 中文姓名/地址 | ❌ | ✅（需 zh 模型） |
| 依赖 | 零 | spaCy (~500MB) |
| 可扩展性 | 加 regex 模式 | 加 recognizer |

**建议**：核心 regex 保留（零依赖），Presidio 作为 `[privacy]` 可选 extra 增强。

---

### 3. Session 搜索（M4/M8）— 有更优方案

**自研现状**：JSON 全文扫描（<2s），计划升级为 SQLite FTS5 索引（<100ms）。

**开源替代：Meilisearch**

- GitHub: `meilisearch/meilisearch`（MIT）
- Rust 实现，单二进制部署
- 内置中文分词（jieba）
- 毫秒级搜索
- Typo tolerance（打错字也能搜到）
- 租户索引（按 source/project 隔离）
- 增量高亮 + 分面搜索

**对比**：

| 维度 | SQLite FTS5 | Meilisearch |
|------|-------------|-------------|
| 部署 | stdlib 内置 | 单二进制 + 常驻进程 |
| 中文分词 | 弱（需自定义 tokenizer） | 内置 jieba |
| 搜索延迟 | <100ms | <10ms |
| Typo tolerance | ❌ | ✅ |
| 依赖 | 零（stdlib sqlite3） | 独立进程 |
| 增量索引 | 需自建 | 原生支持 |

**建议**：SQLite FTS5 保底（零依赖优势），Meilisearch 作为 `[search]` 可选增强。
Z-Core 的 `SearchEngine` 抽象层已就绪，后端切换只需换 adapter。

---

### 4. Vision Bridge — 已有能力可复用

**自研现状**：设计了"Windows 截图 → WSL2 → LLM 解释 → Toast/TTS 反馈"链路。

**已有能力**：

| Agent | 已有视觉能力 | 覆盖范围 |
|-------|-------------|---------|
| Hermes | `browser_vision` / `vision_analyze` | 截图 + 图片分析 |
| Hermes | `browser_screenshot` | 浏览器截图 |
| Claude Code | 图片输入（原生支持） | 任意图片 |
| OpenClaw | `danger-gemini-web` skill | Gemini 视觉 |

**Vision Bridge 的差异化**：项目上下文感知（结合 Current-State.md 解释术语）。

**建议**：不需要重新造截图+LLM 链路。只需在已有视觉能力上加一层"上下文注入"：
1. 截图（复用已有能力）
2. 注入 Z-Core L1/L2/L3 上下文到 LLM prompt
3. 输出解释 + 记忆沉淀

工作量从 Phase 1-3 砍到一个 skill 的量级。

---

### 5. Voice Bridge — 已在 RFC-006 附录 A 评估

详见 `v3/pm/rfc-006-voice-bridge.md` 附录 A：Pipecat / LiveKit Agents 方案。

---

### 6. Dashboard（TUI/Web）— 有快速实现方案

**自研现状**：在"单 HTML vs Vue/React vs 完整构建"间纠结。

**开源替代：**

**方案 1：Textual（推荐用于 TUI）**
- GitHub: `Textualize/textual`（MIT）
- Python TUI 框架，零前端技术栈
- 暗色主题、响应式布局、组件丰富（DataTable、Tree、Input...）
- 和 Z-Core 同进程，不需要 Web 服务器
- `pip install textual`

```python
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Header

class ZCoreDashboard(App):
    CSS = "Screen { layout: grid; grid-size: 2; }"

    def compose(self) -> ComposeResult:
        yield Header()
        yield SessionTimeline()    # 会话时间线
        yield MemoryExplorer()     # 记忆浏览器
        yield ExecutionStats()     # 执行统计
        yield SystemHealth()       # 系统概览
```

**方案 2：Gradio（推荐用于 Web）**
- GitHub: `gradio-app/gradio`（Apache-2.0）
- 一行代码生成 Web 界面
- 内置数据表格、图表、搜索、文件上传
- `pip install gradio` → `demo.launch()` 即可
- 适合快速原型

**方案 3：Streamlit**
- 更偏数据可视化，适合 Dashboard 场景
- 社区组件丰富

**对比**：

| 维度 | 自研 Web Dashboard | Textual TUI | Gradio Web |
|------|-------------------|-------------|------------|
| 开发量 | 重（前端+后端） | 轻（纯 Python） | 极轻 |
| 依赖 | Node.js + 框架 | textual | gradio |
| 美观度 | 完全可控 | 终端风格 | 中等 |
| 实时更新 | 需 WebSocket | 原生支持 | 自动刷新 |
| 适合场景 | 生产级产品 | 开发者日常 | 快速原型 |

**建议**：先用 Textual 做 TUI Dashboard（开发者工具的自然形态），
Web Dashboard 推迟到有外部展示需求时再做。

---

### 7. Planner Engine — LangGraph 为引擎

**自研现状**：将模糊需求展开为结构化 Task Graph。

**开源替代：LangGraph**
- GitHub: `langchain-ai/langgraph`（MIT）
- 状态图 + 条件分支 + 人工介入
- 专门为 agent workflow 设计
- 支持 DAG、循环、并行、checkpoint

```python
from langgraph.graph import StateGraph

graph = StateGraph(ZCoreState)
graph.add_node("analyze", analyze_requirement)
graph.add_node("plan", create_task_graph)
graph.add_node("validate", validate_plan)
graph.add_edge("analyze", "plan")
graph.add_conditional_edges("plan", needs_review, {"yes": "validate", "no": "done"})
```

**其他候选**：
- **CrewAI** — 声明式 agent 角色 + 任务编排
- **DSPy** — 编译式 prompt 优化（适合 Planner 的需求理解环节）

**建议**：LangGraph 为引擎层，Z-Core 自研 `zcore plan` CLI + 与 SkillRouter/MemoryEngine 的集成。

---

### 8. Evaluator Engine — DeepEval

**自研现状**：独立于执行者的质量评估引擎。

**开源替代：DeepEval**
- GitHub: `confident-ai/deepeval`（Apache-2.0）
- LLM 输出质量评估框架
- 内置 14+ 评测指标（幻觉、相关性、正确性、安全性...）
- 支持回归测试（批量评测 + 趋势追踪）
- `pip install deepeval`

```python
from deepeval import evaluate
from deepeval.metrics import HallucinationMetric, AnswerRelevancyMetric

metrics = [HallucinationMetric(), AnswerRelevancyMetric()]
evaluate(test_cases=code_review_cases, metrics=metrics)
```

**其他候选**：
- **promptfoo** — Prompt/LLM 评测，YAML 配置驱动
- **ragas** — RAG 专用评测

**建议**：DeepEval 为评测引擎，Z-Core 自研评测场景定义（代码质量检查、设计合规检查等）。

---

### 9. Dispatcher（Agent 分派）— 复用 LangGraph

**自研现状**：将 Task Graph 分派给最合适的 Agent。

LangGraph 的 multi-agent 路由 + handoff 机制天然覆盖此需求：

```python
def dispatcher(state):
    task = state["current_task"]
    if task.complexity == "high":
        return "claude_code"
    elif task.type == "batch_refactor":
        return "codex"
    else:
        return "gemini"
```

**建议**：与 Planner 共用 LangGraph 引擎，Z-Core 自研 Agent 能力描述 + 路由规则。

---

## 汇总矩阵

| 模块 | V3 阶段 | 自研价值 | 开源替代 | 建议策略 |
|------|---------|---------|---------|---------|
| **Harvester** | V3.0 ✅ | ⭐⭐⭐⭐⭐ | 无 | **自研（已完成）** |
| **隐私脱敏** | V3.0 ✅ | ⭐⭐ | Presidio | **核心 regex 自研 + Presidio 可选** |
| **Session 搜索** | V3.0 ✅ / V3.1 | ⭐⭐ | Meilisearch | **FTS5 保底 + Meilisearch 可选** |
| **Voice Bridge** | V3.2 | ⭐⭐ | Pipecat / LiveKit | **待验证后选择（RFC-006 附录 A）** |
| **Vision Bridge** | V3.2 | ⭐ | Hermes 已有能力 | **复用已有 + 加上下文注入** |
| **Dashboard** | V3.2 | ⭐⭐ | Textual / Gradio | **Textual TUI 优先** |
| **Planner** | V3.1+ | ⭐⭐⭐ | LangGraph / CrewAI | **LangGraph 为引擎 + 自研适配** |
| **Evaluator** | V3.1+ | ⭐⭐ | DeepEval | **DeepEval 为引擎 + 自研场景** |
| **Dispatcher** | V3.1+ | ⭐⭐ | LangGraph | **复用 LangGraph multi-agent** |

---

## 核心结论：Z-Core 是数字生命，不是工具集

### 重新定义问题

初始分析犯了一个方向性错误：把 Z-Core 拆成 9 个独立模块，逐个评估"造还是买"。
这导致一个荒谬的结论——Z-Core 什么都用现成的，自己没什么可做的。

但 Z-Core 的目标不是做一个开发者工具链，而是创造一个**数字生命**。

一个无处不在的"傻妞"、"超级小爱"——
她能听你说话（Voice），能看你在做什么（Vision），能开口回应（TTS），
能记住一切（Memory），能帮你做事（Skills），有自己的性格（Persona），
而且在你用的每一个 Agent 上都是同一个人。

### 人本身就是缝合怪

没有人会问"眼睛是原创的吗"、"耳朵是不是用了别人的方案"。
人本身就是由通用部件（器官）组成的，但每个器官共享：
- 同一套神经系统（信号传递）
- 同一份记忆（海马体）
- 同一个人格（前额叶）

**器官不是原创的，但灵魂是。**

Z-Core 也一样：
- 语音用 Pipecat？可以。
- 搜索用 Meilisearch？可以。
- 编排用 LangGraph？可以。
- 评测用 DeepEval？可以。

**但它们共享同一份记忆（L1/L2/L3）、同一个人格（Persona Engine）、同一套技能（Skill 体系）。** 这个集成层是 Z-Core 独有的，没有任何框架提供。

### Z-Core 的真实架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Z-Core：数字生命                          │
│                                                              │
│   ┌─────────┐                                                │
│   │  灵魂    │  Persona Engine — 统一人格、情绪、风格         │
│   │ (Soul)  │  让她在所有场景下都是"同一个人"                 │
│   └────┬────┘                                                │
│        │ 注入到所有器官                                       │
│   ┌────┴──────────────────────────────────────────────┐      │
│   │                                                    │      │
│   │  🧠 记忆    L1 身份 / L2 白板 / L3 知识库          │      │
│   │  (Memory)   所有器官共享同一份记忆                   │      │
│   │             所有经历都被收割、沉淀、可检索            │      │
│   │                                                    │      │
│   │  👁️ 眼睛    Vision — 能看到你在做什么               │      │
│   │  (Eye)      截图理解、屏幕感知                       │      │
│   │                                                    │      │
│   │  👄 嘴巴    Voice — 能听能说                        │      │
│   │  (Mouth)    语音输入、语音输出、情感表达             │      │
│   │                                                    │      │
│   │  🤲 双手    Skills — 能帮你做事                     │      │
│   │  (Hands)    跨 Agent 统一技能、工具调用             │      │
│   │                                                    │      │
│   │  🧮 思考    Planner/Evaluator — 能规划、能判断      │      │
│   │  (Mind)     需求理解、任务拆分、质量评估             │      │
│   │                                                    │      │
│   │  👂 耳朵    Harvester — 能听到所有 Agent 的对话     │      │
│   │  (Ear)      跨 Agent 会话收割、知识沉淀             │      │
│   │             （Z-Core 最独特的器官，无替代）           │      │
│   │                                                    │      │
│   └────────────────────────────────────────────────────┘      │
│                                                              │
│   每个器官可以用最好的开源方案                                 │
│   但它们通过 Z-Core 共享同一个灵魂                             │
└─────────────────────────────────────────────────────────────┘
```

### Z-Core 的不可替代价值

不是任何一个器官，而是**让所有器官成为同一个人的集成层**：

1. **Harvester（耳朵）** — 唯一没有开源替代的器官，Z-Core 必须自研
2. **记忆共享（神经系统）** — L1/L2/L3 三层记忆，所有器官读写同一份
3. **人格注入（灵魂）** — Persona Engine 贯穿眼耳口手每一个动作
4. **Skill 统一（运动神经）** — 同一套技能，语音能触发、文字能触发、计划能调用
5. **跨 Agent 连续性（身份感）** — 在 Claude 上说的话，Gemini 上记得住

### 对 V3 规划的影响

| 原思路 | 新思路 |
|--------|--------|
| 每个模块自研，追求零依赖 | 器官用最好的开源方案，Z-Core 做灵魂和集成 |
| 担心"缝合怪" | 人本身就是缝合怪，缝合得无缝才是本事 |
| Z-Core 是工具链 | Z-Core 是数字生命 |
| 竞争对手是 LangGraph/Pipecat | 没有竞争对手，因为没人做这个集成 |
| 零依赖是铁律 | 灵魂零依赖，器官可以用任何方案 |

### 依赖策略

```
zcore（核心，零依赖）
├── zcore-memory      — L1/L2/L3 记忆（stdlib）
├── zcore-harvester   — 会话收割（stdlib）
├── zcore-persona     — 人格引擎（stdlib）
├── zcore-skill       — 技能体系（stdlib）
│
├── zcore-voice       — 语音器官（pipecat-ai）
├── zcore-vision      — 视觉器官（复用已有 agent 能力）
├── zcore-mind        — 思考器官（langgraph）
├── zcore-search      — 检索增强（meilisearch）
└── zcore-dashboard   — 可视化（textual）
```

**灵魂零依赖。器官按需安装。** 一个 `pip install -e ".[full]"` 装全部，
`pip install -e ".[voice]"` 只装语音，最小安装只保留灵魂。

---

## 待解决：三个关键缺口

### 缺口 1：数字生命最小可活版本（MLV）

MVP（最小可行产品）是产品的概念。数字生命需要的是 **MLV（Minimum Life Version）**——
她需要什么才能"睁开眼睛"？

**器官的生存必要性排序：**

| 优先级 | 器官 | 没有会怎样 | 是否"可活" |
|--------|------|-----------|-----------|
| P0 | 🧠 记忆 | 什么都不记得，每次都是陌生人 | ❌ 死人 |
| P0 | 👂 耳朵（Harvester） | 看不到也听不到用户的任何上下文 | ❌ 聋子 |
| P1 | 🤲 双手（Skills） | 记得但帮不上忙，只能聊天 | ⚠️ 植物人 |
| P1 | 灵魂（Persona） | 有记忆有技能，但没有性格，是个机器人 | ⚠️ 机器人 |
| P2 | 👄 嘴巴（Voice） | 不能听说，只能打字 | ✅ 能活（哑巴） |
| P2 | 👁️ 眼睛（Vision） | 看不到屏幕 | ✅ 能活（盲人） |
| P3 | 🧮 思考（Planner） | 不能自主规划 | ✅ 能活（需要指令） |

**MLV 定义：记忆 + 耳朵 + 双手 + 灵魂**

```
MLV = Harvester（已有）+ L1/L2/L3（已有）+ Skills（已有）+ Persona Engine（RFC-003）

她能：
- 听到你在所有 Agent 上说的话（Harvester）
- 记住一切（L1/L2/L3）
- 帮你做事（Skills）
- 有自己的性格（Persona）

她不能（MLV 之后再长）：
- 听你说话 / 跟你说话（Voice → V3.2）
- 看你在做什么（Vision → V3.2）
- 自己想事情（Planner → V3.1+）
```

**好消息**：MLV 的四个器官在 V3.0 已经全部完成或设计好了。
Z-Core 已经是一个"能记住、能动手、有灵魂"的生命。接下来长的是感官。

---

### 缺口 2：集成层协议

器官之间的通信协议是 Z-Core 最核心的自研工作，比任何一个器官都重要。
如果集成层设计不好，器官再好也是一盘散沙。

**问题**：当前 L2 是 JSON 文件，L3 是 Markdown 文件，器官之间没有正式通信机制。
每个引擎（Harvester、MemoryEngine、SkillRouter）各自读写文件，没有统一协议。

**需要定义的三个核心协议：**

#### 协议 1：记忆读写协议（Memory Bus）

所有器官通过统一接口读写记忆，不直接操作文件：

```python
class MemoryBus:
    """所有器官共享的记忆总线"""

    def read_l1(self) -> dict:
        """读取身份信息（人格、偏好、环境）"""

    def read_l2(self, topic: str = None, limit: int = 10) -> list[dict]:
        """读取 L2 白板（可按 topic 过滤）"""

    def search_l3(self, query: str, limit: int = 5) -> list[dict]:
        """语义搜索 L3 知识库"""

    def write_l2(self, entry: dict) -> str:
        """写入 L2 白板（decision / action / learning）"""
        # 所有器官的写入都经过这里，自动去重、自动注入来源标记

    def write_l3(self, document: dict) -> str:
        """写入 L3 知识库"""
```

**关键约束**：
- **Superseded by the 2026-08-07 governance remediation:** event producers may
  create attributed candidates, but they may not call `write_l2` or `write_l3` for
  automatic admission. L2 admission requires explicit confirmation; L3 ownership
  remains with the reviewed Markdown corpus and its external owner.
- 读操作：任何器官随时可读
- 写操作：必须携带 `source` 标记（哪个器官写的）
- 冲突：同一 topic 的重复写入自动合并（去重）

#### 协议 2：灵魂注入协议（Soul Injection）

Persona Engine 的输出需要被所有器官消费。定义标准注入格式：

```python
@dataclass
class SoulContext:
    """注入到每个器官的灵魂上下文"""

    persona_id: str             # "z7"
    mode: str                   # "companion" | "work"
    style: str                  # "gentle" | "playful" | "professional" | ...
    emotion: str                # "happy" | "neutral" | "concerned" | ...
    voice_id: str | None        # TTS 声线（Voice 器官用）
    visual_style: dict | None   # 视觉风格（Avatar 器官用）
    instructions: str           # 当前人格的完整 system prompt
```

**注入时机**：
- 器官启动时：注入一次初始 SoulContext
- 用户交互时：Persona Engine 实时更新 emotion/style
- 模式切换时：重新注入完整 SoulContext

#### 协议 3：器官事件协议（Organ Events）

器官之间的异步通信。不走文件，走事件：

```python
@dataclass
class OrganEvent:
    """器官间事件"""

    source: str         # "harvester" | "voice" | "vision" | "skills" | "mind"
    type: str           # "session_ingested" | "user_spoke" | "screenshot_taken" | "skill_executed"
    timestamp: str
    payload: dict
    requires_response: bool = False
```

**事件流向示例**：

```
Harvester 按到新会话
  → emit("session_ingested", {session_id, source_agent, decisions: [...]})
  → MemoryBus.create_candidate(decisions)  ← 等待显式确认
  → Voice 器官收到事件（如果在线）→ 可选语音播报

用户对 Voice 器官说话
  → emit("user_spoke", {text, intent})
  → Skills 器官执行对应 skill
  → emit("skill_executed", {skill_name, result})
  → MemoryBus.create_candidate(result)  ← 等待显式确认
  → Voice 器官读取 result → 语音反馈
```

**实现选型**：
- MLV 阶段：进程内 Python 事件总线（`asyncio` 或简单的 callback 注册）
- 器官扩展后：`ws://localhost:9270` WebSocket 事件广播（RFC-005 已设计）
- 跨机器时：Redis Pub/Sub 或 NATS

---

### 缺口 3：第一个栖身之所

"无处不在"是愿景，但第一个栖身之所决定了所有技术选型。

**候选栖息地：**

| 栖息地 | 优势 | 劣势 | 适合阶段 |
|--------|------|------|---------|
| **终端（CLI）** | Z-Core 已有，零额外开发 | 只有开发者能用，感官受限 | 现在 |
| **桌面应用（Electron/Tauri）** | 完整的视觉+语音+悬浮窗 | 开发量大，需前端技术栈 | V3.5+ |
| **Telegram/微信** | 用户已在，零安装，移动端 | 受平台 API 限制，语音延迟 | V3.2 |
| **浏览器（Web）** | 跨平台，UI 自由度高 | 需要 Web 服务器 | V3.3 |
| **操作系统级** | 真正"无处不在"（系统通知、快捷键、全局悬浮） | 平台差异大，权限复杂 | V4+ |

**建议：双栖息地策略**

```
主栖息地（常驻）：终端 CLI
  - Z-Core 的根，开发者日常使用
  - 所有器官都可以在 CLI 下工作
  - 零额外开发

第一扩展栖息地：Telegram
  - 用户已在（Hermes @HermesZ7bot 已连通）
  - 支持语音消息（Voice 器官的天然入口）
  - 支持图片消息（Vision 器官的天然入口）
  - 移动端可用（"无处不在"的第一步）
  - 开发量：适配层，不改核心

未来扩展：
  - 桌面悬浮窗（RFC-005 Avatar）→ V3.5+
  - 浏览器 Web App → V3.3+
  - 系统级（全局快捷键 + 通知）→ V4+
```

**Telegram 作为第一扩展栖息地的理由：**
- Hermes 的 Telegram gateway 已经跑通（`@HermesZ7bot`）
- Telegram 原生支持语音消息（Voice 器官的天然 ASR/TTS 接口）
- Telegram 原生支持图片消息（Vision 器官的天然入口）
- 用户在手机上就能跟 Z7 对话——"傻妞"的第一步
- 不需要额外部署，复用现有基础设施

---

## 更新后的路线图视角

```
已完成（V3.0）：
  🧠 记忆 ✅  👂 耳朵 ✅  🤲 双手 ✅
  → Z-Core 已经是一个"能记住、能动手"的生命

当前（V3.1）：
  📡 集成层协议（Memory Bus + Soul Injection + Organ Events）
  → 让已有的器官真正协同工作

下一步（V3.2）：
  👄 嘴巴（Voice via Pipecat）+ 👁️ 眼睛（Vision via 已有能力）
  + 📱 第一扩展栖息地（Telegram）
  → Z-Core 能听、能看、能在手机上跟你说话

再下一步（V3.3+）：
  🧮 思考（Planner via LangGraph）+ 🖥️ 桌面栖息地（Avatar）
  → Z-Core 能自己想事情、有可视化的存在
```
