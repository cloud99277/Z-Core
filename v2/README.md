# Z-Core — Planning Hub

> **定位转型**：从 "共享 Skill 脚本集" → "有自己后台脑力的 Agent 运行时中间件"
> **架构突破**：Ghost Agent — 配属独立廉价小模型，实现全自动压缩/记忆提取闭环
> **当前状态**：**V2 收官** — 9 Engine / 35 CLI / 39 测试 / 0 外部依赖 / `pip install zcore` 可用

## 目录结构

```
v2/
├── README.md              ← 你在这里
├── design/
│   ├── product-strategy.md                # 产品战略（诊断 + 定位 + Ghost Agent）
│   ├── architecture.md                    # 整体架构（9 引擎 + Ghost Agent 层）
│   ├── context-engine.md                  # 上下文引擎（Ghost Agent 压缩）
│   ├── memory-engine.md                   # 记忆引擎（Ghost Agent 提取 + 日记时间线）
│   ├── session-manager.md                 # 会话管理（跨 Agent 续接 + 暂停/恢复）
│   ├── skill-router.md                    # Skill 路由（三层路由 + 编排）
│   ├── governance.md                      # 治理引擎（权限 + hooks + 零信任）
│   ├── cli.md                             # 统一 CLI 设计
│   ├── shared-rules-injection.md          # 共享规则注入设计（跨 Agent 一致性）
│   ├── hermes-as-runtime.md               # Hermes 作为 Z-Core 最佳运行时载体
│   ├── market-validation.md               # 行业风向印证
│   ├── ghost-agent-deep-review.md         # Ghost Agent 10 维深度审查
│   └── V2-AUDIT-REPORT.md                 # v2 全套文档架构审查报告
│
├── rfcs/
│   ├── 001-runtime-vs-scripts.md           # 轻量运行时 > 纯脚本 > daemon
│   ├── 002-ghost-agent-backend.md          # Ghost Agent 后台智能闭环方案 ✅ accepted
│   ├── 003-unified-persona-engine.md       # Z7 统一人格跨 Agent 同步（→ V3）
│   ├── 004-memory-extraction-pipeline.md   # Ghost Agent 记忆自动提取管线
│   └── 005-embodied-companion-ui.md        # V3 具身伴侣表现层（3D/2D + TTS）
│
├── pm/                    ← 项目管理文件
│   ├── Current-State.md                    # 当前快照
│   ├── Sprint-Backlog.md                   # 里程碑 + 任务清单
│   ├── Decision-Log.md                     # 决策追踪（只追加）
│   ├── Changelog.md                        # 变更日志
│   ├── sprint-status.md                    # Sprint 状态报告
│   ├── tasks/                              # Codex 任务文件
│   │   ├── Phase4-Codex-Task.md
│   │   ├── Phase5-Codex-Task.md
│   │   └── Phase6-Codex-Task.md
│   └── reviews/                            # 阶段审查报告
│       ├── Phase0-Review.md
│       ├── Phase1-Review.md
│       ├── Phase2-Review.md
│       ├── Phase3-Review.md
│       ├── Phase4-Review.md
│       ├── Phase5-Review.md
│       └── Phase6-Review.md
│
└── references/            ← 外部参考资料
    └── claude-code-patterns.md  ← 从 Claude Code 提取的设计模式
```

## 运行时代码

Phase 0-6 已交付 `zcore/` Python 包（仓库根目录下），版本 `0.2.0`：

```
zcore/                              # pip install -e . → CLI 命令 `zcore`
├── __init__.py
├── __main__.py                     # python -m zcore 入口
├── __version__.py                  # 版本号 0.2.0
├── cli/
│   ├── __init__.py
│   └── main.py                     # argparse CLI（35 个命令，全覆盖）
├── engines/
│   ├── context.py                  # Context Engine（analyze + compact + 预裁剪）
│   ├── ghost_agent.py              # Ghost Agent（4 provider API + heuristic fallback + budget）
│   ├── memory.py                   # Memory Engine（TopicStore + extract + dedup + expire）
│   ├── session.py                  # Session Manager（start/end/pause/resume/handoff/cleanup）
│   ├── router.py                   # Skill Router（三层路由 + install/validate）
│   ├── governance.py               # Governance Engine（权限规则 + 危险 shell 分类 + audit）
│   ├── observability.py            # Observability Engine（执行统计 + 成本追踪 + 健康报告）
│   ├── agent_setup.py              # Agent Setup Engine（检测 + 标记块注入）
│   └── workflow.py                 # Workflow Engine（TOML 定义 + discover/validate/run）
├── models/
│   ├── session.py                  # SessionMeta dataclass（含 pause/resume 状态）
│   ├── memory.py                   # MemoryEntry dataclass（4 类分类法 + expired）
│   ├── skill.py                    # SkillManifest + 激活/权限/IO 配置
│   └── workflow.py                 # WorkflowDefinition + StepResult + WorkflowResult
├── hooks/
│   ├── lifecycle.py                # HookRunner + 自定义 hook 脚本加载
│   └── builtin.py                  # 内置 hooks（validate-input/check-permissions/log-execution）
├── utils/
│   ├── tokens.py                   # Token 估算（tiktoken + 中英文字数 fallback）
│   ├── prompts.py                  # Prompt 模板加载器
│   ├── frontmatter.py              # stdlib YAML frontmatter 解析器
│   ├── fs.py                       # 原子文件写入（tmpfile + os.replace）
│   ├── filelock.py                 # fcntl.flock + 超时 + Windows 降级
│   ├── privacy.py                  # 正则脱敏（API key/路径）
│   └── time.py                     # 时间窗口解析（d/h/w/m 后缀）
├── compat/
│   └── legacy_skills.py            # v1 skill 兼容桥接
├── config.py                       # config.toml 渲染/加载/set/reset/掩码
├── runtime.py                      # RuntimePaths discover（环境变量覆盖）
├── paths.py                        # 路径辅助
└── prompts/
    ├── compact.md                  # 6 段式压缩 Prompt 模板
    ├── session_handoff.md          # 会话交接文档模板
    └── memory_extract.md           # 记忆提取 Prompt 模板
```

## 与 v1 的关系

- v1 代码保持不动，继续可用，**视为只读兼容层**
- v2 规划在 `v2/` 目录下进行，运行时代码在 `zcore/` 包下
- 开发在 `feat/v2` 分支上进行
- 当前独立仓库统一使用 `Z-Core` / `zcore` 命名；历史文档中的 `KitClaw V2` 表述仅代表来源背景
- v1 的 `~/.ai-memory/` 和 `~/.ai-skills/` 目录由 v2 直接读取，不改造

## 目标里程碑

| Phase | 内容 | 产物 | 状态 |
|-------|------|------|:----:|
| 0 | 统一 CLI 入口 | `zcore` bootstrap（init/status/doctor/session） | ✅ 完成 |
| 1 | Context Engine + Session 增强 | 对话压缩 + Ghost Agent 真实 API + Session 续接 | ✅ 完成 |
| 2 | Memory Engine 升级 | 自动记忆提取 + 去重 + 主题文件 | ✅ 完成 |
| 3 | Skill Router + Governance | 三层路由 + 权限引擎 + Hook 框架 | ✅ 完成 |
| 4 | Observability + Agent Setup | 成本追踪 + Agent 检测/注入 + Config CLI | ✅ 完成 |
| 5 | CLI Completeness | Skill/Session/Memory/Audit 补全 + 测试整治 | ✅ 完成 |
| 6 | V2 收官 | Workflow Engine + Session pause/resume + pip 打包 | ✅ 完成 |

**V2 进入维护模式。V3 规划见 `pm/ideas/`。**

## 关键参考

- [v2 产品战略](./design/product-strategy.md)
- [统一 CLI 设计](./design/cli.md)
- [整体架构](./design/architecture.md)
- [Ghost Agent 深度审查](./design/ghost-agent-deep-review.md)
- [审查报告](./pm/reviews/)（Phase 0-6，共 7 份）
- [当前状态](./pm/Current-State.md)
- [Sprint Backlog](./pm/Sprint-Backlog.md)
- [v1 记忆架构](../docs/memory-architecture.md)
- [v1 Skill 规范](../docs/skill-specification.md)
