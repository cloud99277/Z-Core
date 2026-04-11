# Decision Log

## [2026-04-11] 正式归档 KitClaw，将其余特性并入 Z-Core

**决策：**
- 彻底废弃分离式中间件（Standalone Middleware）概念，将 Z-Core 升级为 唯一入口的 KitClaw 迭代品（V2）。
- 吸收 17 个 Core Skill 与 RAG 能力，提供统一的命令空间与包管理体验 (`zcore skill install --core`, `zcore[rag]`)。

**原因：**
- 分离状态削弱了两侧的使用者体验，双面维护徒增工作负荷，严重违背 All-in-One 一致性初衷。

**影响：**
- KitClaw 仓库结束其生命周期，标记为 `Deprecated`。
- Z-Core 获得完全统治力及原先欠缺的具体功能包。
## [2026-04-07] PM 体系初始化

**决策：** 采用 6 文件 PM 管理体系。

**原因：** 平衡完整性和维护成本，Agent 可自动维护。

**影响：** 每次重要决策和状态变更自动记录。

---

## [2026-04-09] 命名冻结与 Phase 0 收口

**决策：**
- `KitClaw` 保留为仓库 / 平台品牌名。
- `Z-Core` 保留为 v2 runtime codename。
- `zcore` 统一作为 v2 Python package 名与 CLI 命令名。
- Phase 0 只交付 bootstrap 骨架：包结构、CLI 根路由、`zcore init`、`zcore status`。

**原因：**
- 之前文档混用 `kitclaw` / `zcore` / 失效引用，导致实现入口不稳定。
- 先收口骨架，才能控制后续 Context / Memory / Router 的范围。

**影响：**
- V2 文档示例统一走 `zcore.*` 包路径和 `zcore` CLI。
- v1 代码在 Phase 0 内保持只读兼容，不主动改造。

---

## [2026-04-09] Phase 0 CLI 框架选择

**决策：** Phase 0 先用 stdlib `argparse` 落地 CLI，而不是直接引入 Click/Typer。

**原因：**
- 当前目标是锁定命令契约与安装骨架，不是追求完整 DX。
- 保持零额外依赖，更符合当前 runtime 轻量化原则。

**影响：**
- `zcore <subcommand>` 的外部命令面先稳定下来。
- 后续如命令复杂度继续上升，再评估迁移 Click/Typer。

---

## [2026-04-10] Phase 0 收口 & Phase 1 启动

**决策：**
- Phase 0 正式收口（commit 41660e7 + 55b6af9），全部 P0+P1 完成，8/8 测试通过。
- Phase 1 聚焦 Context Engine + Ghost Agent 真实 API + Session 续接，不做 Memory Engine。
- Token 估算采用 tiktoken（可选依赖）+ 中英文字数 fallback 双模式。
- Ghost Agent API 调用用纯 stdlib `urllib.request`，支持 google/anthropic/openai/ollama 四个 provider。

**原因：**
- Phase 0 的 Session start/end 已就绪，但缺少真实的压缩/提取能力，Ghost Agent 还是 stub。
- Context Engine 是"上下文永不爆"的基础，是用户感知最强的功能。
- 不做 Memory Engine 是为了避免范围蔓延。

**影响：**
- Sprint-Backlog 更新为 4 个里程碑（Token估算 → API调用 → compact E2E → Session增强）。
- 该任务分配给 Codex 执行，通过 L2 whiteboard 传递上下文。

---

## [2026-04-10] Phase 1 实现收口与超长输入保护

**决策：**
- Phase 1 的 M1-M4 以 `zcore` 包内直接实现落地，不再拆分额外子包。
- Context Engine 对超长 transcript 采用“首部目标 + 尾部当前状态 + 中段采样”的预裁剪策略。
- Ghost Agent 在发往 provider 前统一执行 prompt budget guard，确保极长输入不会打爆后端上下文窗口。
- Phase 1 交付以“自动化回归 + 命令级冒烟 + self-review”三重证据作为完成标准。

**原因：**
- `compact` 和 session handoff 都依赖同一份长上下文数据，若不在引擎层统一处理，风险会反复出现。
- 仅靠 fallback 不足以覆盖“API 可用但输入过长”的失败路径，必须补预算保护。
- Antigravity 审查需要明确可复核的完成证据，而不是只看实现说明。

**影响：**
- `zcore compact`、`session end` 与后续所有 Ghost Agent 调用路径，都受益于统一的长度保护。
- Phase 1 当前可视为功能完成并通过本地验证，后续可以把重点转向 Phase 2。

---

## [2026-04-10] Phase 1 收口 & Phase 2 启动

**决策：**
- Phase 1 正式收口（commit 6f3f16a + dbe51b9 + 0f91bf3），17/17 测试通过，审查建议全部修复。
- Phase 2 聚焦 Memory Engine：自动提取 + 去重 + 主题文件存储 + v1 迁移。
- 去重策略用纯 stdlib `difflib.SequenceMatcher`，不引入 embedding 依赖。
- 置信度三档过滤：>0.8 自动入库，0.5-0.8 写入 pending-confirm.json，<0.5 丢弃。
- 主题文件格式：`~/.ai-memory/topics/{topic}.md`，每行一条 markdown 格式条目。
- 提取 prompt 模板用英文（输出格式统一），但允许中文内容。

**原因：**
- Phase 1 的 Ghost Agent 真实 API 已就绪，可以直接用于驱动记忆提取。
- Memory Engine 是 Z-Core 三大核心能力之一（Context/Memory/Session），Phase 2 自然衔接。
- 不做 Prefetch/睡眠整理/时间线 UI 是为了控制范围。

**影响：**
- Sprint-Backlog 更新为 4 个里程碑（模型+存储 → 提取管线 → 去重+分类 → CLI+迁移）。
- 该任务分配给 Codex 执行，通过 full-cycle-builder Phase 3 流程。

---

## [2026-04-10] Phase 2 收口 & Phase 3 启动

**决策：**
- Phase 2 正式收口（commit 96b7875 + 0fd13b0），23/23 测试通过，审查通过。
- Phase 3 聚焦 Skill Router + Governance + Hooks 三大组件。
- SKILL.md frontmatter 解析用简化 YAML parser（stdlib re），不引入 PyYAML 依赖。
- 路径激活条件用 fnmatch（stdlib），不引入 pathspec 库。
- 危险模式检测用正则静态匹配 12+ 个模式。
- 只做内置 hooks（validate-input, check-permissions, log-execution），不做自定义脚本 hook 执行。
- YAML Workflow 编排执行器明确延期到 Phase 4+。

**原因：**
- Phase 0-2 已完成三大核心引擎（Context/Memory/Session），Phase 3 补全路由和治理。
- 保持零外部依赖原则（P2），用 stdlib 替代 PyYAML 和 pathspec。
- 编排引擎过于复杂且当前优先级不高，延期合理。

**影响：**
- Sprint-Backlog 更新为 4 个里程碑（模型+解析 → 三层路由 → 权限引擎 → hooks+CLI）。
- 该任务分配给 Codex 执行。

---

## [2026-04-10] Phase 3 编码收口

**决策：**
- Phase 3 M1-M4 一次性收口，交付 `SkillManifest`、stdlib frontmatter parser、`SkillRouter`、`PermissionEngine`、builtin hook 框架和 `zcore skill/run/governance` CLI。
- 保持零外部依赖：SKILL frontmatter 继续用 stdlib 解析，路径匹配继续用 `fnmatch`，测试新增改用 stdlib `unittest`。
- `zcore run` 顶层 CLI 用 `parse_known_args()` 透传 skill 自身参数，避免未知参数被 argparse 误拦截。
- 权限匹配优先级按 `deny > ask > allow`，再按 `session > project > global` 决定最终规则。

**原因：**
- Phase 3 的价值在于把“skill 发现/匹配/执行”和“运行时治理”接成闭环，而不是继续停留在设计文档。
- 当前环境没有 `pytest`，新增测试如果继续依赖外部框架，会破坏零依赖开发体验。
- `zcore run <skill> --args...` 是最核心的用户入口，必须优先保证参数透传体验正确。

**影响：**
- `python3 -m zcore skill list/match/run/governance` 已具备可演示闭环。
- `executions.jsonl` 开始具备基础执行日志记录能力，为后续 observability 留好了挂点。
- 全量历史测试仍需后续统一依赖环境，本次 Phase 3 已明确把它记录为独立测试整治项。

---

## [2026-04-10] Phase 3 审查通过

**决策：**
- Phase 3 正式收口，Gemini 独立审查通过（0 Blocking / 3 Non-blocking / 3 Nit）。
- 审查期间修复 2 处问题：`router.py` 的 `__import__("re")` 反模式改为正常 `import re`；`builtin.py` 的 defense-in-depth shell 检测加注释说明意图。
- 28/28 测试全部通过（Phase 0-3 全覆盖），建议进入 Phase 4。

**原因：**
- Phase 3 完成了从"skill 猜测"到"智能路由"的核心能力转变。
- 审查未发现阻塞级问题，Non-blocking 问题已在本次修复或记录为技术债。
- 全部 4 个 Phase 的代码都有对应的审查报告存档在 `v2/pm/reviews/`。

**影响：**
- Phase 4 可以开始规划：Workflow 编排执行器、Observability 升级、Agent Setup 自动化。
- 3 个 Non-blocking 技术债：log_execution 的原子写入保护（低优先级）、`_args_to_cli` 硬编码黑名单、真实 skill 测试的环境依赖。

---

## [2026-04-10] Phase 3 收口 & Phase 4 启动

**决策：**
- Phase 4 聚焦"可观测性 + Agent 集成"：Observability Engine + Agent Setup 自动化 + Config CLI + Governance CLI 扩展 + 自定义 hook 脚本。
- Agent Setup 使用 `<!-- ZCORE:START -->` / `<!-- ZCORE:END -->` 标记块，实现幂等注入到各 Agent 配置文件。
- Persona Engine (RFC-003) 延期到 Phase 5 —— 当前优先级是让 Agent 能自动使用 zcore，而不是人格同步。
- YAML Workflow 编排执行器延期到 Phase 5+ —— 当前手动串联 CLI 命令已够用。

**原因：**
- Phase 0-3 完成了全部核心引擎（Context/Memory/Session/Router/Governance），但 Agent 还没有自动使用 zcore 的路径。
- 缺少 Observability 意味着无法量化 zcore 的价值（执行统计、成本追踪）。
- Agent Setup 是让 zcore 从"工具"变成"中间件"的关键一步——Agent 启动时自动获得 session/memory/context 指令。
- Config CLI 是基础能力缺口，用户无法通过 CLI 管理配置。

**影响：**
- Sprint-Backlog 更新为 4 个里程碑（Observability → Agent Setup → Config CLI → Governance 扩展+自定义 hook）。
- 该任务分配给 Codex 执行。
- Phase 4 完成后，zcore 将具备完整的"引擎 + 治理 + 可观测 + Agent 集成"能力，接近 MVP 状态。

---

## [2026-04-10] Phase 4 实现收口（Codex）

**决策：**
- Observability 采用独立 `ObservabilityEngine`，统一读写 `executions.jsonl` / `costs.jsonl`，CLI 直接复用该 engine。
- Ghost Agent 成本统计采用硬编码公开定价估算（Google Gemini Flash / Anthropic Haiku / OpenAI GPT-4o-mini），失败请求按 0 成本写入日志。
- Agent Setup 采用托管标记块 `<!-- ZCORE:START -->` / `<!-- ZCORE:END -->`，支持幂等替换、备份原文件、`--dry-run` 预演。
- Config CLI 继续坚持零外部依赖：TOML 更新采用 section 级正则替换，写入通过 `FileLock` + 临时文件实现原子落盘。
- HookRunner 在保留 builtin hooks 优先级的前提下，新增 `pre-execute.d/` 与 `post-execute.d/` 脚本加载；脚本排序按文件名，接口契约为 `exit 0/1 + stdout`。

**原因：**
- Phase 4 的核心不是再加一个新抽象层，而是把“已有 runtime 能力”变成可观测、可自动接入、可运维的实际系统。
- 继续坚持 stdlib-only，可以避免为 CLI 管理、hook 执行或配置写回引入额外维护负担。
- 自定义 hook 必须挂在现有 HookRunner 上，才能复用已存在的 lifecycle 和治理路径，而不是并行造一套脚本系统。

**影响：**
- `zcore observe/*`、`zcore setup/*`、`zcore config/*`、`zcore governance allow|deny|log` 已形成完整的 Phase 4 命令面。
- 新增 4 个测试文件、13 个 `unittest` 用例，且按任务文档指定命令完成回归和冒烟验证。
- 下一步可进入 Gemini 独立审查与提交收口流程。

---

## [2026-04-10] Phase 4 审查通过 & Phase 5 启动

**决策：**
- Phase 4 Gemini 独立审查通过（Conditional Pass），审查期间修复 3 个问题：`mask_sensitive_data` 误报、`_parse_since` 扩展 w/m 后缀、测试 helper 去重统一。
- 提交 Phase 4 代码（commit 14e4f22），19/19 测试通过。
- Phase 5 聚焦 CLI 命令树完备性：补全 `skill info/install/validate`、`session show/cleanup`、`memory write/topics/stats`、`governance audit`。
- 同时整治历史测试依赖：让 `unittest discover` 不因外部依赖缺失而报错。
- `session pause/resume` 延期（需状态机设计），`memory expire-check` 延期（需 TTL 策略设计）。
- Persona Engine (RFC-003) 继续延期到 Phase 6+。

**原因：**
- Phase 0-4 已完成全部 Engine 层建设（Context/Memory/Session/Router/Governance/Observability/AgentSetup/GhostAgent），但 CLI 命令树覆盖率约 70%。
- 设计文档定义的 `skill info/install/validate`、`session show/cleanup`、`memory write/topics/stats` 是 Agent 和用户日常操作的高频命令，缺失影响实际使用体验。
- 历史测试的 ImportError 问题积攒了 4 个 Phase，是时候一并整治。

---

## [2026-04-10] Phase 6 收官实现决策

**决策：**
- Workflow Engine 首版采用 TOML schema + 串行 `subprocess.run([sys.executable, "-m", "zcore", ...])` 执行模型。
- Workflow 搜索路径固定为全局 `~/.zcore/workflows/*.toml` 与项目 `.zcore/workflows/*.toml`。
- `session pause/resume` 默认作用于最近一条匹配状态的 session；未指定 `--session-id` 时自动选最近 `active`/`paused`。
- Memory 过期处理采用“标记为 `expired`”策略，不删除、不迁移目录。
- 版本号正式冻结到 `0.2.0`，`__version__` 独立到 `zcore/__version__.py`。
- Editable install 在项目虚拟环境内验证；不使用 `--break-system-packages` 绕过系统 Python 的 PEP 668 保护。

**原因：**
- TOML 可用 stdlib `tomllib`，满足零外部依赖。
- 串行 subprocess 模型足以覆盖 Phase 6 设计目标，同时保持每步与真实 CLI 路径一致。
- 暂停/恢复命令常用于“当前会话”场景，默认定位最近会话能降低 CLI 负担。
- `expired` 标记可逆、可审计，比直接删除更安全。
- 当前 Ubuntu 环境禁止系统级 pip 写入，虚拟环境验证最接近真实用户安装路径且风险最低。

**影响：**
- V2 设计文档中的最后一个 Engine 已落地，CLI 覆盖达到 35/35。
- Workflow 暂不支持变量插值、条件分支与并行编排；这些能力明确留给 V3。
- 交付证据扩展为：39/39 `unittest` 通过、`compileall` 通过、editable install + CLI 冒烟通过。

---

## [2026-04-10] PM 管理体系精简（6 → 5 文件）

**决策：**
- PM 文件体系从 6 文件精简为 5 文件：Current-State、Sprint-Backlog、Decision-Log、sprint-status、Changelog。
- 删除 `Risk-Register.md`：风险信息合并到 Current-State 的"阻塞点/当前最大风险/明确延期"段落。
- 删除 `PM-Agent-Prompt.md`：行为规约已内化到 project-manager SKILL.md 中，独立文件从未被读取过。
- `sprint-status.md` 从非正式文件升级为正式 PM 文件（5 个 Phase 中使用频率最高的文件之一）。
- 新增 `tasks/` 和 `reviews/` 子目录为正式目录结构。
- 同步更新了 `project-manager/SKILL.md`、`init-pm.py`。

**原因：**
- 基于 KitClaw V2 Phase 0-5 的实战反馈：Risk-Register 在 Phase 0 后再未更新（4 条中 3 条 Phase 0 就 Mitigated），PM-Agent-Prompt 从未被任何 Agent 读取。
- sprint-status.md 承担了"行动指令 + 延后池 + 阻塞日志"的核心协调功能，但一直没有正式身份。
- `project-manager` skill 的 collect-status.py 强制前置要求与实际操作不匹配（Agent 直接用 git/view_file 更高效），改为可选。

**影响：**
- `init-pm.py` 将为新项目生成 5 + 2 目录的标准化结构。
- 已有项目（如 KitClaw）无需迁移——只是删除了两个死文件。

---

## [2026-04-10] Phase 5 实现收口（Codex）

**决策：**
- Skill 管理逻辑直接扩展到 `SkillRouter`，不再新建独立 engine；安装支持本地目录优先，Git URL 在 `git` 可用时降级支持。
- 时间窗口解析统一提取到 `zcore/utils/time.py`，避免 observability 和 session cleanup 各自维护一套后缀解析。
- Memory 写入采用最小可用模型：`memory write` 直接写入 `fact` 类型条目，tags 先编码进 `source` 元信息，后续如要强结构化标签再扩展 `MemoryEntry`。
- Governance Audit 采用现有 `rules + executions.jsonl` 聚合，不新增审计存储层。
- 历史测试整治采用 `tests/__init__.py` 的可选依赖探测 + 测试函数级 `unittest.skipIf`，目标是让 `unittest discover` 稳定可跑，而不是重写历史测试。

**原因：**
- Phase 5 的重点是补 CLI 表面积，而不是再引入更多抽象层；直接在现有 Router/Session/Memory/Governance 上增量扩展，风险最低。
- `discover` 的真正问题是导入阶段炸掉，而不是断言失败，所以需要在模块加载前就提供依赖探测和可跳过路径。
- Memory tags 当前不是核心引擎字段，若为 Phase 5 临时扩 schema，会扩大回归面。

**影响：**
- `zcore skill info/install/validate`、`session show/cleanup`、`memory write/topics/stats`、`governance audit` 已可用。
- 新增 4 个 Phase 5 测试文件、10 个 `unittest` 用例，并完成 `discover` 回归。
- 下一步进入 Gemini 独立审查与提交收口流程。

---

## [2026-04-11] Phase 5 审查通过 & Phase 6 启动（V2 收官）

**决策：**
- Phase 5 Gemini 独立审查通过（Pass），0 Blocking 问题，29/29 测试全部通过，CLI 覆盖率达 89%。
- Phase 6 定位为 **V2 收官 Phase**：完成最后 4 个 CLI 命令 + Workflow Engine + pip 打包。
- **Workflow 定义使用 TOML**（不用 YAML），`tomllib` 是 Python 3.11+ stdlib，保持零依赖。
- Session pause/resume 引入 `paused` 状态，暂停时不触发 hook 或 memory 提取。
- Memory expire-check 采用"标记过期"策略（`type = "expired"`），不物理删除。
- pip 打包使用 `pyproject.toml` + `setuptools`，`zcore` 作为 CLI entry point。
- **V2 & V3 分界**：Phase 6 之后 V2 进入维护模式。Codex 提出的 Planner/Evaluator/Dispatcher 架构（见 `v2/pm/ideas/`）归入 V3 规划。

**原因：**
- Phase 0-5 已完成全部 Engine 层和 89% CLI 覆盖率。V2 的架构目标（零常驻、Agent 无关、渐进增强）已全部实现。
- 剩余 4 个 CLI 命令（workflow×3 + session pause/resume + memory expire-check）和打包是收尾工作，不涉及架构变更。
- V3 的 Planner/Evaluator/Dispatcher 是根本性的架构升级（从"辅助引擎"到"主控大脑"），不应与 V2 收尾混合。

**影响：**
- Phase 6 完成后，CLI 覆盖率将达 35/35 = 100%。
- `pip install zcore` 将可用，用户可以直接 `zcore <cmd>` 使用。
- V2 进入稳定维护期，后续 V3 在独立分支或目录中规划。

---

## [2026-04-11] V2 综合审查通过 & 全部文档同步

**决策：**
- V2 综合审查（Antigravity）通过，发现 1 个 P1 Bug + 4 个文档过时 + 1 个测试重复问题，全部当场修复。
- P1 Bug 修复：`SkillRouter.discover()` 添加 try/except 容错，`coding-agent` 的 JSON-style frontmatter 不再导致 crash。
- 10 个设计文档 status 从 `draft` 更新为 `implemented/accepted`。
- `v2/README.md` 全面重写反映 V2 最终状态；`pyproject.toml` description 更新；`cli.md` 添加 argparse 实现说明。
- 测试 helper 统一：`test_zcore_cli.py` 的本地 `run_zcore` 删除，改用 `tests.helpers.run_zcore`。
- V2 正式进入维护模式，全部 PM 文件与代码同步完成。

**原因：**
- 审查发现设计文档在 7 个 Phase 迭代过程中未持续同步，导致新读者可能被 Click 语法示例和过时的包结构图误导。
- `skill list` 的 P1 crash 因测试只覆盖临时目录而未在真实 `~/.ai-skills/` 中发现。
- V2 收官需要确保代码 + 文档 + PM 三方一致，才能可靠地进入维护模式。

**影响：**
- V2 全量交付物：5,457 行代码、9 Engine、35 CLI、39 测试全绿、0 外部依赖、文档完全同步。
- 后续 V3 开发者可以直接阅读设计文档和 README，不会遇到与实现不一致的信息。

---
