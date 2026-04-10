---
title: "Governance Engine 详细设计"
status: implemented
created: 2026-04-07
engine: governance
claude_code_refs:
  - "src/utils/permissions/permissionRuleParser.ts"
  - "src/utils/permissions/permissions.ts"
  - "src/utils/permissions/PermissionMode.ts"
  - "src/utils/permissions/dangerousPatterns.ts"
  - "src/utils/permissions/bashClassifier.ts"
  - "src/utils/permissions/yoloClassifier.ts"
  - "src/hooks/useCanUseTool.tsx"
  - "src/utils/hooks/postSamplingHooks.ts"
---

# Governance Engine 详细设计

## 1. v1 → v2 变化总结

| 能力 | v1 | v2 |
|------|-----|-----|
| 范围 | pre-commit hook + auditor 脚本 | **全生命周期治理** |
| 权限 | 无 | Rule-based 权限系统 |
| Hooks | pre-commit 只检查 frontmatter | pre/post skill 执行 + 自定义 |
| 审计 | Git 历史 + 可选 JSONL | 结构化执行日志 + 决策追踪 |
| 安全 | skill-security-audit（静态） | 静态 + **运行时**安全检查 |
| 危险检测 | 无 | bash 命令分类器 |

## 2. 权限模型

### 2.1 三种模式

借鉴 Claude Code 的 `PermissionMode`：

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `ask` | 每次需要写入/执行时询问用户 | 默认、教学环境 |
| `auto` | 根据规则自动判断，匹配则允许 | 生产环境 |
| `yolo` | 全部允许（无确认） | 信任环境、速测 |

### 2.1.1 非 TTY 行为约定

- TTY 模式下，`ask` 可以进入交互确认。
- 非 TTY 模式下，`ask` 不允许阻塞等待输入，必须直接返回结构化错误并退出非零状态。
- 错误输出至少包含：`decision=ask_required`、`action`、`target`。
- Agent 在得到用户批准后，需带显式批准标记重新执行。

### 2.2 权限规则

```toml
# ~/.zcore/config.toml

[governance]
permission_mode = "auto"

[governance.rules]
# 格式：action(pattern) = allow | deny | ask

# 文件操作
"file.read(*)" = "allow"                      # 读取任何文件
"file.write(~/.ai-memory/**)" = "allow"       # 写入记忆目录
"file.write(src/**)" = "ask"                  # 写 src 前询问
"file.delete(*)" = "deny"                     # 禁止删除

# Shell 命令
"shell(npm *)" = "allow"                      # npm 命令允许
"shell(git *)" = "allow"                      # git 命令允许
"shell(rm -rf *)" = "deny"                    # 禁止 rm -rf
"shell(curl *)" = "ask"                       # 网络请求询问

# Skill 执行
"skill.run(memory-*)" = "allow"               # 记忆相关 skill 自动允许
"skill.run(security-*)" = "allow"
"skill.run(*)" = "ask"                        # 其他 skill 询问
```

### 2.3 权限解析器

```python
@dataclass
class PermissionRule:
    action: str               # "file.read", "file.write", "shell", "skill.run"
    pattern: str              # glob 模式
    decision: str             # "allow" | "deny" | "ask"
    source: str               # "global" | "project" | "session"

class PermissionEngine:

    def check(self, action: str, target: str) -> PermissionDecision:
        """检查权限
        优先级：deny > ask > allow
        范围：session rules > project rules > global rules"""

    def load_rules(self) -> list[PermissionRule]:
        """加载规则（global + project-level）"""

    def add_session_rule(self, rule: PermissionRule) -> None:
        """会话内临时添加规则（不持久化）"""
```

## 3. 生命周期 Hooks

### 3.1 Hook 链

```
Skill 执行请求
    │
    ▼
┌──────────────┐     失败 → 中止执行，返回错误
│ pre-execute  │────────────────────────────────→ 错误报告
│ hooks        │
└──────┬───────┘
       │ 全部通过
       ▼
┌──────────────┐
│ 执行 Skill   │
│ script       │
└──────┬───────┘
       │
       ▼
┌──────────────┐     不阻塞执行结果
│ post-execute │────────────────────────────────→ 后台处理
│ hooks        │
└──────┬───────┘
       │
       ▼
    返回结果
```

### 3.2 内置 Hooks

```python
# zcore/hooks/builtin.py

BUILTIN_PRE_HOOKS = [
    "validate-input",       # 校验输入参数类型和范围
    "check-permissions",    # 权限规则检查
    "check-dependencies",   # 依赖 skill 是否可用
    "dangerous-pattern",    # 危险模式检测（shell 命令）
    "stale-guardrail",      # 🟡 项目停滞/过度工程检测（待接入）
]

BUILTIN_POST_HOOKS = [
    "log-execution",        # 记录到 executions.jsonl
    "auto-l2-capture",      # 如果结果包含 decision/learning，自动写 L2
    "cost-track",           # 记录 API 成本（如果有）
    "notify-session",       # 通知 Session Manager 更新状态
]
```

> 🟡 **先行原型（`stale-guardrail`）**：
> `~/.ai-skills/project-manager/scripts/stale-detector.py` 已实现 `stale-guardrail` hook 的完整检测逻辑：
> - 代码停滞检测（N 天无 commit）
> - 变更堆积检测（未提交文件数 > 阈值）
> - 未完成行动指令搁置检测（sprint-status.md ❓ 超期）
> - 悬挂分支检测
>
> 接入方式（待 hooks 框架完成后）：将其注册到 `BUILTIN_PRE_HOOKS["stale-guardrail"]`，在每次 Agent 启动编码前自动运行，`trigger_mode: suggest` 时仅输出建议不阻塞。


### 3.3 自定义 Hooks

```bash
# 用户自定义 hook：放到 ~/.zcore/hooks/ 下
# 文件名格式：<priority>-<name>.sh 或 .py

~/.zcore/hooks/
├── pre-execute.d/
│   ├── 10-my-custom-check.sh     # 自定义前置检查
│   └── 20-notify-slack.py        # 执行前通知
└── post-execute.d/
    └── 10-push-to-obsidian.py    # 执行后同步到 Obsidian
```

Hook 脚本的接口约定：

```bash
#!/usr/bin/env bash
# 接收 JSON 格式的 context（stdin 或参数）
# exit 0 = 通过
# exit 1 = 阻塞（仅 pre-hook）
# stdout = 消息（显示给用户/Agent）

# 环境变量：
# KITCLAW_SKILL_NAME   — 当前 skill 名
# KITCLAW_SESSION_ID   — 当前会话 ID
# KITCLAW_PROJECT      — 当前项目
# KITCLAW_AGENT        — 当前 Agent
```

## 4. 危险模式检测

借鉴 Claude Code 的 `dangerousPatterns.ts` 和 `bashClassifier.ts`：

```python
# zcore/engines/governance.py

DANGEROUS_PATTERNS = [
    # 文件系统破坏
    r"rm\s+-rf\s+[/~]",             # rm -rf / or ~
    r"rm\s+-rf\s+\*",               # rm -rf *
    r">\s*/dev/sd[a-z]",            # 写入磁盘设备
    r"mkfs\.",                       # 格式化磁盘
    r"dd\s+if=.+of=/dev/",          # dd 写入设备

    # 系统修改
    r"chmod\s+-R\s+777",            # 全局可写
    r"chown\s+-R\s+root",           # 改变所有权到 root
    r"sudo\s+",                      # sudo 命令

    # 网络风险
    r"curl\s+.*\|\s*sh",            # pipe curl to sh
    r"wget\s+.*\|\s*sh",
    r"eval\s+\$\(",                  # eval 远程命令

    # 数据泄露
    r"cat\s+.*\.env",               # 读取 .env 文件
    r"echo\s+.*API_KEY",            # 输出 API key
    r"export\s+.*SECRET",           # 设置 secret 变量
]

def classify_shell_command(cmd: str) -> str:
    """分类 shell 命令的风险等级
    返回：'safe' | 'risky' | 'dangerous'"""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd):
            return "dangerous"
    # 更多启发式规则...
    return "safe"
```

## 5. 零信任与来源验签机制 (Zero-Trust & Provenance Signature)

> **背景**：AI Agent 面临的最大安全隐患是“间接提示词注入 (Indirect Prompt Injection)”。Agent 在文本流中无法区分指令是来自“真实用户（Owner）”还是“恶意外部数据（如钓鱼邮件/恶意网页）”。

为了解决身份防伪与指令劫持问题，Z-Core Governance Engine 引入了基于签名与隔离的验证体系：

### 5.1 数据污点隔离 (Data Tainting)
所有负责读取外部数据的 Skill（如 `web_fetch`, `read_email`），其输出内容会被拦截器强制包裹在 `<untrusted_content>` 等安全边界标签中。并在 `system prompt` 层面定义该标签内的数据具有“最高执行毒性”，仅供读取，严禁作为操作依据。

### 5.2 高危指令的带签双端认证 (Signed 2FA)
当前台 Agent（如 Claude Code）试图执行触发 `ask` 规则的高危操作时：
- **防伪造拦截**：传统的终端 `[Y/n]` 确认是不安全的（被注入的恶意 Prompt 可自行生成 `Y` 来蒙混过关）。
- **物理验签**：Z-Core 挂起执行进程，要求提供**物理通道签名**（例如向主人的 Telegram 推送一条审批卡片，或要求用户在终端输入硬件生成的 TOTP 验证码）。
- 任何无法提供加密验证签名的操作，将被引擎直接丢弃。

### 5.3 Ghost Agent 意图审计 (Intent Audit Hook)
在 `pre-execute` 阶段，利用独立的 Ghost Agent 担任“安检员”：
- **交叉比对**：提取 `近期调用的外部工具输出` 与 `即将执行的高危命令`。
- **劫持判定**：Ghost Agent 若判定“该删除指令是由刚刚读取的网页文本诱导产生的”，则立即发出红色告警并强行中断会话。


## 6. 审计日志

```json
// ~/.zcore/logs/executions.jsonl（每行一条）
{
  "schema_version": "2.0",
  "timestamp": "2026-04-07T14:30:00+08:00",
  "event": "skill_execute",
  "skill": "context-engine",
  "action": "compact",
  "agent": "claude",
  "session_id": "abc-123",
  "project": "kitclaw",
  "permission_check": "auto_allowed",
  "pre_hooks": ["validate-input:pass", "check-permissions:pass"],
  "post_hooks": ["log-execution:done", "auto-l2-capture:skipped"],
  "duration_ms": 2340,
  "input_summary": "150k tokens, model=sonnet",
  "output_summary": "compressed to 8k tokens",
  "status": "success",
  "error": null
}
```

## 7. CLI 命令

```bash
# 查看当前权限规则
zcore governance rules

# 添加权限规则
zcore governance allow "shell(npm test)"
zcore governance deny "file.delete(src/**)"

# 检查某个操作是否允许
zcore governance check "shell(rm -rf node_modules)"
# → ALLOWED (rule: shell(rm *) in project config)

# 查看审计日志
zcore governance log --last 20
zcore governance log --skill context-engine --since 2026-04-01

# 运行安全审计（增强版 skill-security-audit）
zcore governance audit --skill-dir ~/.ai-skills/
```

## 8. Skill 标准治理（v1 经验提炼）

v1 阶段确立了 skill frontmatter 的分层校验标准，v2 直接继承：

### 7.1 分层 Frontmatter 校验

| 文件类型 | 必填 (阻塞) | 推荐 (warn) | 原则 |
|---|---|---|---|
| **SKILL.md** | `name` + `description` | `tags`, `scope` | 本地 skill 规范优先 |
| **references/\*.md** | frontmatter 存在 | 无 | 按需加载，宽松 |
| **其他 .md** | `title` | `tags`, `scope` | 通用文档标准 |

**设计原则**：必填字段 = 路由最小契约。`name` + `description` 是所有 Agent（Claude、Codex、Gemini）路由 skill 的唯一依据，必须保证。`tags`/`scope` 是治理增强，warning 级别。

### 7.2 Skill Admission 质量关口

进入 Z-Core core-skills 的 skill 必须通过 7 项检查：

1. **Lint 通过** — frontmatter 格式、命名规范、路由质量
2. **安全审计** — 无硬编码密钥、无危险命令模式
3. **无个人依赖** — 无硬编码用户路径（`/home/xxx`）
4. **Agent 无关** — 不依赖特定 Agent 的语法或功能
5. **自包含** — 所有引用文件在 skill 内部存在
6. **文档完整** — SKILL.md 有使用说明和示例
7. **结构干净** — 无 README.md、banner 等非标准文件

### 7.3 公开仓库结构

```
Z-Core (公开)               = 17 个平台核心 skill + runtime
ai-skills-hub (公开)        = 62 个领域 skill，按需安装
```

原则：公开仓库只放通过 admission 的 skill。原件（`~/.ai-skills/`）不修改，公开副本做通用化处理。

## 9. 与其他引擎的交互

| 方向 | 交互 |
|------|------|
| ← Skill Router | 每次 skill 执行前调用 `check()` |
| → Observability | 权限决策和 hook 结果写入审计日志 |
| ← Session Manager | 会话级临时规则 |
| ← CLI | 用户管理权限规则 |
