# Z-Core 新手上手指南

> 从安装到完成第一个会话，10 分钟快速上手。

---

## 第一步：安装

```bash
# 克隆项目
git clone <your-repo-url> Z-Core
cd Z-Core

# 创建虚拟环境并安装（Python ≥3.11，零外部依赖）
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 验证安装
zcore --version
# → zcore 0.2.0
```

---

## 第二步：初始化

```bash
zcore init
```

```
Initialized Z-Core runtime
  Runtime: /home/you/.zcore
  Config: /home/you/.zcore/config.toml
  Shared rules: /home/you/.zcore/shared-rules.yaml
```

这会创建 `~/.zcore/` 目录，里面包含配置文件和运行时数据目录。

---

## 第三步：检查系统状态

```bash
zcore status
```

```
Z-Core Status
  Version: 0.2.0
  Runtime: /home/you/.zcore
  Config: present
  Active sessions: 0
  Whiteboard entries: 0
  Topic files: 0
  Ghost Agent: fallback (google/gemini-2.5-flash)
  File locking: ready
```

```bash
zcore doctor
```

```
Z-Core Doctor
  Healthy: yes
```

> 💡 **所有命令都支持 `--json` 标志**，输出结构化 JSON。Agent 应始终使用 `--json` 模式。

---

## 第四步：（可选）启用 Ghost Agent

Ghost Agent 是 Z-Core 的后台 LLM，用于自动压缩上下文和提取记忆。不启用也能正常工作（降级为启发式模式）。

```bash
# 启用 Ghost Agent
zcore config set llm_backend.enabled true

# 设置 API Key（推荐用环境变量）
export KITCLAW_LLM_API_KEY="your-api-key"

# 可选：切换模型
zcore config set llm_backend.provider google
zcore config set llm_backend.model gemini-2.5-flash
```

> 不设 API Key 也完全可用——Z-Core 会自动降级为启发式提取模式（用正则匹配 `[decision]`/`[fact]` 标记）。

---

## 第五步：开始你的第一个会话

```bash
zcore session start --project my-app --agent claude
```

```
Session started: 802718d8b3f4
```

查看活跃会话：

```bash
zcore session list
```

```
802718d8b3f4    my-app    claude    active
```

---

## 第六步：工作过程中使用记忆

### 6.1 从对话中提取记忆

假设你有一段对话保存在 `messages.json`（Agent 通常会自动生成）：

```json
[
  {"role": "user", "content": "设计 REST API 框架"},
  {"role": "assistant", "content": "[decision] 使用 FastAPI，它支持自动 OpenAPI 文档"},
  {"role": "assistant", "content": "[decision] 使用 PostgreSQL + SQLAlchemy ORM"},
  {"role": "assistant", "content": "[fact] FastAPI 的依赖注入可以管理数据库连接池"}
]
```

提取记忆：

```bash
zcore memory extract --input messages.json --model sonnet --project my-app
```

```
Extracted 4 entries (0 admitted, 3 pending, 1 discarded)
```

> 💡 **置信度分流机制**：
> - `>0.8`：自动入库
> - `0.5~0.8`：放入 pending 待人工确认
> - `<0.5`：丢弃

### 6.2 确认待审记忆

```bash
# 查看待确认的记忆
zcore memory pending
```

```
520f4bf2cbee: [decision] 使用 FastAPI，它支持自动 OpenAPI 文档
bfb2d7788c19: [decision] 使用 PostgreSQL + SQLAlchemy ORM
cf2a5608488b: [decision] 使用 JWT token + OAuth2 密码流
```

```bash
# 确认一条记忆（永久写入主题存储）
zcore memory pending --confirm 520f4bf2cbee
```

### 6.3 手动写入记忆

```bash
zcore memory write "项目代号 Phoenix，目标 3 个月内上线 MVP" \
  --topic my-app --tags "project,timeline"
```

### 6.4 搜索记忆

```bash
zcore memory search --query "FastAPI"
```

```
- [decision] 使用 FastAPI，它支持自动 OpenAPI 文档
    (source: heuristic, confidence: 0.70, date: 2026-04-10)
```

### 6.5 查看记忆统计

```bash
zcore memory topics     # 按主题查看条目数
zcore memory stats      # 总体统计
```

---

## 第七步：分析上下文

当对话变长，可以用上下文分析检查 token 使用情况：

```bash
zcore context analyze --input messages.json --model sonnet
```

```
Context Analysis
  Total tokens: 87
  Context window: 200000
  Usage: 0.04%
  Remaining: 199913
  Should compact: no
  Urgency: normal
```

如果 `Should compact: yes`，执行压缩：

```bash
zcore compact --input messages.json --model sonnet
```

---

## 第八步：结束会话

```bash
zcore session end --session-id 802718d8b3f4 --messages messages.json
```

```
Session ended: 802718d8b3f4
设计 REST API 框架       ← 自动生成的摘要
```

会话结束时自动完成：
- 💾 保存上下文快照（`context.json.gz` + `context.md`）
- 🧠 提取记忆（`memories.json`）
- 📝 生成人可读摘要

查看会话快照文件：

```bash
ls ~/.zcore/sessions/802718d8b3f4/
# → context.json.gz  context.md  memories.json  meta.json
```

---

## 第九步：暂停 / 恢复会话

工作中途需要暂停？

```bash
# 开始新会话
zcore session start --project my-app --agent gemini

# 暂停（不结束，不提取记忆）
zcore session pause
# → Session paused: 81b6baad6688

# 稍后恢复
zcore session resume
# → Session resumed: 81b6baad6688
```

---

## 第十步：跨 Agent 交接

把会话从 Claude 交给 Gemini 继续：

```bash
zcore session handoff --session-id <id> --to gemini --note "请继续实现认证模块"
```

这会生成一份结构化的交接文档，包含上下文摘要、关键决策和未完成事项。

---

## 第十一步：可观测性

```bash
# 执行统计
zcore observe stats --since 7d

# 成本报告（Ghost Agent API 用量）
zcore observe costs --since 30d

# 健康检查
zcore observe health
```

---

## 第十二步：治理与安全

```bash
# 查看当前权限规则
zcore governance rules

# 添加拒绝规则（禁止删除操作）
zcore governance deny "rm -rf *"

# 查看执行日志
zcore governance log --last 10

# 审计报告
zcore governance audit
```

---

## 常用命令速查

| 场景 | 命令 |
|------|------|
| 初始化 | `zcore init` |
| 开始工作 | `zcore session start --project <名> --agent <agent> --json` |
| 查询记忆 | `zcore memory search --query "关键词" --json` |
| 分析上下文 | `zcore context analyze --input <文件> --model <模型> --json` |
| 结束会话 | `zcore session end --session-id <id> --messages <文件> --json` |
| 暂停/恢复 | `zcore session pause` / `zcore session resume` |
| 手动记忆 | `zcore memory write "内容" --topic <主题>` |
| 健康检查 | `zcore doctor --json` |
| 查看状态 | `zcore status --json` |

---

## 下一步

- 📖 阅读[架构设计](v2/design/architecture.md)了解 9 引擎如何协作
- 🛡️ 配置[治理规则](v2/design/governance.md)保护你的开发环境
- 🔧 浏览[技能路由文档](v2/design/skill-router.md)了解如何安装和管理技能
- 🤖 运行 `zcore setup claude`（或 `gemini`/`codex`）让 Agent 自动学会使用 Z-Core
