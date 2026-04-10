# Phase 4: Observability + Agent Setup + Config CLI + Governance Extensions

## 目标

让 Z-Core 从"引擎完备"走向"可观测、可集成"。Phase 0-3 已经实现了全部核心引擎（Context/Memory/Session/Router/Governance/Hooks），现在需要让 Agent 自动使用 zcore，并具备运行时可观测能力。

## 上下文

- 当前 28/28 测试通过（Phase 0-3 全覆盖），commit `b28c422`，分支 `feat/v2`
- 已有 `executions.jsonl` 基础写入（`builtin.py` 的 `log_execution` hook）
- 已有 `config.toml` 加载/解析（`config.py` 的 `load_config` + `tomllib`）
- 已有 `HookRunner` 框架（`hooks/lifecycle.py`），当前只加载 `BUILTIN_HOOKS` 字典
- 已有 Agent 配置文件路径约定：Claude → `~/.claude/CLAUDE.md`，Gemini → `~/.gemini/GEMINI.md`，Codex → `~/.codex/AGENTS.md` 或 `~/AGENTS.md`
- 保持零外部依赖原则

## 执行方法论

本任务使用 `delegated-sprint` skill 的标准流程，当前处于 **Step 2: Dispatch（执行 Agent 编码）**。

> 完整流程定义见 `~/.ai-skills/delegated-sprint/SKILL.md`  
> Step 1 (Plan) 已由 Gemini 完成；Step 3 (Review) 和 Step 4 (Commit) 将在本任务完成后由 Gemini 执行。

### 推荐流程：delegated-sprint Step 2

```
Step 1: Codex 编码 + 自审
  ├── 按 M1→M4 顺序实现
  ├── 每个 Milestone 完成后运行对应测试
  ├── 全部完成后执行 code-review 自审（🔒 必须读取 code-review SKILL.md）
  ├── 修复自审发现的 Blocking 问题
  └── 更新 PM 文件（Current-State, Sprint-Backlog, Decision-Log, sprint-status）

Step 2: Gemini 独立审查
  ├── 执行 code-review skill 的 Standard 模式 5 层审查
  ├── 与设计文档对比偏差
  ├── 修复审查发现的问题
  └── 产出审查报告到 v2/pm/reviews/Phase4-Review.md

Step 3: 提交 + 收口
  ├── git commit（含审查修复）
  └── PM 文档全量更新
```

### Codex 必须遵守的规则

1. **🔒 code-review 自审不可跳过**：编码完成后，必须先 `view_file` 读取 `~/.ai-skills/code-review/SKILL.md`，然后按其定义的流程执行 self-review。这是从 Phase 1 起确立的交付纪律。
2. **测试先行**：每个 Milestone 完成后先验证该 Milestone 的测试通过，再进入下一个 Milestone。
3. **回归保护**：最终交付前，历史 28 个测试必须全部通过。
4. **PM 文件同步**：编码完成后更新 PM 文件，不要等审查后再更新。

## 任务详情

### M1: Observability Engine（1.5 天）

创建 `zcore/engines/observability.py`：

```python
@dataclass
class ExecutionStats:
    total: int
    success: int
    failed: int
    avg_duration_ms: float
    by_skill: dict[str, int]      # skill_name → count
    by_status: dict[str, int]     # status → count
    period: str                   # e.g. "7d"

@dataclass
class CostReport:
    total_usd: float
    by_provider: dict[str, float]  # provider → cost
    by_model: dict[str, float]     # model → cost
    budget_limit: float
    budget_remaining: float
    period: str

@dataclass
class HealthReport:
    healthy: bool
    checks: dict[str, str]        # check_name → "ok" | "warn" | "fail"
    warnings: list[str]
    disk_usage: dict[str, int]    # dir_name → bytes

class ObservabilityEngine:
    def __init__(self, runtime_paths: RuntimePaths): ...
    
    def log_execution(self, skill_name, status, duration_ms, cost_usd=None, provider=None, model=None, ...): ...
    def log_cost(self, provider, model, input_tokens, output_tokens, cost_usd): ...
    
    def get_execution_stats(self, since: str = "7d", skill_name: str | None = None) -> ExecutionStats: ...
    def get_cost_report(self, since: str = "30d", provider: str | None = None) -> CostReport: ...
    def health_check(self) -> HealthReport: ...
```

**集成改造**：
- 改造 `builtin.py` 的 `log_execution` hook：除了写 JSONL，还调用 `ObservabilityEngine.log_execution()` 追加成本字段
- 在 `ghost_agent.py` 的 API 调用成功/失败后，调用 `ObservabilityEngine.log_cost()` 记录 token 用量和成本（根据 provider 的公开定价估算）
- `costs.jsonl` 格式：`{"timestamp", "provider", "model", "input_tokens", "output_tokens", "cost_usd", "session_id", "skill_name"}`

**CLI 新增**：
- `zcore observe stats [--since 7d] [--skill <name>] [--json]`
- `zcore observe costs [--since 30d] [--provider <name>] [--json]`
- `zcore observe health [--json]`

### M2: Agent Setup 自动化（1 天）

创建 `zcore/engines/agent_setup.py`：

```python
@dataclass
class AgentInfo:
    name: str          # "claude" | "gemini" | "codex"
    detected: bool
    config_path: Path | None
    version: str | None
    zcore_integrated: bool  # 是否已有 ZCORE:START 标记块

@dataclass  
class SetupResult:
    agent: str
    success: bool
    config_path: str
    changes: list[str]   # 变更描述列表
    backup_path: str | None

class AgentSetupEngine:
    def __init__(self, runtime_paths: RuntimePaths): ...
    
    def detect_agents(self) -> list[AgentInfo]: ...
    def setup_agent(self, agent_name: str, *, dry_run: bool = False) -> SetupResult: ...
    def render_injection_block(self) -> str: ...
```

**注入内容模板**（10-15 行）：
```markdown
<!-- ZCORE:START (managed by zcore setup, do not edit manually) -->
## Z-Core Runtime Integration

- 开始新任务时：`zcore session start --project <project> --agent <agent> --json`
- 完成任务后：`zcore session end --session-id <id> --json`
- 搜索记忆：`zcore memory search "<query>" --json`
- 上下文分析：`zcore context analyze --model <model> --input <file> --json`
- 执行 skill：`zcore run <skill-name> [--args] --json`
- 所有 zcore 命令都加 `--json` 获取结构化输出
<!-- ZCORE:END -->
```

**Agent 适配器**：
- `_detect_claude()` → 检测 `~/.claude/CLAUDE.md` 是否存在
- `_detect_gemini()` → 检测 `~/.gemini/GEMINI.md` 或 `~/.gemini/settings.json`
- `_detect_codex()` → 检测 `~/.codex/AGENTS.md` 或 `AGENTS.md`
- `_setup_agent(config_path)` → 读取文件，查找/替换标记块，备份原文件后写入

**CLI 新增**：
- `zcore setup <agent> [--dry-run] [--json]`（agent = claude | gemini | codex | all）
- `zcore setup detect [--json]`

### M3: Config CLI（0.5 天）

**不需要新建 engine**，直接在 `cli/main.py` 中实现，读写 `config.toml`。

**CLI 新增**：
- `zcore config show [--section <name>] [--json]` — 展示配置，掩码 api_key 等敏感字段
- `zcore config set <key> <value>` — dot notation 设置（如 `governance.permission_mode yolo`），原子写入
- `zcore config reset [--section <name>] [--force]` — 重置为默认

**实现约束**：
- `config set` 需要读取现有 TOML → 修改 → 写回。可以用字符串替换或 simple TOML writer（不引入 tomlkit 依赖）。推荐用 `re` 替换 section 内的 key = value 行。
- `config show` 的敏感字段掩码：匹配 `api_key`、`secret`、`password`、`token` 等 key 名，值替换为 `***`。

### M4: Governance CLI 扩展 + 自定义 Hook + 测试（1.5 天）

**Governance CLI 扩展**：
- `zcore governance allow <pattern>` — 添加 allow 规则到 `[governance.rules]`
- `zcore governance deny <pattern>` — 添加 deny 规则
- `zcore governance log [--last N] [--skill <name>] [--json]` — 读取 `executions.jsonl` 展示

**自定义 Hook 脚本**：
- 扩展 `HookRunner.load_hooks()` 支持从 `~/.zcore/hooks/pre-execute.d/` 和 `post-execute.d/` 加载 `.py` 和 `.sh` 脚本
- 按文件名排序确定优先级（`10-xxx.sh` < `20-yyy.py`）
- 脚本执行：`subprocess.run()` + 环境变量注入（`ZCORE_SKILL_NAME`, `ZCORE_SESSION_ID`, `ZCORE_PROJECT`）
- exit 0 = pass, exit 1 = fail（pre-hook 阻塞执行）, stdout = message
- builtin hooks 优先级始终在自定义脚本之前

**测试**：
- `tests/test_observability.py`：ExecutionStats 计算、CostReport 计算、HealthReport
- `tests/test_agent_setup.py`：detect agents（模拟文件系统）、setup 注入（幂等更新验证）
- `tests/test_config_cli.py`：config show/set/reset CLI 端到端
- `tests/test_governance_ext.py`：governance allow/deny 规则持久化、governance log 读取、自定义 hook 脚本执行
- 验收：新增 ≥8 个测试，总计 36+ 测试全部通过

## 交付标准

1. 全部新文件通过 `python3 -m compileall zcore tests`
2. `python3 -m unittest -q tests.test_observability tests.test_agent_setup tests.test_config_cli tests.test_governance_ext` 全部通过
3. 历史测试 `python3 -m unittest -q tests.test_skill_router tests.test_zcore_cli tests.test_zcore_runtime tests.test_zcore_context tests.test_zcore_ghost_agent tests.test_zcore_memory` 回归通过
4. 冒烟验证：
   - `python3 -m zcore observe stats --json`
   - `python3 -m zcore observe health --json`
   - `python3 -m zcore setup detect --json`
   - `python3 -m zcore config show --json`
   - `python3 -m zcore governance allow "shell(npm test)" --json`
   - `python3 -m zcore governance log --last 5 --json`
5. 执行 code-review self-review，修复所有 Blocking 问题

## 完成后更新 PM 文件

- `v2/pm/Current-State.md`: 更新成功标准完成状态
- `v2/pm/Sprint-Backlog.md`: 标记 M1-M4 ✅
- `v2/pm/sprint-status.md`: 更新验证结果
- `v2/pm/Decision-Log.md`: 记录实现期间的任何决策变更

## 技术约束（必读）

- **零外部依赖**：不引入 tomlkit、PyYAML、click 等。用 stdlib re/tomllib/argparse/subprocess
- **Python ≥3.11**：可用 tomllib（stdlib）
- **保持 argparse**：CLI 继续用 argparse，不迁移 Click
- **config set 的 TOML 写入**：由于 stdlib 没有 TOML writer，用正则字符串替换方式修改 config.toml。注意保持文件格式和注释
- **成本估算**：Ghost Agent 的成本估算可以硬编码主要 provider 的公开定价（Google Gemini Flash, Anthropic Haiku, OpenAI GPT-4o-mini），不需要实时查询定价 API
