# Z-Core 深度架构分析报告

> 分析对象：`/home/yangyy/projects/Z-Core`（KitClaw V2 进化形态，零依赖纯 CLI Agent 运行时中间件）
> 分析方法：全部结论来自对仓库实际代码的 read / grep / glob 勘察 + 一次真实 `pytest` 运行；所有引用给出**真实文件名与行号**，无臆测。
> 分析时点仓库状态：`git branch` 当前在 `v3/develop`（`main` 并存）；`pyproject.toml` 版本 `0.2.0`；`dist/` 含 `zcore-0.2.0-py3-none-any.whl` 与 `zcore-0.2.0.tar.gz`；V3.0 MVP 已关闭、V3.1 Sprint 进行中（见 `v3/pm/Current-State.md`）。

---

## 0. 一句话结论

Z-Core 是一个**单进程、无守护、文件即状态**的 Python 3.11+ 标准库 CLI 中间件：约 8.7k 行核心代码 + 3.8k 行测试，把"记忆、会话、技能、治理、可观测"全部落成 `~/.zcore` / `~/.ai-memory` / `~/.ai-skills` 目录下的可审计文件；引擎之间通过**构造函数注入 `RuntimePaths`** 松散耦合，但引擎列表、命令命名空间、三层记忆模型、Agent 名单（claude/gemini/codex）都是**硬编码**的——这与 Cordis 的"注册表 + 插件行 + 服务注入 + 热更新"哲学形成鲜明对照（详见第 8 节）。

---

## 1. 代码规模与结构

### 1.1 规模总览

| 度量 | 数值 | 依据 |
|---|---|---|
| zcore/ Python 文件数 | 58 个 | glob `zcore/**/*.py` |
| zcore/ 总代码行 | 8,725 行 | `find zcore -name '*.py' \| xargs wc -l` |
| tests/ 文件数 / 行数 | 29 个文件 / 3,841 行 | 同上 |
| 测试函数数 | 143 个（实测 **142 passed, 1 skipped**） | `grep -rc "def test_"` + 实跑 `pytest tests/ -q` |
| 顶层 CLI 命令 | 19 个 | `cli/main.py:42-374` 的 argparse 注册 |
| 叶子命令（含子命令） | 56 个 | 逐条统计 `add_parser`（详见 2.3） |
| 外部运行时依赖 | 0（`pyproject.toml:12` `dependencies = []`） | RAG 为可选 extra（`pyproject.toml:32-37`） |

### 1.2 包内文件树（按行数降序）

```
zcore/
├── cli/main.py                        1450  ← 唯一 CLI 入口：argparse 构建 + if/elif 分发
├── engines/                           引擎层（14 个文件，含 10 个命名引擎 + 4 个附加引擎）
│   ├── memory.py                       601  MemoryEngine + TopicStore
│   ├── router.py                       512  SkillRouter（三层路由 + 技能执行）
│   ├── context.py                      419  ContextEngine（token 分析 + 压缩）
│   ├── ghost_agent.py                  379  GhostAgent（LLM 调用 + 降级）
│   ├── session.py                      352  SessionManager
│   ├── governance.py                   277  PermissionEngine + 危险命令分类
│   ├── observability.py                252  ObservabilityEngine（执行/成本/健康）
│   ├── knowledge.py                    204  KnowledgeHealthEngine + ExternalReadonlyProvider
│   ├── knowledge_contract.py           185  L2 provider（topic/whiteboard 只读）
│   ├── mcp.py                          196  McpEngine
│   ├── harvester.py                    196  HarvesterEngine
│   ├── agent_setup.py                  194  AgentSetupEngine
│   ├── workflow.py                     190  WorkflowEngine（TOML 编排）
│   └── search.py                       174  SearchEngine（全文扫描）
├── models/                            数据模型层（dataclass + 序列化）
│   ├── knowledge_contract.py           381  CorpusRegistry / ContextPack / L2 报告（强校验契约）
│   ├── skill.py                        250  SkillManifest + activation/lifecycle/permissions/io
│   ├── knowledge.py                    247  KnowledgeHealthManifest（外部索引健康契约）
│   ├── memory.py                       102  MemoryEntry + 三层记忆类型
│   └── session.py / workflow.py / mcp.py / harvester.py / search.py   (32~59)
├── utils/                             工具层
│   ├── frontmatter.py                  237  手写 YAML 子集解析器（零依赖）
│   ├── tokens.py                        93  token 估算（tiktoken 可选 → 字符混合估算）
│   ├── privacy.py                       69  脱敏（默认 9 组正则）
│   ├── filelock.py                      54  FileLock（fcntl flock 咨询锁）
│   └── fs.py / time.py / prompts.py     32 / 16 / 18
├── hooks/
│   ├── lifecycle.py                    111  HookRunner（内置 + 外部脚本钩子）
│   └── builtin.py                       90  内置钩子（validate-input / check-permissions / log-execution）
├── adapters/
│   ├── base.py                          23  SourceAdapter ABC
│   ├── claude_adapter.py               164  读 ~/.claude/projects/*.jsonl
│   └── hermes_adapter.py                91  读 ~/.hermes/sessions/session_*.json
├── rag/                                L3 知识库（可选依赖，lancedb + sentence-transformers）
│   ├── __init__.py                      71  惰性 import + RagDependencyError
│   ├── _md_chunker.py                  176  markdown 分块
│   ├── _knowledge_index.py             148  KnowledgeIndexer + EmbeddingEngine
│   └── _knowledge_search.py            139  向量/FTS/混合检索
├── compat/legacy_skills.py              25  旧版 memory-manager 等脚本兼容入口
├── prompts/                              3 个模板：compact.md / memory_extract.md / session_handoff.md
├── runtime.py                           94  RuntimePaths（全项目依赖注入载体）
├── config.py                           274  config.toml 读写 + 原子写
└── paths.py                             18  路径解析（ZCORE_HOME / AI_MEMORY_DIR / AI_SKILLS_DIR）
```

注意：`zcore/engines/__init__.py` 只有 2 行 docstring（`engines/__init__.py:1-2`），**没有任何引擎注册表**——引擎之间、CLI 与引擎之间全靠显式 import。

### 1.3 核心类与函数签名（关键证据）

| 类 / 函数 | 位置 | 签名要点 |
|---|---|---|
| `RuntimePaths` | `zcore/runtime.py:10-68` | frozen dataclass，21 个 `Path` 字段；`discover()` 类方法从环境变量组装 |
| `FileLock` | `zcore/utils/filelock.py:12-53` | `acquire()` 用 `fcntl.flock(LOCK_EX|LOCK_NB)` 轮询，5s 超时；非 POSIX 降级为空操作 |
| `GhostAgent` | `zcore/engines/ghost_agent.py:14-379` | `generate(prompt, fallback_text=None, *, role, session_id, skill_name) -> dict`；`call()`、`compact_messages()`、`extract_memories()` |
| `MemoryEngine` | `zcore/engines/memory.py:122-601` | `extract_from_conversation()`、`dedup()`、`write()`、`search_all()`、`expire_check()`、`migrate_v1()` |
| `TopicStore` | `zcore/engines/memory.py:67-119` | 读写 `topics/<slug>.md`；`write_entry()` 在 `FileLock("memory-topics.lock")` 下读改写 |
| `SkillRouter` | `zcore/engines/router.py:65-512` | `discover()`、`match()`（三层打分）、`execute()`（subprocess）、`install_skill()` / `uninstall_skill()` / `validate_skill()` |
| `ContextEngine` | `zcore/engines/context.py:43-419` | `analyze(messages, model) -> TokenAnalysis`、`apply_compact()`、`get_compact_prompt()` |
| `SessionManager` | `zcore/engines/session.py:19-352` | `start()`、`end()`（gzip 落盘 + 压缩 + 记忆提取）、`pause()/resume()`、`handoff()`、`cleanup_sessions()` |
| `PermissionEngine` | `zcore/engines/governance.py:105-266` | `check(action, target) -> PermissionDecision`、`load_rules()`（global/project/session 三级） |
| `classify_shell_command` | `zcore/engines/governance.py:269-277` | 正则匹配 DANGEROUS/RISKY 表 → safe/risky/dangerous |
| `ObservabilityEngine` | `zcore/engines/observability.py:52-252` | `log_execution()` / `log_cost()`（JSONL append）、`get_cost_report()`（读 monthly_budget） |
| `AgentSetupEngine` | `zcore/engines/agent_setup.py:42-194` | `detect_agents()`、`setup_agent()`（向 CLAUDE.md/GEMINI.md/AGENTS.md 注入受管代码块） |
| `McpEngine` | `zcore/engines/mcp.py:15-196` | `add_server()` / `sync_to_agent()` / `diff()`；注册表 `~/.zcore/mcp-servers.toml` |
| `WorkflowEngine` | `zcore/engines/workflow.py:15-190` | `discover_workflows()`（TOML）、`validate_workflow()`、`run_workflow()`（逐步骤 `python -m zcore` 子进程） |
| `HarvesterEngine` | `zcore/engines/harvester.py:15-196` | `discover()` / `ingest()` / `status()`；`register_adapter()` 手动注册 |
| `SearchEngine` | `zcore/engines/search.py:13-174` | 纯线性扫描 `sessions/*/meta.json` + `context.json.gz` + `harvested/*/*.json` |
| `HookRunner` | `zcore/hooks/lifecycle.py:31-111` | `execute_chain(names, *, manifest, args, phase, ...)`；pre 阶段 fail 即阻断 |
| `SkillManifest` | `zcore/models/skill.py:120-187` | `from_skill_md(path)` 解析 SKILL.md frontmatter；`from_dict()` 严格类型收窄 |
| `main` | `zcore/cli/main.py:541-559` | `main(argv)` 包一层 try/except（`--json` 时输出 `{ok:false,error}`）；`_main_impl` 为巨型 if/elif 分发 |

---

## 2. 架构模式

### 2.1 十个引擎的实现方式（逐个）

**① GhostAgent（`engines/ghost_agent.py`，379 行）**
- 职责：会话间隙的廉价 LLM 后端，用于压缩、记忆提取、降级兜底。
- 实现：`availability()`（28-76）先判断 `llm_backend.enabled` 与 API key，得到 `mode=fallback/local/remote` 三态；`generate()`（93-176）按 role 模型 → 默认模型 → 兜底文本的顺序逐级尝试，每级带 `retry_max+1` 次重试；HTTP 完全走标准库 `urllib.request.urlopen`（217-220）；`_build_request()`（222-267）按 provider 拼装 Google/Anthropic/OpenAI/Ollama 四种请求体；响应解析 `_extract_text_from_response()`（327-379）。
- 关键设计：与 `ContextEngine` 的循环依赖通过**函数内延迟 import** 规避（193 行）。

**② ContextEngine（`engines/context.py`，419 行）**
- 职责：token 用量分析与超限压缩。
- 实现：`analyze()`（68-95）计算 `hard_limit = window - MAX_OUTPUT_TOKENS - buffer`、早警告阈值、百分比阈值，取最小者触发 `should_compact`；`apply_compact()`（127-179）保留尾部 5 条消息（`_preserve_tail`，200-202），优先用 GhostAgent 生成摘要、失败退到 `_heuristic_summary()`（204-233，按"意图/决策/进度/阻塞/状态/下一步"六段模板）；`_trim_messages_to_budget()`（286-359）对超长 transcript 做"头 4 + 尾 8 + 采样中点 + 二分截断单条消息"的裁剪。
- 特点：全部启发式 + 纯文本模板，不依赖任何 LLM 也能工作。

**③ MemoryEngine（`engines/memory.py`，601 行）**
- 职责：L2 记忆（topic markdown 文件）的写入、去重、搜索、提取、迁移、过期。
- 实现：`TopicStore`（67-119）把每条记忆序列化成一行 markdown + **base64 JSON 注释**（`models/memory.py:63-73` 的 `to_markdown_line()`：`- [type] content (source: ..., confidence: ..., date: ...) <!-- zcore:<base64> -->`，解析见 75-101）——人类可读且机器无损；`extract_from_conversation()`（183-247）先 LLM 提取、失败退到 `_heuristic_extract()`（512-547，按 `[decision]/[fact]/[learning]/[preference]` 标记）；所有候选先进 `pending-confirm.json`（`_admit_entries` 549-565，Phase 0A 注释在 560 行明确"候选-only，需显式确认"）；`dedup()`（249-266）用规范化文本相等 + `SequenceMatcher` 相似度 + 关键词重叠三重复合；`search_all()`（317-349）返回固定 `{l2, l3, meta}` 结构。
- 存储格式：`~/.ai-memory/topics/<topic>.md`，主题由 `auto_topic()`（268-280）按 project → topic → 关键词匹配 slug 化决定。

**④ SessionManager（`engines/session.py`，352 行）**
- 职责：会话生命周期（start/end/pause/resume/handoff/cleanup）。
- 实现：每个会话一个目录 `~/.zcore/sessions/<12位hex>/`，内含 `meta.json`（SessionMeta dataclass，`models/session.py:12-32`）、结束时的 `context.json.gz`（gzip 压缩消息，65-66 行）、`context.md`（压缩摘要）、`memories.json`、`handoff.md`；中央索引 `sessions/index.json`（schema_version "2.0"）在 `_upsert()`（252-258）持锁读写；`end()`（43-94）串联 compact + 记忆提取；GC 是**概率式**的：每次 `start()` 有 5% 概率触发 `_lazy_gc()`（24、39-40、260-288 行），另提供显式 `cleanup_sessions()`（197-227）。

**⑤ SkillRouter（`engines/router.py`，512 行）**
- 职责：技能发现、三层匹配、执行、安装/卸载/校验。
- 实现：`discover()`（70-90）扫描 `~/.ai-skills/*/SKILL.md` 与 `<repo>/.skills/*/SKILL.md`（`_normalized_search_paths` 208-211），解析失败降级为带 warning 的空 manifest；`match()`（92-137）按 Layer1 关键词（`_keyword_score` 417-434）→ Layer2 文件路径（`_path_score` 437-442）→ Layer3 上下文 token/project（`_context_score` 445-453）三级打分；`execute()`（150-206）先跑 pre-hooks（阻断即 blocked）→ `subprocess.run(["python3", script, *args], timeout=30)`（181-184）→ 跑 post-hooks；`install_skill()`（293-335）支持本地目录 / git clone，装完自动 `validate_skill()`（337-385）。

**⑥ PermissionEngine（`engines/governance.py`，277 行）**
- 职责：权限决策 + 审计。
- 实现：规则三级来源（`load_rules()` 111-121：global config → 项目 `.zcore/config.toml` → 会话内规则），决策优先级 `allow < ask < deny`、来源优先级 `global < project < session`（87-88 行）；`check()`（126-155）先精确匹配规则，未匹配时按 `permission_mode`（yolo/auto/ask）兜底；非 TTY 下 `ask` 必须 fail-fast（`resolve_ask_behavior` 91-102，抛 `PermissionDeniedError("decision=ask_required ... mode=non_tty")`）；`audit_report()`（236-266）聚合规则统计、被拒事件、高频技能、危险命令历史。

**⑦ ObservabilityEngine（`engines/observability.py`，252 行）**
- 职责：执行日志、成本追踪、健康报告。
- 实现：`log_execution()`（57-83）与 `log_cost()`（85-107）**追加写 JSONL**（`_append_jsonl` 204-207，注意此函数**没有 FileLock**，见 7.3）；统计靠每次全量重读 JSONL 再过滤时间窗（`_iter_jsonl` 209-227）；成本报告读 `llm_backend.monthly_budget` 算剩余（146-170）。

**⑧ AgentSetupEngine（`engines/agent_setup.py`，194 行）**
- 职责：把 Z-Core 的用法注入 Claude/Gemini/Codex 的配置文件。
- 实现：`detect_agents()`（46-51）写死三个 agent；`setup_agent()`（53-99）对 `~/.claude/CLAUDE.md`、`~/.gemini/GEMINI.md`、`~/.codex/AGENTS.md`（或 cwd 下）做受管代码块注入（`<!-- ZCORE:START -->` / `<!-- ZCORE:END -->`，12-13 行），写前备份 `.bak`；注入内容见 `render_injection_block()`（101-115），即"教 Agent 用 zcore 命令"的提示词。

**⑨ McpEngine（`engines/mcp.py`，196 行）**
- 职责：MCP server 注册表 + 向各 Agent 配置同步。
- 实现：注册表 `~/.zcore/mcp-servers.toml`（`_write_registry` 108-130 手工拼 TOML 字符串）；`sync_to_agent()`（58-61）把注册表整体覆盖写入 `claude_desktop_config.json` / `~/.gemini/settings.json` / `~/.codex/config.json` 的 `mcpServers` 字段（`_agent_mcp_config_path` 132-140 写死三个路径），写前 `.bak` 备份；`diff()`（63-79）对比注册表与各 agent 现状。

**⑩ WorkflowEngine（`engines/workflow.py`，190 行）**
- 职责：声明式多步骤编排。
- 实现：只解析 **TOML**（`_parse_workflow_file` 154-190），扫描 `~/.zcore/workflows/*.toml` 与 `<cwd>/.zcore/workflows/*.toml`（148-152）；`run_workflow()`（80-146）对每个 step 执行 `[sys.executable, "-m", "zcore", *shlex.split(step.command), *step.args]`（96 行）——**workflow 本质是 zcore 子命令的序列**；`on_failure=abort|continue`，abort 时后续步骤标记 skipped（129-142）。

**附加引擎（第 11~14 个，不在用户列举的 10 个内但同层）**：`HarvesterEngine`（跨 Agent 会话收割）、`SearchEngine`（会话全文线性扫描）、`KnowledgeHealthEngine`（外部索引健康只读）、`zcore/engines/knowledge_contract.py`（L2 只读 provider：`TopicMarkdownL2Provider` 44-111、`WhiteboardL2Provider` 114-185）。

### 2.2 RuntimePaths 依赖注入如何工作

- 载体：`zcore/runtime.py:10-68` 的 **frozen dataclass** `RuntimePaths`，一次性从环境变量解析出 21 个路径：`ZCORE_HOME`（或 `KITCLAW_HOME`，默认 `~/.zcore`）、`AI_MEMORY_DIR`（默认 `~/.ai-memory`）、`AI_SKILLS_DIR`（默认 `~/.ai-skills`）、`ZCORE_KNOWLEDGE_DB`、`ZCORE_KNOWLEDGE_HEALTH_MANIFEST`（见 `paths.py:7-14` 与 `runtime.py:35-68`）。
- 注入方式：**构造函数注入 + 默认值**。所有引擎签名都是 `def __init__(self, paths: RuntimePaths | None = None): self.paths = paths or RuntimePaths.discover()`（如 `memory.py:123-125`、`ghost_agent.py:24-26`、`context.py:53-55`、`session.py:20-21`、`router.py:66-67`）。`discover()` 每次进程启动独立调用，因此测试可以用 `TestHome`（`tests/helpers.py:31-70`）改环境变量实现完全隔离。
- 二次读取：每个引擎在 `__init__` 里各自 `load_config(self.paths)`（如 `memory.py:126`、`ghost_agent.py:26`、`context.py:55`、`observability.py:55`），**配置不共享、每次进程内重复解析 TOML**。
- 跨引擎协作：靠**直接 import + 延迟 import** 而非服务定位——`session.py:77` 引入 `MemoryEngine`、`ghost_agent.py:193` 引入 `ContextEngine`、`memory.py:196` 引入 `GhostAgent`、`router.py:14` 引入 `HookRunner`。没有接口抽象（除 `adapters/base.py` 的 `SourceAdapter` ABC）、没有注册表、没有事件总线。
- 结论：这是"依赖注入"的最小可行形态——**路径注入**；能力注入（引擎作为服务、可替换实现）不存在。

### 2.3 CLI 命令注册与分发

- 注册：`_build_parser()`（`cli/main.py:42-374`）用标准库 **argparse** 的 `add_subparsers(dest="command", required=True)` 逐条 `add_parser` 手写，约 370 行；每个子命令手动加 `--json` 开关（约定"所有命令可输出机器可读 JSON"）。
- 分发：`_main_impl()`（551-559）先 `parse_known_args`，然后是一个从 561 行延伸到 1450 行的**巨型 if/elif 链**（`if args.command == "init": ... if args.command == "memory": if args.memory_command == "extract": ...`）。每个分支内联 new 引擎 → 调方法 → 按 `args.json` 打印。
- 命令统计（叶子命令 56 个）：

| 顶层命令 | 子命令 | 数量 |
|---|---|---|
| init / status / doctor / compact / migrate / run / governance-check / setup | —（叶子） | 8 |
| context | analyze | 1 |
| memory | extract, list, search, write, topics, stats, pending, expire-check | 8 |
| session | start, end, list, show, search, cleanup, handoff, pause, resume | 9 |
| workflow | list, validate, run | 3 |
| mcp | list, add, remove, sync, diff | 5 |
| skill | list, match, info, install, uninstall, validate | 6 |
| governance | rules, check, allow, deny, log, audit | 6 |
| observe | stats, costs, health | 3 |
| ghost | roles | 1 |
| harvest | discover, ingest, status | 3 |
| config | show, set, reset | 3 |
| **合计** | | **56** |

- 输出约定：`--json` 时 `print(json.dumps(payload, ensure_ascii=False))`；错误路径经 `_emit_error()`（534-538）与 `main()` 顶层的 try/except（541-548，检测 argv 里含 `--json` 即输出结构化错误）。
- 特殊处理：`_normalize_argv()`（506-518）为 `mcp add --args` 做参数修正；`run` 的未知参数并入 `skill_args`（555-556）；`_parse_skill_args()`（460-480）把 `--key value` 转成 dict 再经 `_args_to_cli()`（router.py:497-511）转回 `--key value` 传给技能子进程。

---

## 3. 状态与持久化

### 3.1 所有文件格式清单

| 格式 | 路径 | 内容 | 写入方式 |
|---|---|---|---|
| TOML | `~/.zcore/config.toml` | 9 个配置区块（core/llm_backend/privacy/memory/...） | 全量渲染（`config.py:15-87`）或正则改写（`set_config_value` 156-176） |
| TOML | `~/.zcore/mcp-servers.toml` | MCP server 注册表 | 手工拼字符串（`mcp.py:108-130`） |
| YAML | `~/.zcore/shared-rules.yaml` | 共享规则（约束/用户画像/路由提示） | 全量渲染（`config.py:90-106`） |
| JSON | `~/.zcore/sessions/index.json` | 会话中央索引（schema "2.0"） | `atomic_write_json` + `FileLock`（`session.py:252-258`） |
| JSON+gzip | `~/.zcore/sessions/<id>/context.json.gz` | 会话消息快照 | `gzip.open` 直写（`session.py:65-66`，无锁） |
| JSON | `.../meta.json` / `memories.json` | 会话元数据 / 记忆提取结果 | `atomic_write_json` |
| JSON | `~/.zcore/harvested/index.json` + `harvested/<source>/*.json` | 收割索引 + 脱敏后的会话 | 直写（`harvester.py:146-155`，无锁） |
| JSON | `~/.ai-memory/whiteboard.json`（v1 遗留）、`staging/pending-confirm.json`、`extraction-log.jsonl` | 白板 / 待确认记忆 / 提取日志 | `atomic_write_json`/追加，均加锁 |
| Markdown | `~/.ai-memory/topics/<topic>.md` | L2 记忆（行式 + base64 JSON 注释） | 持锁读改写（`memory.py:85-102`） |
| JSONL | `~/.zcore/logs/executions.jsonl`、`costs.jsonl` | 执行/成本日志 | **追加写、无锁**（`observability.py:204-207`） |
| 外部 JSON | `~/.claude/claude_desktop_config.json` 等 | MCP 同步目标 | 备份后整体重写（`mcp.py:166-173`） |
| .lock | `~/.zcore/locks/*.lock` | flock 锁文件 | 见 3.2 |
| 可选 | `~/.lancedb/knowledge` | L3 向量库（lancedb，仅 rag extra） | `rag/_knowledge_index.py:101+` |

### 3.2 锁机制（FileLock）

- 实现：`utils/filelock.py:12-53`。打开锁文件 `a+` 后 `fcntl.flock(fd, LOCK_EX|LOCK_NB)`，`BlockingIOError` 时以 0.1s 间隔轮询直到 5s 超时抛 `TimeoutError`（28-38 行）。
- 使用点：`config.py:268`（config.toml 原子写）、`memory.py:90/99/423/569/574`（topic 写、迁移、pending、日志）、`session.py:225/253`（索引）、`governance.py:209`（规则写）、`mcp.py:192`（注册表与 agent 配置写）。
- **关键缺陷**：`filelock.py:25-26`——`fcntl` 导入失败（Windows）时 `acquire()` **直接 return，锁完全失效**；而 `cli/main.py:394-397` 的 status 报告 `"file_locking": {"available": True}` 是**无条件写死的**，与实际能力无关。
- 覆盖缺口：`observability.py:204-207` 的 JSONL 追加、`harvester.py:146-155` 的收割索引与会话写入、`session.py:65-66` 的 gzip 快照**都不持锁**。

### 3.3 跨进程一致性处理

- 原子写：`utils/fs.py:15-28` `atomic_write_text` = `tempfile.mkstemp` + `flush` + `fsync` + `os.replace`（同目录，原子重命名），可选 chmod；`atomic_write_json` 是其 JSON 包装。config 层另有 `_atomic_write`（`config.py:265-274`）额外套 FileLock 并 chmod 0o600。
- 读改写一致性：写多行/多条目结构（topic 文件、sessions 索引、pending 队列）时在锁内"读全量 → 内存修改 → 原子写全量"，保证锁内串行化（如 `session.py:252-258`、`memory.py:85-102`）。
- 索引 vs 实体：`sessions/index.json` 与 `sessions/<id>/` 目录**双写**（`session.py:37-38, 92-93`），靠锁保护索引；`cleanup_sessions()`（224-226）在锁内重写索引。但进程在"写 meta.json 成功、写索引前崩溃"的窗口会造成索引与目录不一致（无恢复/对账机制）。
- 无守护进程下的跨进程约束：所有共享状态只通过文件系统 + 咨询锁串行化；不存在跨进程缓存或共享内存；`SkillRouter` 的 `self._cache`（`router.py:68`）只是进程内的 manifest 缓存，每次 CLI 调用进程即消亡。

### 3.4 无常驻进程带来的权衡（设计取舍）

| 能力 | 实现方式 | 代价 |
|---|---|---|
| 去重 | 每次写入全量扫描 `store.all_entries()`（`memory.py:283`）+ 三重复合比对（249-266） | O(全部记忆) 时间；记忆越多越慢 |
| 会话恢复 | `session start --resume-latest` → `find_latest()`（`session.py:149-151`）+ 读 `context.md`（`load_context` 153-157）；`resume-from` 记录 `parent_session`（`session.py:32`） | 恢复的是**压缩摘要**而非原对话；无实时状态 |
| 记忆提取 | 结束会话时一次性 `extract_from_conversation()`（`session.py:76-87`）；"会话间隙自主思考"实际依赖外部定时任务/Agent 在会话结束后调用 CLI | Ghost Agent 并非后台进程，无法真正"间隙"运行 |
| GC | 5% 概率惰性 GC（`session.py:24, 39-40`）+ 显式 `cleanup`/`expire-check` 命令 | 无人调用则状态无限累积；概率式清理不可预期 |
| 成本预算 | 只读日志聚合（`observability.py:146-170`），`log_cost` 后置记账 | **非实时硬限制**：月度预算超了也只是报告剩余为 0，不拦截请求 |
| 并发 | 咨询锁 + 原子写 | 见 3.2 的覆盖缺口；Windows 上锁失效 |
| 进程粒度 | 每次 CLI 调用 = 一次全新 Python 进程，重新解析 config、重新 discover | 无热状态、无连接复用；启动开销虽小但重复 |

---

## 4. 扩展机制

### 4.1 hooks 框架

- 两层：**内置钩子**（`hooks/builtin.py:83-90` 的 `BUILTIN_HOOKS` dict：`validate-input`、`check-permissions`、`log-execution`，含连字符/下划线双别名）+ **外部脚本钩子**（`~/.zcore/hooks/pre-execute.d/` 与 `post-execute.d/` 下的 `.py` / `.sh`，`hooks/lifecycle.py:83-92`）。
- 执行链：`HookRunner.execute_chain()`（`lifecycle.py:44-81`）先按名字取内置钩子，再追加目录脚本；pre 阶段任一钩子返回 `fail` 即阻断（79-80），`SkillRouter.execute()` 据此返回 `status="blocked"`（`router.py:160-175`）。
- 外部钩子协议：**仅环境变量**（`ZCORE_SKILL_NAME` / `ZCORE_SESSION_ID` / `ZCORE_PROJECT`，`lifecycle.py:96-103`），无 stdin/stdout 结构化协议，退出码 0/非 0 决定 pass/fail——比 Cordis 的 `ctx.on(event)` 原语能力弱很多。
- 钩子声明来源：`SKILL.md` frontmatter 的 `lifecycle.pre_execute/post_execute` 列表（`models/skill.py:59-69`），`post_execute` 为空时自动补 `log-execution`（`models/skill.py:185-186`）。

### 4.2 workflows 定义格式

- 格式：TOML，`[workflow]`（name/description）+ `[[steps]]`（name/skill/command/args/on_failure），解析见 `workflow.py:154-190`；示例位置 `~/.zcore/workflows/` 或 `<cwd>/.zcore/workflows/`。
- 执行：每个 step 启动一个 `python -m zcore ...` 子进程（`workflow.py:96`），无状态传递（只有 cwd 共享）、无步骤间数据管道（对比下面 YAML 链）。
- **双轨不一致**：仓库内置技能 `skills/core/agent-orchestrator/chains/*.yaml`（如 `translate-tweet-publish.yaml`）是**另一种编排格式**（`schema_version: "1.0"`，`steps: [{skill, input, output}]`，变量插值 `$URL`，由该技能自带的 `run-chain.py` 执行），与 `zcore workflow` 的 TOML 引擎**完全不互通**——两套编排系统并存且互不知晓。

### 4.3 skills 的 SKILL.md 格式与三层路由

- 发现：目录式约定 `*/SKILL.md`（`router.py:75`），manifest 由 `SkillManifest.from_skill_md()`（`models/skill.py:157-187`）解析 frontmatter（手写 YAML 子集解析器 `utils/frontmatter.py:6-237`）。
- frontmatter 字段（`models/skill.py:10-133` 的 dataclass）：`name/version/description`、`activation.{triggers,paths,context.{min/max_tokens,project_types},effort}`、`dependencies.{required,optional}`、`lifecycle.{pre_execute,post_execute}`、`permissions.{reads,writes,shell,network}`、`io.{input,output}`。
- 脚本发现：只扫 `scripts/*.py`（`models/skill.py:199-203`）；执行时 `_resolve_script()`（`router.py:475-494`）按 `action` 参数 → 单脚本 → `run/main/<name>` 优先级选脚本。
- 三层路由（`router.py:417-453`）：Layer1 关键词（触发词命中 130 分 / 描述命中 115 分 / 重叠率 100+20×）、Layer2 文件路径 fnmatch（80 分）、Layer3 上下文（token 区间 60/55 分、project 类型 50 分）；`match()` 排序键 `(-score, match_layer, name)`（137 行）。另有 `activate_conditional()`（139-148）按路径模式静态激活。
- `dependencies` 字段被解析（`models/skill.py:44-55`）但**执行时从不校验**（`router.py:150-206` 全程未引用 `manifest.dependencies`）——声明了却未实施。

### 4.4 依赖注入与插件化程度（总结）

| 维度 | 现状 | 证据 |
|---|---|---|
| 引擎注册 | **无注册表**，直接 import 实例化 | `engines/__init__.py` 空；`cli/main.py:18-39` 显式 import 全部引擎 |
| 引擎接口 | 无统一 ABC（仅 `SourceAdapter` 有） | `adapters/base.py:8-23` |
| 配置注入 | 构造注入 `RuntimePaths`，每引擎各自读 config | `runtime.py` + 各引擎 `__init__` |
| 服务替换 | 不可替换（如换 Memory 实现需改 import） | — |
| 数据插件 | skills（目录式）、hooks（脚本式）、adapters（注册式）是**仅有的三类可插拔面** | `router.py` / `lifecycle.py` / `harvester.py:23-24` |
| 热更新 | 无（无进程可热更新；技能安装只是拷贝目录） | `install_skill` 即 `shutil.copytree`（`router.py:303-325`） |

---

## 5. Ghost Agent 细节

### 5.1 LLM 调用实现

- **完全标准库**：`urllib.request.urlopen`（`ghost_agent.py:219`）+ `urllib.parse.quote`（231）、`urllib.error`（140）。无 `requests`、无 SDK。
- 请求构建（`_build_request` 222-267）：Google 走 `generativelanguage.googleapis.com/v1beta/models/<model>:generateContent?key=...`（229-237）；Anthropic 走 `/v1/messages` + `x-api-key` + `anthropic-version`（238-246）；OpenAI 走 `/v1/chat/completions` + Bearer（247-254）；Ollama 走 `/api/generate`（255-262）。超时 `timeout` 从 config 读（111 行），重试 `retry_max+1` 次（123 行）。
- 响应解析（`_extract_text_from_response` 327-379）：按 provider 分支提取 `candidates[].content.parts[].text` / `content[].text` / `choices[].message.content` / `response`。

### 5.2 三级降级链（实际是"四级阶梯"）

1. **能力门**：`availability()`（28-76）——未启用或缺 API key 直接 `mode=fallback`，`generate()` 返回 `_fallback_text(prompt)`（104-109；fallback 实现 284-288 即"截断的原文摘要"）。
2. **角色模型优先**：`_role_model(role)`（178-185）从 config `llm_backend.roles.<role>` 读角色专属模型；`generate()` 先试 role_model（154-157）。
3. **默认模型 + 重试**：`try_model(default_model)`（159-161），内部对 `OSError/ValueError/HTTPError/URLError` 重试 `retry_max+1` 次（123-141），空响应视为 `empty_response`（139）。
4. **兜底**：`fallback_on_failure=false` 时返回 `mode=error`（163-169）；否则返回 fallback 文本，`reason="request_failed:<ExcName>"`（171-176）。

另有"stub"模式：`extract_memories()`（203-215）在 LLM 不可用时仅按 `[decision]/[action]/[learning]/[fact]/[preference]` 标记做启发式摘取。

### 5.3 脱敏（发送前）

- 出口钩子：`_sanitize_text()`（276-282）在 `privacy.redact_before_send` 开启时对 prompt 调 `redact_text()`；`generate()` 在 120 行 `_truncate_prompt_to_budget(self._sanitize_text(prompt))` 处执行（**脱敏先于预算裁剪**）。
- 规则库：`utils/privacy.py:10-19` 默认 9 组正则（api key/token/secret、`sk-`、`AIza`、IP、邮箱、手机号、AWS AKIA、Bearer、路径替换 `/home/<user>/` → `/home/[USER]/` 等 22-33 行）；用户可用 config `privacy.redact_patterns` 覆盖（`config.py:34-38` 默认值）。
- 全链路：收割会话入库前也脱敏（`harvester.py:157-173` `_redact_session`）；config 展示用 `mask_sensitive_data`（`config.py:142-153`）。

### 5.4 预算控制的具体代码位置

| 机制 | 位置 | 说明 |
|---|---|---|
| 每 token 单价表 | `ghost_agent.py:18-22` `PRICING_PER_1M_TOKENS`（gemini-2.5-flash / claude-3-5-haiku / gpt-4o-mini 三对 (input, output) 价格） | 未知组合按 0 计 |
| 单次成本估算 | `_estimate_cost_usd()`（187-190） | 调后记录 |
| 记账 | `generate()` 成功路径 `observability.log_cost(...)`（129-137）；失败也记 0 成本（143-151） | 落 `~/.zcore/logs/costs.jsonl` |
| 月度预算 | config `llm_backend.monthly_budget`（默认 5.0，`config.py:27`）；`get_cost_report()` 读并算 `budget_remaining`（`observability.py:161-162`） | **只报告、不拦截** |
| 提示词预算 | `max_prompt_tokens()`（84-91）= 上下文窗口 − 4096 输出 − 2048 安全边距；`_truncate_prompt_to_budget()`（290-316）双阶段字符裁剪 | 防超窗 |
| token 估算 | `utils/tokens.py:89-93`：优先 tiktoken（可选依赖，54-71），否则中英混合字符估算（74-86）；上下文窗口表 27-35（硬编码） | 降级路径 |

---

## 6. 测试与质量

### 6.1 测试覆盖

- 规模：29 个测试文件、3,841 行、**143 个 `def test_` 函数**；本报告写作时实跑 `pytest tests/ -q` → **142 passed, 1 skipped（16.53s）**。
- 隔离设施：`tests/helpers.py` 的 `TestHome` 上下文管理器（31-70）把 `HOME/ZCORE_HOME/AI_MEMORY_DIR/AI_SKILLS_DIR/ZCORE_KNOWLEDGE_DB/...` 全部重定向到临时目录；`run_zcore()`（13-28）以子进程方式跑 `python -m zcore`，因此 CLI 集成测试是**真实子进程黑盒**。
- 风格：CLI 集成（`test_zcore_cli.py` 388 行）+ 单引擎单元（`test_zcore_memory.py` 152、`test_skill_router.py` 270、`test_context.py` 62）+ monkeypatch 网络（`test_zcore_ghost_agent.py:6-60` 用假 `urlopen` 捕获请求体、验证脱敏后发送）。RAG 测试（`test_rag_integration.py` 81 行）因可选依赖被跳过（对应 1 skipped）。
- 主要覆盖点：CLI 全命令、记忆提取/去重/过期/迁移、会话生命周期与暂停恢复、三层路由打分、权限规则与审计、MCP 同步、workflow 校验执行、harvester/adapters、脱敏、知识健康契约（`test_knowledge_health.py` 354 行）、知识治理审计（`test_knowledge_watcher_audit.py` 151）。

### 6.2 pyproject.toml 配置

- `pyproject.toml:1-50`：setuptools 构建；`requires-python >=3.11`；`dependencies = []`（零依赖卖点）；`[project.scripts] zcore = "zcore.cli.main:main"`（27 行）；可选 extras：`dev`（build/pytest/twine）、`test`（pytest）、`rag`（lancedb/sentence-transformers/python-frontmatter/pandas，32-37）；打包包含 `zcore.prompts/*.md` 与 `skills.core/**/*`（45-47），排除 `.claude` 与 pyc（49-50）。
- **无** ruff/flake8/mypy/pytest 配置节（`[tool.pytest.ini_options]` 等均不存在）——质量门只有"测试通过"。

### 6.3 版本与发行状态

| 项 | 状态 | 证据 |
|---|---|---|
| 当前版本 | 0.2.0 | `pyproject.toml:7`、`zcore/__version__.py`（`__version__ = "0.2.0"`） |
| dist/ | `zcore-0.2.0-py3-none-any.whl`（248 KB）+ `zcore-0.2.0.tar.gz`（228 KB），2025-08-07 构建 | `ls dist/` |
| zcore.egg-info/ | 元数据齐全（PKG-INFO 0.2.0、entry_points 含 `zcore=zcore.cli.main:main`） | `zcore.egg-info/PKG-INFO` |
| build/lib | 已包含 `skills/core/`（17 个技能）与 `zcore/` 全量拷贝 | `build/lib/` 树 |
| v2/ 目录 | **V2 设计文档与 PM 归档**：`design/`（architecture.md、memory-engine.md、ghost-agent-deep-review.md 等 13 份）、`pm/`（Changelog、Decision-Log、6 轮 Phase Review）、`rfcs/`（001~005）、`references/`、`prototypes/`（空） | `ls v2/` |
| v3/ 目录 | **V3 PM**：`BREAKING-CHANGES.md`（V3.0 纯增量、无破坏；V3.1 预告 Planner/Evaluator/Dispatcher 变更）、`pm/`（Current-State、Sprint-Backlog-V3.1、Task0~7 规格、3 份 Codex Review） | `v3/BREAKING-CHANGES.md`、`v3/pm/` |
| 分支 | `main` + `v3/develop`（当前） | `git branch -a` |
| Git 叙事 | 最近提交 `fb99839`（v3 audit fixes）；V3.0 四里程碑（Harvester、GhostAgent 角色、隐私管线、会话搜索）已关闭，V3.1 目标为 OpenClaw/Codex/Gemini Adapter + sqlite-fts5 搜索索引（<100ms） | `git log --oneline \| head`、`v3/pm/Current-State.md` |

---

## 7. 已知局限（从代码中找到的证据）

### 7.1 TODO / FIXME 与未实现

代码库**几乎没有 TODO/FIXME 注释**（grep `TODO|FIXME|XXX|HACK` 仅 6 处弱相关命中，均为"stub"/"Phase 0"等措辞而非任务标记）。真正的"未实现"体现在行为而非注释：

| 未实现/半实现点 | 证据 |
|---|---|
| `dependencies` 声明不校验 | `models/skill.py:44-55` 解析，`router.py:150-206` 从不使用 |
| Ghost 角色模型表未内置 | `ghost_agent.py:178-185` 只从 config 读；config 默认值里 `roles` 区块不存在（`config.py:21-29`） |
| 月度预算只记账不拦截 | `observability.py:161-162` 算 `budget_remaining`，`ghost_agent.py` 无任何预算判断 |
| `extract_memories` 是启发式 stub | `ghost_agent.py:203-215` 注释自述 "stub" |
| skill 远程安装依赖 git | `router.py:310-312` 无 git 即报错 |
| `whiteboard.json` 是 v1 遗留 | `migrate_v1` 一次性迁移（`memory.py:379-429`），迁移后删除原文件（428 行） |
| workflow 无步骤间数据流 | `workflow.py:96` 只传命令行 |
| SearchEngine 是线性扫描 | `search.py:73-114` 逐文件读；V3.1 规划 FTS 索引替代（`v3/pm/Current-State.md`） |
| YAML 链与 TOML workflow 双轨 | `skills/core/agent-orchestrator/chains/*.yaml` vs `workflow.py` |

### 7.2 单点脆弱环节

1. **无守护进程的天然限制**：所有"后台"能力（Ghost 思考、记忆提取、GC、预算拦截）都依赖外部按时调用 CLI；没有任何内置调度。
2. **FileLock 在非 POSIX 失效且 status 谎报**：`filelock.py:25-26` 空操作 vs `cli/main.py:394-397` 恒为 True。
3. **无锁写入缺口**：`observability.py:204-207` JSONL 追加（多进程并发 append 可能交错产生半行）、`harvester.py:146-155` 索引/会话直写（`ingest` 无锁，两进程同时收割可能覆盖索引）、`session.py:65-66` gzip 快照。
4. **索引与目录可能不一致**：`session.py:37-38` 先写 meta.json 再 `_upsert` 索引，中间崩溃即失配；`SessionManager.list()` 从索引读，而 `_lazy_gc`/`cleanup` 按目录扫——两套事实来源（`session.py:96-127` vs 260-288）。
5. **内存/时间复杂度**：每次记忆写入全量扫描（`memory.py:283`）；每次统计重读全部 JSONL（`observability.py:209-227`）；token 估算的字符混合法在中文场景偏粗糙（`tokens.py:74-86`）。
6. **配置改写用正则**：`config.py:156-176, 248-262` 用正则定位 TOML 节与键，遇到手写复杂值（如内联数组跨行）可能错位；无 schema 校验（`load_config` 只是 `tomllib.load`，132-136）。
7. **并发写同一 topic 文件**：`memory.py:85-102` 锁内"读全部行 + append + 原子写"，若两进程各自持锁串行执行没问题，但 read-modify-write 期间另一进程用**无锁**的 `harvester` 等路径不会冲突（不同文件），主要风险仍是锁覆盖不全的文件。
8. **安全边界是软性的**：`governance.py:59-84` 危险命令黑名单靠正则，`classify_shell_command` 只对 `permission_mode=auto` 时 shell 动作生效（145-149），且 hooks 层再查一次（`builtin.py:60-65`）属防御纵深——但这是"规则引擎"而非强制沙箱；非 TTY 的 `ask` 直接拒绝（91-102）保证了安全但牺牲了自动化。

### 7.3 其它质量问题

- 引擎间耦合靠延迟 import 破循环（`ghost_agent.py:193`、`session.py:77`、`memory.py:196`），模块图不是纯 DAG，`zcore status` 会实例化 4 个引擎（`cli/main.py:377-407`）。
- 错误处理风格不统一：有的命令 catch 特定异常并 `return 1`（如 `session end` 917-918），有的让异常冒泡到 `main()` 顶层（544-548），有的直接 `print` 后 return（如 `mcp add` 1096-1098）。
- `_status_payload` 里 `file_locking.available`、`compat.legacy_memory_manager_present` 等是硬编码推断，非实测。

---

## 8. 与 Cordis / DSH 插件式架构的对照点

> 目标：为"Z-Core 能否以 DeepSeek Harness（Cordis 组合式插件框架）作为载体"提供事实依据。以下每一条都是**当前代码中可指认的硬编码/固定结构**，即若要做成可组合、可插拔、可热更新必须重构的位置。

### 8.1 硬编码点清单（重构靶点）

| # | 硬编码点 | 代码位置 | 若要插件化需要 |
|---|---|---|---|
| H1 | **引擎列表**：CLI 顶部一次性 import 全部 10+ 引擎，无注册表、无服务接口 | `cli/main.py:18-39`；`engines/__init__.py` 为空 | 引入引擎接口（如 `Engine` ABC）+ 按名字注册 + 惰性实例化 |
| H2 | **命令命名空间**：argparse 子命令与分发全部写死在一个 1450 行文件 | `cli/main.py:42-374`（注册）、`551-1450`（if/elif 分发） | 命令注册表：`@command(name, subcommands)` 装饰器 + 按命名空间分发 |
| H3 | **`--json` 输出约定**：每个分支手动 `if args.json:` 双写打印逻辑 | 遍布 `cli/main.py`（如 568-575、639-646） | 统一的响应/渲染管线（类似 Cordis 的 service 方法返回 + 序列化层） |
| H4 | **三层记忆模型写死**：类型枚举、存储格式、检索结构固定 | `models/memory.py:12-13`（`MEMORY_TYPES` Literal）；`memory.py:317-349`（`search_all` 固定 `{l2,l3,meta}`）；`TopicStore` 固定 markdown 行格式（`memory.py:67-119`） | 记忆后端接口（`MemoryProvider`），topic/whiteboard/向量库作为可插拔实现 |
| H5 | **Agent 名单写死（claude/gemini/codex）**：setup、MCP 同步、CLI choices 全部三选一 | `agent_setup.py:58`；`mcp.py:67, 132-140`；`cli/main.py:233, 353` | Agent 描述符注册表（配置文件/目录发现），而非代码内 tuple |
| H6 | **Harvester 适配器自动注册列表写死** | `harvester.py:112-122`（`("zcore.adapters.claude_adapter","ClaudeAdapter"), ...` 二元组硬编码） | entry-points/目录发现式注册（Cordis 的插件行正对应于此） |
| H7 | **LLM provider/模型/价格表硬编码** | `ghost_agent.py:18-22`（价格）、`222-267`（四 provider 分支）；`tokens.py:27-35`（上下文窗口表） | provider 接口 + 配置驱动（对应 Cordis 的 model route 服务） |
| H8 | **知识库 provider 枚举锁定为 `external_readonly`** | `knowledge.py:22-27`（`_PROVIDER_RE` 正则约束）、`knowledge_contract.py:119-120`（`search_provider != "external_readonly"` 即拒绝） | provider 注册表（当前只有一个实现且被契约锁死） |
| H9 | **内置钩子写死 + 外部钩子只有环境变量协议** | `hooks/builtin.py:83-90`；`hooks/lifecycle.py:94-109` | 钩子即事件处理器：`on('pre_execute')` 语义化注册（Cordis `ctx.on`），脚本钩子升级为结构化协议 |
| H10 | **配置 schema 写死**：默认 config 是代码内字符串模板，set 用正则改写 | `config.py:15-87`、`156-176` | 配置 schema 声明化 + 校验器注册 |
| H11 | **Workflow 双轨且无数据流**：TOML 引擎只跑 `zcore` 子命令；YAML 链在技能内部自成体系 | `workflow.py:96, 154-190` vs `skills/core/agent-orchestrator/chains/*.yaml` | 统一编排 DSL + 步骤间 IO 契约（对比 Cordis 的 workflow 工具/chain 校验） |
| H12 | **无生命周期/热更新**：无进程可 reload；技能安装 = 拷贝目录 | `router.py:293-335`（`shutil.copytree` / `git clone`） | 需要常驻宿主（如 DSH）提供插件生命周期（define/run/update/rollback） |
| H13 | **技能执行协议固定**：`python3 script --k v` 子进程 + 30s 超时 | `router.py:181-184` | 可注入执行器（本地子进程 / MCP / 宿主内调用） |
| H14 | **L2 报告 provider_id 枚举锁定** | `models/knowledge_contract.py:294`（`provider_id not in {"topic_markdown","legacy_whiteboard"}` 即抛错） | provider 白名单改为注册表 |

### 8.2 已经"像插件"的部分（可迁移资产）

| 资产 | 说明 | 与 Cordis 的对应 |
|---|---|---|
| SKILL.md 目录式技能 | 数据驱动的 manifest + 发现 + 安装/卸载/校验 | 近似 Cordis 插件（但缺版本管理/热更新/审批） |
| hooks 链 | 名字→可调用对象 + 外部脚本 | 近似事件监听（`ctx.on`），协议需升级 |
| SourceAdapter ABC | 唯一的抽象接口 + 注册方法 | 近似 service 注册（`ctx.provide`） |
| RuntimePaths 注入 | 路径级 DI 已成习惯 | 近似 context/service 注入的雏形 |
| 知识健康契约 | 外部 owner 发布 manifest、消费方只读校验（`knowledge.py:38-178`） | 与 Cordis 的"Host 提供 Inspect Provider、插件消费"思想最接近 |

### 8.3 若以 DSH（Cordis）为载体，Z-Core 的角色推演

- Z-Core 现在的形态是**进程即 CLI、文件即状态、无宿主**；Cordis 的形态是**宿主进程 + 插件行 + 服务注册表 + 生命周期 + 热更新**。两者互补而非互斥：Z-Core 的引擎（H1-H14 中列出的类）可以原样搬进 Cordis 插件行（每个引擎一个 plugin，`apply(ctx)` 里注册服务、监听事件），`RuntimePaths.discover()` 变成宿主注入的 service；`zcore <cmd>` 的 56 个命令可以映射为宿主内 JSON 方法或保留为 CLI 插件；skills/hooks/adapters 三个已数据化的扩展面可以直接复用其格式（SKILL.md、hooks 目录、adapter 类）作为 Cordis 之上的领域层。
- 需要重构的部分正好是第 8.1 节 14 项：把"import 即注册"改成"注册表即真相"，把"if/elif 分发"改成"命令表"，把"写死的 Agent/provider/记忆模型枚举"改成注册表 + 配置。
- 关键取舍提示：Z-Core 的**零依赖、无常驻进程**与 Cordis 的**常驻宿主**是根本性张力——若以 DSH 为载体，等于放弃"纯 CLI 可独立部署"的属性，换取热更新、服务注入与多 Agent 共享状态；反之，Z-Core 的"文件即状态 + 原子写 + 咨询锁"设计在宿主内仍可原样使用（DSH 的持久化层可复用同一套路径约定）。

---

## 9. 总结：Z-Core 当前架构与 Cordis 哲学的异同

**相同之处**：两者都信奉"能力是注册出来的，而不是写死的"这一方向——Z-Core 已经在**数据面**做到了：技能是目录式 SKILL.md 清单、hooks 是名字到函数的表、收割适配器有 ABC 与注册方法、知识健康走"外部 owner 发布 manifest、消费方只读校验"的契约（`knowledge.py:38-178`），这些与 Cordis 的"插件行向注册表发布服务、宿主按契约消费"在精神上同源；且 Z-Core 的 `RuntimePaths` 构造注入已经具备"上下文注入"的雏形，文件即状态 + 原子写 + 咨询锁的持久化哲学与 DSH 的"工作区即持久记忆"也高度一致。

**根本差异**：Z-Core 的**代码面**是封闭的单体——引擎列表、56 个命令、claude/gemini/codex 名单、三层记忆模型、LLM provider 与价格表全部硬编码（第 8.1 节 H1-H14），引擎间靠直接 import 和延迟 import 破循环而非服务查找，没有进程内生命周期（无启动/停止/热更新概念），每次调用都是全新进程；而 Cordis 的哲学是**宿主进程承载一切**：插件行声明式组合、服务按名注入、事件驱动协作、版本化包与热更新、审批与回滚。一句话：**Z-Core 把"可插拔"做在了数据与文件格式层，Cordis 把"可插拔"做在了运行时与服务层**——Z-Core 若要迁入 DSH，不需要重写业务逻辑（引擎类、文件格式、SKILL.md、hooks 全部可复用），需要重构的是第 8.1 节那 14 处"import 即注册 / if/elif 即分发 / 枚举即事实"的接缝，并接受"从零依赖纯 CLI 变为宿主内插件"这一架构定位的转变。
