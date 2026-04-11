[简体中文](README.md) | [English](README_EN.md)

<div align="center">

# 🐾 Z-Core

**给你的 AI Agent 装上持久记忆、会话管理与技能编排 — 零依赖，纯 CLI。**

[![Author](https://img.shields.io/badge/Author-Cloud927-blue?style=flat-square)](https://github.com/cloud99277)
[![Python](https://img.shields.io/badge/Python-≥3.11-blue?style=flat-square)](https://python.org)
[![Dependencies](https://img.shields.io/badge/外部依赖-0-green?style=flat-square)](#)
[![Tests](https://img.shields.io/badge/测试-50%20通过-brightgreen?style=flat-square)](#-测试)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

---

## ✨ 特点

Claude Code、Gemini CLI、Codex CLI — 每个都很强，但会话一关什么都不记得，也没法无缝使用各种复杂的终端技能。

**Z-Core 作为 KitClaw 的终极演进形态（V2）**，通过单一 CLI 补齐了 Agent 在本地开发中所缺失的全部运行时基建：

- 👻 **Ghost Agent** — 在会话间隙自主思考的 LLM 后端（Z-Core 的灵魂）
- 🧠 **三层记忆** — L1 身份 / L2 白板跨会话去重与提取，并集成可选的 **RAG 向量引擎** 支持 L3 知识库
- 🔄 **会话** — 生命周期管理、暂停/恢复、跨 Agent 工作交接
- 📋 **上下文** — Token 分析、超限自动防爆裁剪
- 🔧 **技能体系** — **内置 17 个高质量核心 Skill**，支持依赖注入、工作流编排和三层路由
- 🛡️ **治理** — 权限规则守门、危险 Shell 检测拦截、执行开销审计
- 🔌 **MCP 管理** — 一处注册 MCP Server，同步到所有主流 Agent
- 📊 **可观测性** — 可视化执行追踪、Token 成本追踪、Agent 健康报告
- 🤖 **自动配置** — 无侵入自动注入指令到 Claude/Gemini/Codex 配置文件

### 核心设计原则

- **零外部依赖** — 仅使用 Python 3.11+ 标准库
- **无常驻进程** — 纯 CLI 工具，调用间无状态
- **Agent 无关** — 适配任何终端原生 AI Agent
- **Ghost Agent** — 自主廉价 LLM 后端，负责压缩/提取

---

## 📦 安装

```bash
git clone <repo-url> Z-Core && cd Z-Core
pip install -e .

# 验证
zcore --version
# → zcore 0.2.0
```

Python ≥3.11，零外部依赖 — 仅使用标准库。

---

## 🚀 60 秒快速上手

```bash
# 1. 初始化运行时
zcore init

# 2. 自动配置你的 Agent（检测 Claude/Gemini/Codex）
zcore setup all

# 3. 开始会话
zcore session start --project my-app --agent claude
# → Session started: 802718d8b3f4

# 4. 正常工作...结束后自动保存上下文和记忆
zcore session end --session-id 802718d8b3f4 --messages messages.json

# 5. 搜索所有历史会话
zcore memory search --query "数据库选型" --json
```

搞定。你的 Agent 现在有持久记忆了。

---

## 🏗️ 工作原理

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Claude Code │  │ Gemini CLI  │  │  Codex CLI  │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       └────────────────┼────────────────┘
                        │
               ┌────────▼────────┐
               │    Z-Core CLI   │
               │  (零外部依赖)   │
               └────────┬────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
  ┌─────▼─────┐  ┌──────▼──────┐  ┌────▼─────┐
  │  Memory   │  │  Sessions   │  │  Skills  │
  │ ~/.ai-    │  │  ~/.zcore/  │  │ ~/.ai-   │
  │ memory/   │  │  sessions/  │  │ skills/  │
  └───────────┘  └─────────────┘  └──────────┘
```

Z-Core 是**无状态 CLI** — 没有守护进程，没有后台服务。每次调用直接读写文件。Agent 通过 `zcore <command> --json` 调用，获取结构化 JSON 返回。

---

## 👻 Ghost Agent — Z-Core 的灵魂

Z-Core 的引擎负责记忆、会话和技能。但 **Ghost Agent** 才是让它*自主*运转的核心。

Ghost Agent 是一个廉价 LLM 后端，在你的**会话之间**运行 — 压缩长对话、提取决策和事实、按置信度分流记忆。这就是 Z-Core 能在你不手动维护的情况下保持持久上下文的原因。

```
  你关掉 Claude Code
         │
         ▼
  ┌──────────────────┐
  │  Ghost Agent     │
  │                  │
  │  1. 读取对话记录  │
  │  2. 提取决策/事实 │
  │  3. 压缩上下文    │
  │  4. 去重          │
  │  5. 置信度分流    │
  │                  │
  │  ~$0.01/次会话   │
  └────────┬─────────┘
           │
           ▼
  你打开 Gemini CLI → 记忆已经就位
```

**为什么重要：**
- 你的 Agent 会话是**昂贵的**（Claude Opus、Gemini Pro）。别把上下文窗口浪费在整理工作上。
- Ghost Agent 用**廉价模型**（Gemini Flash，$0.30/百万输入 token）干这些脏活。
- 它**离线运行** — 在会话之间，不在会话期间。对你实际工作零延迟影响。

### 三级降级（永不丢失数据，永不阻塞）

```
Level 0: API 可用       → 完整 LLM 提取 + 压缩
                           总结对话、提取 [decision]/[fact] 标记、
                           与已有记忆去重、打置信度分。

Level 1: API 不可用     → 启发式提取
                           正则扫描 [decision]、[action]、[learning] 标记。
                           没有语义理解，但保留结构。

Level 2: 启发式也失败   → Gzip 原始对话
                           完整对话压缩存储。
                           下次 Ghost Agent 可用时补做处理。
```

原则：**永不丢失数据，永不阻塞用户。** 降级的 Ghost Agent 也比完全没有记忆强。

### 配置

```bash
# 启用 Ghost Agent
zcore config set llm_backend.enabled true

# 设置 API Key（推荐环境变量）
export ZCORE_LLM_API_KEY="***"

# 检查状态
zcore status
# → Ghost Agent: remote (google/gemini-2.5-flash)
```

**成本：** Gemini Flash 约 $0.01/次会话。支持预算上限 `monthly_budget = 5.00`（超限降级）。

**隐私：** 所有 prompt 发送前自动脱敏 — API Key、文件路径、密钥自动抹除。

**支持的提供商：** Google Gemini、Anthropic Claude、OpenAI GPT、DeepSeek、Ollama（本地）。

→ **[Ghost Agent 深度审查](v2/design/ghost-agent-deep-review.md)** — 10 维度架构评估

---

## 📖 核心命令

```bash
# 运行时
zcore init              # 首次初始化
zcore status            # 状态概览
zcore doctor            # 健康检查

# 会话
zcore session start --project <名称> --agent <agent>
zcore session end --session-id <id> --messages <文件>
zcore session pause / resume / handoff

# 记忆与知识 (L2/L3)
zcore memory search --query "关键词"
zcore memory write "重要事实" --topic <主题>
zcore knowledge index             # 需要 zcore[rag]
zcore knowledge search            # 混合语义检索

# 技能与插件 (Skills / MCP)
zcore skill list --available      # 列出内置的 17 个核心功能
zcore skill install --core        # 一键安装
zcore run <skill-name>            # 执行技能
zcore mcp add filesystem --command npx --args "-y,@mcp/server-filesystem,/tmp"
zcore mcp sync --dry-run
```

所有命令支持 `--json` 输出结构化数据。Agent 应始终使用该模式。

→ **[完整上手指南（含真实输出）](docs/getting-started.md)**

---

## 🤖 Agent 自动配置

`zcore setup` 自动向 Agent 配置文件注入托管指令块，让 Agent 自动学会使用 Z-Core：

```bash
zcore setup detect --json     # → claude: true, gemini: true, codex: false
zcore setup claude            # 配置单个 Agent
zcore setup all               # 配置所有检测到的
zcore setup claude --dry-run  # 预览不修改
```

**安全保障：** 幂等注入、自动备份（`.bak`）、不破坏原有内容。

---

## ⚙️ 配置

`~/.zcore/config.toml`：

```toml
[llm_backend]
enabled = false                   # 启用 Ghost Agent
provider = "google"               # google | anthropic | openai | deepseek | ollama
model = "gemini-2.5-flash"        # 推荐：廉价快速模型
monthly_budget = 5.00             # 月度预算上限（美元）
fallback_on_failure = true        # API 失败时降级为启发式模式

[privacy]
redact_before_send = true         # 发送前自动脱敏

[memory]
auto_extract = false              # 会话结束时自动提取记忆

[context]
auto_compact = false              # 上下文超限时自动压缩

[governance]
permission_mode = "ask"           # ask | allow | deny
```

API Key 通过环境变量设置：`export ZCORE_LLM_API_KEY="***"`

---

## 🏗️ 架构

Z-Core 由 **10 个独立引擎** 构成，全部通过 `RuntimePaths` 依赖注入：

| 引擎 | 职责 |
|------|------|
| **GhostAgent** 👻 | 生成 / 可用性检查 / 三级降级（大脑） |
| ContextEngine | 分析 / 压缩 / 预裁剪 |
| MemoryEngine | 提取 / 写入 / 搜索 / 去重 / 过期 |
| SessionManager | 开始 / 结束 / 暂停 / 恢复 / 交接 / 清理 |
| SkillRouter | 发现 / 匹配 / 执行 / 安装 / 验证 |
| PermissionEngine | 检查 / 添加规则 / 审计报告 |
| ObservabilityEngine | 记录执行 / 记录成本 / 统计 / 健康检查 |
| AgentSetupEngine | 检测 / 配置 / 注入 |
| McpEngine | 注册 / 对比 / 同步到各 Agent |
| WorkflowEngine | 发现 / 校验 / 执行 |

---

## 📁 运行时目录

```
~/.zcore/                         # 运行时主目录（zcore init 创建）
├── config.toml                   #   配置文件（权限 0600）
├── shared-rules.yaml             #   共享行为规则
├── mcp-servers.toml              #   MCP Server 注册表
├── sessions/                     #   会话数据
│   ├── index.json                #     会话索引
│   └── <id>/                     #     单次会话
│       ├── context.json.gz       #       上下文快照
│       ├── context.md            #       人可读摘要
│       └── memories.json         #       提取的记忆
├── logs/                         #   执行与成本日志
├── hooks/                        #   前/后置执行 Hook
└── workflows/                    #   工作流定义

~/.ai-memory/                     # 记忆存储
├── topics/                       #   按主题存储的条目
└── whiteboard.json               #   跨会话决策/行动

~/.ai-skills/                     # 技能安装目录
└── <skill-name>/
    ├── SKILL.md                  #   技能清单
    └── scripts/                  #   可执行脚本
```

---

## 📁 项目结构

```
Z-Core/
├── zcore/                  # Python 包
│   ├── cli/main.py         #   argparse CLI（40 个命令）
│   ├── engines/            #   10 个引擎
│   ├── models/             #   数据模型
│   ├── hooks/              #   生命周期 Hook 框架
│   ├── utils/              #   Token 估算、FileLock、脱敏
│   ├── prompts/            #   LLM Prompt 模板
│   ├── config.py           #   TOML 配置管理
│   └── runtime.py          #   RuntimePaths 发现
├── tests/                  # 50 个单元测试
├── docs/                   # 教程与发布说明
├── v2/                     # 设计文档、RFC、项目管理
├── pyproject.toml          # 包配置
└── LICENSE                 # MIT
```

---

## 🧪 测试

```bash
python -m unittest discover tests -v    # 完整测试
python -m unittest discover tests -q    # 快速验证
```

---

## 📚 设计文档

| 文档 | 内容 |
|------|------|
| **[新手上手指南](docs/getting-started.md)** | 10 分钟完整引导，含真实命令输出 |
| [整体架构](v2/design/architecture.md) | 引擎设计、依赖图、配置 schema |
| [记忆引擎](v2/design/memory-engine.md) | 提取、去重、主题存储 |
| [会话管理](v2/design/session-manager.md) | 生命周期、交接、暂停/恢复 |
| [技能路由](v2/design/skill-router.md) | 三层路由与编排 |
| [治理引擎](v2/design/governance.md) | 权限规则与 Hook 框架 |
| [上下文引擎](v2/design/context-engine.md) | Token 分析与压缩 |
| [CLI 设计](v2/design/cli.md) | 命令接口规格 |
| [Ghost Agent 深度审查](v2/design/ghost-agent-deep-review.md) | 10 维度架构评估 |
| [0.2.0 发布说明](docs/release-0.2.0.md) | 独立抽离基线 |

---

## 🙏 参与贡献

欢迎 Issue 和 PR。核心原则：

- 零外部依赖（仅标准库）
- 所有引擎必须通过 `RuntimePaths` 注入
- 所有命令必须支持 `--json` 输出
- 新功能需要测试覆盖

```bash
# 开发环境
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 提交前
python -m compileall zcore tests
python -m unittest discover tests -v
---

## 📦 与 KitClaw 的关系

Z-Core 是 [KitClaw](https://github.com/cloud99277/KitClaw) 的**全面升级与最终继承者**。原 KitClaw 仓库现已正式归档（Archived）。
Z-Core 在完全保留并内置了前代所有核心 Skill 和知识库（RAG）能力的基础之上，引入了 Ghost Agent 机制、统一的命令空间、全局 MCP 注册表以及高级工作流路由引擎。
只需安装 Z-Core（`pip install zcore`），即可获得所有能力，不再需要任何外部仓库。

---

## 📄 许可证

[MIT](LICENSE)

---

<div align="center">

**Made with ❤️ by [Cloud927](https://github.com/cloud99277)**

</div>
