---
title: "Memory Engine 详细设计"
status: implemented
created: 2026-04-07
engine: memory-engine
claude_code_refs:
  - "src/services/extractMemories/extractMemories.ts"
  - "src/services/extractMemories/prompts.ts"
  - "src/services/SessionMemory/sessionMemoryUtils.ts"
  - "src/memdir/memdir.ts"
  - "src/memdir/memoryScan.ts"
  - "src/memdir/paths.ts"
  - "src/memdir/findRelevantMemories.ts"
---

# Memory Engine 详细设计

## 1. v1 → v2 变化总结

| 能力 | v1（memory-manager） | v2（Memory Engine） |
|------|---------------------|---------------------|
| 存储 | 单一 `whiteboard.json` | 按主题独立 Markdown 文件 + 索引 |
| 触发 | 用户手动调 `l2-capture` | **自动提取**（会话结束时） |
| 去重 | 无 | 编辑距离 + 关键词语义去重 |
| 分类 | decision/action/learning | **4 类**：preference/fact/learning/decision |
| 过期 | 无 | 自动标记 stale → archive |
| 检索 | grep | grep + 向量混合检索 |
| 跨 Agent | 共享 whiteboard | 共享主题文件 + 更好的冲突处理 |

## 2. 记忆分类法（4 类）

借鉴 Claude Code `extractMemories/prompts.ts` 的分类体系，适配 Z-Core：

| 类型 | 含义 | 示例 | 时效性 |
|------|------|------|--------|
| `preference` | 用户个人偏好和工作方式 | "代码风格偏好 4 空格缩进" | 长期 |
| `fact` | 项目/环境的客观事实 | "项目使用 Bun 而非 Node" | 中期 |
| `learning` | 实施中发现的规律或陷阱 | "这个 API 有并发限制 10 req/s" | 中期 |
| `decision` | 两个以上方案之间的明确选择 | "选择 LanceDB 而非 ChromaDB，因为零 infra" | 长期 |

## 3. 存储结构

### 3.1 按主题独立文件

```
~/.ai-memory/
├── config.json                     # v1 兼容
├── whiteboard.json                 # v1 兼容（保留，但不再是主存储）
├── index.json                      # v2 新增：主题索引
└── topics/                         # v2 新增：按主题存储
    ├── user-preferences.md         # preference 类记忆
    ├── project-kitclaw.md          # 项目相关事实
    ├── project-ai-content-hub.md   # 另一个项目
    ├── tech-python.md              # 技术领域
    ├── tech-typescript.md
    └── workflow-patterns.md        # 工作流模式
```

### 3.2 主题文件格式

```markdown
---
topic: "project-kitclaw"
type: mixed                         # preference | fact | learning | decision | mixed
created: 2026-04-07T01:20:00+08:00
updated: 2026-04-07T01:20:00+08:00
entry_count: 5
schema_version: "2.0"
---

# Project: Z-Core

## Decisions

- [2026-04-07] 选择 Python + stdlib argparse 先落地 CLI 骨架，不引入 Rust/Go
  - 原因：先锁定命令契约并保持零额外依赖，后续再评估 Click/Typer
  - 来源：session-abc123

- [2026-04-05] L2 存储从单一 whiteboard.json 迁移到按主题独立文件
  - 原因：whiteboard.json 超过 200 条后检索困难
  - 来源：session-def456

## Facts

- Z-Core 使用 LanceDB 做向量检索
- RAG engine 在 `rag-engine/` 目录下
- 核心 skill 有 7 个（v1）

## Learnings

- [2026-04-06] grep 检索在英文内容上表现好，中文需要分词
```

### 3.3 索引文件

```json
{
  "schema_version": "2.0",
  "updated": "2026-04-07T01:20:00+08:00",
  "topics": {
    "user-preferences": {
      "file": "topics/user-preferences.md",
      "entry_count": 12,
      "types": ["preference"],
      "last_updated": "2026-04-07T01:20:00+08:00"
    },
    "project-kitclaw": {
      "file": "topics/project-kitclaw.md",
      "entry_count": 5,
      "types": ["decision", "fact", "learning"],
      "last_updated": "2026-04-07T01:20:00+08:00",
      "project": "kitclaw"
    }
  },
  "stats": {
    "total_entries": 47,
    "by_type": {
      "preference": 12,
      "fact": 15,
      "learning": 10,
      "decision": 10
    }
  }
}
```

## 4. 核心 API

```python
# zcore/engines/memory.py

@dataclass
class MemoryEntry:
    """单条记忆"""
    id: str                         # UUID
    type: Literal["preference", "fact", "learning", "decision"]
    content: str                    # 记忆内容
    topic: str                      # 所属主题
    created: datetime
    source_session: str | None      # 来源会话 ID
    source_agent: str | None        # 来源 Agent
    status: Literal["active", "stale", "archived"] = "active"
    confidence: float = 1.0         # 置信度（0-1）

@dataclass
class ExtractionResult:
    """自动提取结果"""
    entries: list[MemoryEntry]      # 提取的记忆条目
    duplicates_skipped: int         # 跳过的重复条目
    topics_updated: list[str]       # 更新的主题
    extraction_prompt_used: str     # 使用的提取 prompt

class MemoryEngine:
    """记忆管理引擎"""

    def search(self, query: str, *,
               types: list[str] | None = None,
               topics: list[str] | None = None,
               project: str | None = None,
               limit: int = 10) -> list[MemoryEntry]:
        """混合检索：grep + 向量（如果 LanceDB 可用）"""

    def write(self, entry: MemoryEntry) -> MemoryEntry:
        """写入单条记忆（含去重检查）"""

    def extract_from_conversation(self, messages: list[dict], *,
                                   project: str | None = None,
                                   agent: str | None = None) -> ExtractionResult:
        """从对话中自动提取记忆
        1. 内部装配 system_prompt 与 user_prompt 
        2. 发给底层 Ghost Agent 接口进行推理
        3. 收取 JSON 并解析
        4. 加锁执行：去重 + 分类 + 更新对应主题文件
        5. 解锁并返回执行结果"""

    def dedup(self, entry: MemoryEntry, existing: list[MemoryEntry]) -> bool:
        """判断是否为重复条目
        策略：编辑距离 < 0.15 或关键词重叠 > 85%"""

    def auto_topic(self, entry: MemoryEntry) -> str:
        """自动分类到主题
        策略：关键词匹配已有主题 → 模糊匹配 → 创建新主题"""

    def expire_check(self) -> list[MemoryEntry]:
        """检查过期记忆（90 天未更新的 fact/learning → stale）"""

    def migrate_v1(self) -> int:
        """迁移 v1 whiteboard.json 到 v2 主题文件"""
```

## 5. 自动提取协议

### 5.1 提取 Prompt 模板

```markdown
# zcore/prompts/memory_extract.md

Review the conversation above and extract any durable memories that should
be saved for future sessions. Focus on:

1. **User Preferences** — Working style, coding conventions, tool preferences
2. **Project Facts** — Technical constraints, architecture decisions, environment details
3. **Learnings** — Gotchas, anti-patterns, non-obvious behaviors discovered
4. **Decisions** — Explicit choices between alternatives with reasoning

Rules:
- Extract ONLY information that will be useful in FUTURE conversations
- Do NOT extract transient debugging details or temporary state
- Each memory should be a single, self-contained statement
- Check if a similar memory already exists before writing a new one
- Keep each entry under 200 characters

Output format (JSON):
[
  {"type": "preference", "content": "...", "topic": "..."},
  {"type": "fact", "content": "...", "topic": "..."}
]

Existing memories to check against:
{existing_memories}
```

### 5.2 触发时机

```
会话结束（zcore session end）
    ↓
检查：对话轮数 >= 5？
    ↓ 是
生成提取 prompt + 读取现有记忆列表
    ↓
Z-Core 内部 API 请求 Ghost Agent (Gemini Flash 等)
    ↓
获取响应 (JSON格式抽取的事实)
    ↓
加文件锁 (File Lock)
    ↓
解析 → 去重 → 分类 → 写入各类主题文件
    ↓
释放文件锁，更新全局索引
```

## 6. 与 v1 的兼容

```python
# 读取时：同时搜索 whiteboard.json 和 topics/
# 写入时：只写到 topics/（不再写 whiteboard.json）
# 迁移：zcore migrate 一次性将 whiteboard 条目分配到主题文件
```

`zcore migrate` 的迁移逻辑：
1. 读取 `whiteboard.json` 的所有条目
2. 按 `project` 字段分组
3. 按 `type` 分类
4. 写入对应的 `topics/<project>.md` 或 `topics/<type>.md`
5. 原始 `whiteboard.json` 重命名为 `whiteboard.v1.json.bak`

## 7. Claude Code 参考映射

| 本设计 | Claude Code 源文件 | 借鉴点 |
|--------|-------------------|--------|
| 4 类分类法 | `extractMemories/prompts.ts` | 分类体系 |
| 自动提取逻辑 | `extractMemories/extractMemories.ts` | forked agent 模式 |
| 主题文件存储 | `memdir/memdir.ts` + `memdir/paths.ts` | 目录结构 |
| 去重 | `memdir/memoryScan.ts` | 扫描 + 比对逻辑 |
| 相关记忆检索 | `memdir/findRelevantMemories.ts` | 检索策略 |
|| 阈值触发 | `SessionMemory/sessionMemoryUtils.ts` | `minimumMessageTokensToInit` |

## 8. 日记时间线 UI

借鉴 OpenClaw 2026.4.9「梦境」功能的日记时间线可视化思路，为 Memory Engine 增加面向用户的展示层。

### 8.1 定位

当前 L2/L3 记忆系统完全没有可视化——用户只能通过 Agent 对话间接感知记忆存在，无法自主浏览、审计、修正。时间线 UI 解决的是**记忆透明性**问题：让用户看到 Agent「记住了什么」。

### 8.2 数据源

时间线 UI 直接读取现有存储，不新增数据格式：

| 数据源 | 内容 | 权重 |
|--------|------|------|
| `topics/*.md` | 结构化记忆条目（含时间戳、来源） | 主要 |
| `extraction-log.jsonl` | 提取操作日志（何时提取、置信度、是否自动入库） | 辅助 |
| `staging/pending-confirm.json` | 待确认条目 | 交互入口 |
| `snapshots/index.json` | 对话快照索引 | 可选展开 |

### 8.3 时间线视图设计

```
┌─────────────────────────────────────────────────────────┐
│  📅 2026-04-09                                          │
│                                                         │
│  01:30  🔮 Z-Core                                   │
│         ├── ✅ Persona Engine 选择 file sync 模式       │
│         │      (decision, confidence: 0.92, auto)       │
│         ├── ⏳ Hermes kawaii 会覆盖 SOUL.md 语气        │
│         │      (learning, confidence: 0.65, 待确认)      │
│         └── 📸 对话快照 sess-20260409-001 (23 turns)    │
│                                                         │
│  14:20  🔮 OpenClaw                                     │
│         └── ✅ 升级到 2026.4.9，引入梦境功能            │
│             (action, confidence: 0.88, auto)            │
│                                                         │
│  📅 2026-04-08                                          │
│                                                         │
│  22:15  🔮 健身                                          │
│         └── ✅ 165/50 零基础增肌项目第 3 周完成          │
│             (action, confidence: 0.95, manual)          │
│                                                         │
│  ────────────────────────────────────────────────────   │
│  📊 本周统计: 12 条新增 | 3 待确认 | 2 已归档          │
└─────────────────────────────────────────────────────────┘
```

### 8.4 交互能力

- **浏览**：按日期/主题/类型筛选，支持关键词搜索
- **审计**：点击条目查看来源会话、提取时间、置信度
- **修正**：待确认条目直接 ✅/❌ 操作（同步到 pending-confirm.json）
- **回溯**：点击「对话快照」可展开原始对话片段（从 snapshots/ 读取）

### 8.5 实现路径

**Phase 1 — CLI 时间线**（最小可用）

```bash
zcore memory timeline [--date 2026-04-09] [--topic kitclaw] [--pending]
```

终端表格输出，支持 `--json` 导出。依赖现有存储，零新增依赖。

**Phase 2 — Telegram/消息平台内联**

Agent 在对话中主动展示时间线卡片（类似 OpenClaw 的日记 UI）：

```
Z7: 这是你最近的记忆时间线 👇

4月9日
✅ Persona Engine 用 file sync (decision)
⏳ kawaii 覆盖 SOUL.md 语气 (learning, 待确认)
✅ OpenClaw 升级到 2026.4.9 (action)

回复「详情 N」查看详情 / 「确认 N」确认待定记忆
```

**Phase 3 — Web Dashboard**（远期）

本地 HTTP 服务，`zcore memory serve` 启动，提供完整的 Web 时间线视图。

### 8.6 与 RFC-004 的关系

时间线 UI 是 RFC-004 记忆提取管线的**消费层**——它不改变提取逻辑，只读取提取结果做展示。实现上：

- 读取 `topics/*.md` → 渲染时间线条目
- 读取 `staging/pending-confirm.json` → 渲染待确认交互
- 读取 `extraction-log.jsonl` → 渲染提取历史
- 用户确认操作 → 回写 staging，触发入库

Phase 1 可以在 RFC-004 实现后立即开始，无阻塞依赖。
