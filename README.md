[简体中文](README.md) | [English](README_EN.md)

<div align="center">

# 🐾 Z-Core

**为 AI Agent 提供共享记忆、上下文管理、MCP 同步与技能编排的运行时中间件**

[![Author](https://img.shields.io/badge/Author-Cloud927-blue?style=flat-square)](https://github.com/cloud99277)
[![Python](https://img.shields.io/badge/Python-≥3.11-blue?style=flat-square)](https://python.org)
[![Dependencies](https://img.shields.io/badge/外部依赖-0-green?style=flat-square)](#)
[![Tests](https://img.shields.io/badge/测试-50%20通过-brightgreen?style=flat-square)](#测试)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

---

## 它是什么

Z-Core 是一个 **Agent 无关** 的运行时中间件，为你的 CLI Agent（Claude Code、Gemini CLI、Codex CLI 等）提供统一的底层基础设施：

| 能力 | 说明 |
|------|------|
| 🧠 **记忆** | 跨会话持久化记忆，按主题存储、自动提取、智能去重、过期管理 |
| 📋 **上下文** | Token 分析、通过 Ghost Agent 后台 LLM 自动压缩 |
| 🔄 **会话** | 会话生命周期、暂停/恢复、跨 Agent 交接 |
| 🔧 **技能** | 三层智能路由、生命周期 Hook、安装/验证 |
| 🛡️ **治理** | 权限规则、危险 Shell 检测、执行审计 |
| 📊 **可观测性** | 执行统计、成本追踪、健康报告 |
| 🤖 **Agent 设置** | 自动注入指令到 Claude/Gemini/Codex 配置文件 |
| 🔌 **MCP 管理** | 一处注册 MCP Server，并同步到多个 Agent 配置 |
| 🔁 **工作流** | 基于 TOML 的多步骤技能编排 |

### 核心设计原则

- **零外部依赖** — 仅使用 Python 3.11+ 标准库
- **无常驻进程** — 纯 CLI 工具，调用间无状态
- **Agent 无关** — 适配任何终端原生 AI Agent
- **Ghost Agent** — 可选的廉价 LLM 后端，实现全自动压缩/提取闭环

---

## 快速开始

```bash
# 安装（Python ≥3.11，零外部依赖）
pip install -e .

# 初始化运行时
zcore init

# 自动配置你的 Agent（Claude、Gemini、Codex）
zcore setup all

# 注册并预演同步一个 MCP Server
zcore mcp add filesystem --command npx --args "-y,@modelcontextprotocol/server-filesystem,/tmp"
zcore mcp sync --dry-run --json

# 检查系统健康状态
zcore doctor --json
```

完成 — 你的 Agent 现在已经自动学会使用 Z-Core 了。

---

## Agent 自动配置

`zcore setup` 会自动将 Z-Core 的使用指令注入到 Agent 的配置文件中，让它们自动学会使用会话、记忆和上下文管理。

```bash
# 检测已安装的 Agent
zcore setup detect --json
# → claude: detected=true, gemini: detected=true, codex: detected=false

# 配置单个 Agent
zcore setup claude

# 一次配置所有检测到的 Agent
zcore setup all

# 预览变更但不修改
zcore setup claude --dry-run
```

执行后，会在 Agent 配置文件（如 `~/.claude/CLAUDE.md`）中**幂等注入**一个托管标记块：

```markdown
<!-- ZCORE:START (managed by zcore setup, do not edit manually) -->
## Z-Core Runtime Integration

- 开始新任务时：`zcore session start --project <project> --agent <agent> --json`
- 完成任务后：`zcore session end --session-id <id> --json`
- 搜索记忆：`zcore memory search --query "<query>" --json`
- 上下文分析：`zcore context analyze --model <model> --input <file> --json`
- 执行 skill：`zcore run <skill-name> [--args] --json`
- 所有 zcore 命令都加 `--json` 获取结构化输出
<!-- ZCORE:END -->
```

**安全保障：**
- **幂等性** — 重复执行不会重复注入
- **自动备份** — 修改前自动创建 `.bak` 文件
- **`--dry-run`** — 预览变更但不实际修改
- **不破坏原有内容** — 只操作标记块内的内容

---

## 新手上手（5 分钟走通）

### 1. 开始会话

```bash
zcore session start --project my-app --agent claude
# → Session started: 802718d8b3f4
```

### 2. 从对话中提取记忆

将对话保存为 `messages.json`，然后提取决策和事实：

```bash
zcore memory extract --input messages.json --model sonnet --project my-app
# → Extracted 4 entries (0 admitted, 3 pending, 1 discarded)
```

Z-Core 的置信度分流机制：
- **>0.8** — 自动入库
- **0.5–0.8** — 放入 pending 待人工确认
- **<0.5** — 丢弃

### 3. 确认待审记忆

```bash
# 查看待确认的记忆
zcore memory pending
# → 520f4bf2: [decision] 使用 FastAPI，支持自动 OpenAPI 文档
# → bfb2d778: [decision] 使用 PostgreSQL + SQLAlchemy ORM

# 确认一条
zcore memory pending --confirm 520f4bf2
```

### 4. 跨会话搜索记忆

```bash
zcore memory search --query "数据库" --json
```

### 5. 结束会话（自动保存一切）

```bash
zcore session end --session-id 802718d8b3f4 --messages messages.json
# → Session ended: 802718d8b3f4
# → 自动保存：上下文快照 + 提取的记忆 + 摘要
```

### 6. 暂停 / 恢复 / 交接

```bash
# 暂停但不结束
zcore session pause
# → Session paused: 802718d8b3f4

# 稍后恢复
zcore session resume
# → Session resumed: 802718d8b3f4

# 交接给另一个 Agent
zcore session handoff --session-id <id> --to gemini --note "请继续实现认证模块"
```

### 可选：启用 Ghost Agent

Ghost Agent 提供 LLM 驱动的压缩和提取。不启用也完全可用（自动降级为启发式模式）。

```bash
zcore config set llm_backend.enabled true
export ZCORE_LLM_API_KEY="your-api-key"
```

> 📖 完整引导教程：[docs/getting-started.md](docs/getting-started.md)

---

## 架构

Z-Core 由 **10 个独立引擎** 构成，全部通过 `RuntimePaths` 依赖注入：

```
ContextEngine       → 分析 / 压缩 / 预裁剪
MemoryEngine        → 提取 / 写入 / 搜索 / 去重 / 过期
SessionManager      → 开始 / 结束 / 暂停 / 恢复 / 交接 / 清理
SkillRouter         → 发现 / 匹配 / 执行 / 安装 / 验证
PermissionEngine    → 检查 / 添加规则 / 审计报告
ObservabilityEngine → 记录执行 / 记录成本 / 统计 / 健康检查
AgentSetupEngine    → 检测 / 设置 / 注入
McpEngine           → 注册 / 对比 / 同步 MCP Server 到各 Agent
GhostAgent          → 生成 / 可用性检查 / 三级降级
WorkflowEngine      → 发现 / 校验 / 执行
```

### Ghost Agent 三级降级

Ghost Agent 是 Z-Core 的后台智能层，为压缩和记忆提取提供 LLM 算力：

```
Level 0：API 可用 → 正常 LLM 压缩/提取
Level 1：API 不可用 → 启发式提取（关键词 + 结构化数据保留）
Level 2：提取也失败 → 原始对话 gzip 保存，下次补做处理
原则：永不丢失数据，永不阻塞用户
```

---

## CLI 命令一览（40/40）

### 运行时管理

```bash
zcore init [--force] [--json]         # 初始化运行时目录和配置
zcore status [--json]                  # 全局状态概览
zcore doctor [--json]                  # 健康检查
```

### 会话管理

```bash
zcore session start --project <名称> --agent <agent> [--resume-latest] [--json]
zcore session end --session-id <id> [--messages <文件>] [--json]
zcore session list [--project <名称>] [--json]
zcore session show <id> [--json]
zcore session handoff --session-id <id> --to <agent> [--json]
zcore session pause [--session-id <id>] [--json]
zcore session resume [--session-id <id>] [--json]
zcore session cleanup [--older-than 30d] [--dry-run] [--json]
```

### 记忆管理

```bash
zcore memory extract --input <文件> --model <模型> [--project <名称>] [--json]
zcore memory list [--topic <主题>] [--type <类型>] [--json]
zcore memory search --query <查询> [--json]
zcore memory pending [--confirm <id>] [--json]
zcore memory write --content <文本> [--topic <主题>] [--tags <标签>] [--json]
zcore memory topics [--json]
zcore memory stats [--json]
zcore memory expire-check [--older-than 90d] [--dry-run] [--json]
```

### 上下文管理

```bash
zcore context analyze --input <文件> --model <模型> [--json]   # 分析 token 用量
zcore compact --input <文件> --model <模型> [--json]           # 压缩上下文
```

### 技能管理

```bash
zcore skill list [--json]                   # 列出已安装技能
zcore skill match --query <查询> [--json]   # 智能匹配技能
zcore skill info <名称> [--json]            # 查看技能详情
zcore skill install <来源> [--force] [--json]  # 安装技能
zcore skill validate <名称> [--json]        # 校验技能
zcore run <技能> [技能参数...] [--json]     # 执行技能
```

### 治理与安全

```bash
zcore governance rules [--json]                        # 查看权限规则
zcore governance check --action <动作> --target <目标> [--json]  # 权限检查
zcore governance allow <模式> [--json]                 # 添加允许规则
zcore governance deny <模式> [--json]                  # 添加拒绝规则
zcore governance log [--last <n>] [--json]             # 查看执行日志
zcore governance audit [--json]                        # 审计报告
```

### 可观测性

```bash
zcore observe stats [--since <周期>] [--json]   # 执行统计
zcore observe costs [--since <周期>] [--json]   # 成本报告
zcore observe health [--json]                    # 健康报告
```

### Agent 设置

```bash
zcore setup detect [--json]                            # 检测已安装的 Agent
zcore setup claude|gemini|codex|all [--dry-run] [--json]  # 自动配置 Agent
```

### MCP 管理

```bash
zcore mcp list [--json]                                           # 列出注册的 MCP Server
zcore mcp add <name> --command <cmd> [--args <args>] [--env KEY=VAL] [--json]  # 注册 MCP Server
zcore mcp remove <name> [--json]                                  # 从注册表删除
zcore mcp sync [--agent claude|gemini|codex|all] [--dry-run] [--json]  # 同步到 Agent 配置
zcore mcp diff [--json]                                           # 查看注册表与 Agent 配置差异
```

### 配置管理

```bash
zcore config show [--json]                    # 查看配置（敏感字段掩码）
zcore config set <section.key> <值> [--json]  # 修改配置
zcore config reset [--section <名称>] [--json]  # 重置配置
```

### 工作流

```bash
zcore workflow list [--json]                        # 列出工作流
zcore workflow validate <名称|文件> [--json]        # 校验工作流
zcore workflow run <名称|文件> [--dry-run] [--json]  # 执行工作流
```

### 迁移

```bash
zcore migrate [--dry-run] [--json]   # 从 v1 迁移数据
```

> 所有命令均支持 `--json` 标志输出结构化 JSON，Agent 应始终使用该模式。

---

## 测试

```bash
# 运行完整测试套件
python -m unittest discover tests -v

# 快速验证
python -m unittest discover tests -q
```

---

## 项目结构

```
Z-Core/
├── zcore/                  # Python 包
│   ├── cli/main.py         # argparse CLI（40 个命令）
│   ├── engines/            # 10 个引擎
│   │   ├── context.py      #   上下文引擎
│   │   ├── memory.py       #   记忆引擎
│   │   ├── session.py      #   会话管理器
│   │   ├── router.py       #   技能路由器
│   │   ├── governance.py   #   治理引擎
│   │   ├── observability.py#   可观测性引擎
│   │   ├── agent_setup.py  #   Agent 设置引擎
│   │   ├── mcp.py          #   MCP 管理引擎
│   │   ├── ghost_agent.py  #   Ghost Agent
│   │   └── workflow.py     #   工作流引擎
│   ├── models/             # 数据模型
│   ├── hooks/              # 生命周期 Hook 框架
│   ├── utils/              # 共享工具（Token、FileLock、脱敏等）
│   ├── prompts/            # LLM Prompt 模板
│   ├── config.py           # TOML 配置管理
│   └── runtime.py          # RuntimePaths 发现
├── tests/                  # 50 个单元测试
├── v2/                     # 设计文档
│   ├── design/             #   架构与引擎规格书
│   ├── pm/                 #   项目管理（状态、Backlog、决策日志、变更日志）
│   │   └── reviews/        #   Phase 0-6 审查报告（共 7 份 + 综合审查）
│   ├── rfcs/               #   提案文档
│   └── references/         #   外部参考
├── pyproject.toml          # 包配置
├── LICENSE                 # MIT
└── README.md / README_CN.md
```

---

## 运行时目录

Z-Core 使用以下目录（首次 `zcore init` 时自动创建）：

```
~/.zcore/                    # Z-Core 运行时主目录
├── config.toml              #   配置文件（权限 600）
├── shared-rules.yaml        #   共享行为规则
├── sessions/                #   会话数据
│   ├── index.json           #     会话索引
│   └── <session-id>/        #     单次会话
│       ├── context.json.gz  #       上下文快照
│       ├── context.md       #       人可读摘要
│       └── memories.json    #       提取的记忆
├── logs/                    #   日志
│   ├── executions.jsonl     #     执行日志
│   └── costs.jsonl          #     成本日志
└── workflows/               #   全局工作流定义

~/.ai-memory/                # 记忆存储（兼容 v1）
├── topics/                  #   按主题存储的记忆条目
└── pending-confirm.json     #   待确认的低置信度记忆

~/.ai-skills/                # 技能安装目录
└── <skill-name>/
    ├── SKILL.md             #   技能清单（frontmatter + 文档）
    └── scripts/             #   可执行脚本
```

---

## 配置

`~/.zcore/config.toml` 核心配置项：

```toml
[llm_backend]
enabled = true                    # Ghost Agent 开关
provider = "google"               # google | anthropic | openai | deepseek | ollama
model = "gemini-2.5-flash"        # 推荐使用廉价快速模型
monthly_budget = 5.00             # 月度预算上限（美元）
fallback_on_failure = true        # 失败时降级为非 LLM 模式

[privacy]
redact_before_send = true         # 发送前自动脱敏

[memory]
auto_extract = true               # 会话结束时自动提取记忆

[context]
auto_compact = true               # 上下文超限时自动压缩

[governance]
permission_mode = "ask"           # ask | allow | deny
```

API Key 通过环境变量设置（推荐）：

```bash
export ZCORE_LLM_API_KEY="your-api-key"
```

---

## 设计文档

| 文档 | 内容 |
|------|------|
| **[新手上手指南](docs/getting-started.md)** | **10 分钟完整引导，含真实命令输出** |
| [整体架构](v2/design/architecture.md) | 9 引擎设计、依赖关系图、配置 schema |
| [CLI 设计](v2/design/cli.md) | 命令接口规格 |
| [上下文引擎](v2/design/context-engine.md) | Token 分析与压缩 |
| [记忆引擎](v2/design/memory-engine.md) | 提取、去重、主题存储 |
| [会话管理](v2/design/session-manager.md) | 生命周期、交接、暂停/恢复 |
| [技能路由](v2/design/skill-router.md) | 三层路由与编排 |
| [治理引擎](v2/design/governance.md) | 权限规则与 Hook 框架 |
| [MCP 管理任务](v2/pm/tasks/MCP-Management-Codex-Task.md) | MCP 注册表与跨 Agent 同步 |
| [产品战略](v2/design/product-strategy.md) | 愿景与定位 |
| [Ghost Agent 深度审查](v2/design/ghost-agent-deep-review.md) | 10 维度架构评估 |
| [0.2.0 发布说明](docs/release-0.2.0.md) | 独立抽离与发布就绪基线 |

---

## 项目来源

Z-Core 最初来自 [KitClaw](https://github.com/cloud99277/KitClaw) 的 V2 运行时抽离，现已作为独立仓库维护与发布。

两者可独立使用，也可配合运行。

---

## 开发

```bash
# 创建开发环境
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 运行测试
python -m unittest discover tests -v

# 编译检查
python -m compileall zcore tests
```

---

## 许可证

[MIT](LICENSE)

---

<div align="center">

**Made with ❤️ by [Cloud927](https://github.com/cloud99277)**

</div>
