# Phase 6: V2 收官 — Workflow Engine + Session/Memory 补全 + 打包发布

## 目标

关闭 V2 全部 CLI 缺口（35/35 = 100%），完成 Workflow Engine（最后一个设计文档中的 Engine），补全 session pause/resume 和 memory expire-check，最终打包为 `pip install` 可用的标准 Python 包。Phase 6 之后 V2 进入维护模式，后续重大功能进入 V3 规划。

## 上下文

- 当前 29 测试通过，commit `63b5c71`，分支 `feat/v2`
- CLI 覆盖率 89%（31/35），缺 workflow×3 + session pause/resume + memory expire-check
- 已有共享测试 helper：`tests/helpers.py`（`run_zcore`, `TestHome`, `pushd`）
- 保持零外部依赖原则
- 已有 `parse_since_window()` 在 `zcore/utils/time.py`

## 执行方法论

本任务使用 `delegated-sprint` skill 的标准流程。

### 执行 Agent 必须遵守的规则

1. **🔒 code-review 自审不可跳过**：编码完成后，先 `view_file` 读取 `~/.ai-skills/code-review/SKILL.md`，然后按其流程执行 self-review。
2. **测试先行**：每个 Milestone 完成后先验证该 Milestone 的测试通过。
3. **回归保护**：最终交付前，`python3 -m unittest discover tests -q` 必须全部通过。
4. **PM 文件同步**：编码完成后更新 PM 文件。
5. **使用共享 helper**：从 `tests/helpers.py` 导入 `run_zcore`, `TestHome`。

## 任务详情

### M1: Workflow Engine + CLI（2 天）

新增 `zcore/engines/workflow.py`，交付 `zcore workflow list/run/validate`。

**设计约束**：
- **不用 YAML**（stdlib 没有 YAML parser）。Workflow 定义文件使用 **TOML** 格式（`tomllib` stdlib），与项目 config.toml 风格一致。
- Workflow 文件放在 `~/.zcore/workflows/*.toml` 或项目目录下 `.zcore/workflows/*.toml`
- 每个 workflow 是一个有序步骤序列，每步调用一个 skill

**Workflow 定义格式**（TOML）：

```toml
[workflow]
name = "daily-review"
description = "每日代码审查 + 记忆提取"

[[steps]]
name = "extract-memories"
skill = "memory-manager"
command = "memory extract"
args = ["--topic", "daily"]
on_failure = "continue"  # continue | abort (默认 abort)

[[steps]]
name = "run-audit"
skill = "governance"
command = "governance audit"
args = ["--json"]
on_failure = "abort"

[[steps]]
name = "health-check"
skill = "observability"
command = "observe health"
args = ["--json"]
on_failure = "continue"
```

**`zcore workflow list [--json]`**
- 列出所有发现的 workflow 文件（全局 + 项目级）
- 显示 name、description、步骤数
- 验收：`zcore workflow list --json` 输出 workflow 列表

**`zcore workflow validate <name|file> [--json]`**
- 校验 workflow TOML 文件语法和结构
- 检查引用的 skill 是否存在
- 输出 PASS/WARN/ERROR 检查结果
- 验收：`zcore workflow validate daily-review --json` 输出检查结果

**`zcore workflow run <name|file> [--dry-run] [--json]`**
- 按顺序执行 workflow 的每个步骤
- 每步通过 `subprocess.run([sys.executable, "-m", "zcore", *command_parts])` 调用
- `--dry-run` 只打印将要执行的命令，不实际执行
- `on_failure = "continue"` 时失败步骤不中断
- 输出每步的执行结果（status、stdout 摘要、耗时）
- 验收：`zcore workflow run daily-review --dry-run --json` 输出步骤执行计划

**实现位置**：
- 新增 `zcore/engines/workflow.py`：`WorkflowEngine`（`discover_workflows()`, `load_workflow()`, `validate_workflow()`, `run_workflow()`）
- 新增 `zcore/models/workflow.py`：`WorkflowDefinition`, `WorkflowStep`, `WorkflowResult` dataclass
- CLI 新增 `workflow` subparser 到 `zcore/cli/main.py`

**数据结构**：

```python
@dataclass
class WorkflowStep:
    name: str
    skill: str
    command: str                    # 如 "memory extract"
    args: list[str]
    on_failure: str = "abort"       # "abort" | "continue"

@dataclass
class WorkflowDefinition:
    name: str
    description: str
    steps: list[WorkflowStep]
    source_path: str                # 来源文件路径

@dataclass
class StepResult:
    step_name: str
    status: str                     # "ok" | "skipped" | "error"
    returncode: int
    stdout_summary: str             # 前 500 字符
    duration_ms: int

@dataclass
class WorkflowResult:
    workflow_name: str
    dry_run: bool
    steps: list[StepResult]
    overall: str                    # "ok" | "partial" | "failed"
```

### M2: Session pause/resume（1 天）

补全 `zcore session pause/resume`。

**状态机**：
```
  start → active → pause → paused → resume → active → end → completed
```

**`zcore session pause [--session-id <id>] [--json]`**
- 暂停当前活跃会话（或指定 ID 的会话）
- 仅 `active` 状态可暂停
- 将状态改为 `paused`，记录 `paused_at` 时间戳
- 不触发 memory 提取或 hook（暂停不等于结束）
- 验收：`zcore session pause --json` 暂停当前会话

**`zcore session resume [--session-id <id>] [--json]`**
- 恢复暂停的会话
- 仅 `paused` 状态可恢复
- 将状态改回 `active`，记录 `resumed_at` 时间戳
- 验收：`zcore session resume --json` 恢复暂停的会话

**实现位置**：
- 扩展 `zcore/engines/session.py` 的 `SessionManager`，添加 `pause()` 和 `resume()` 方法
- 扩展 `zcore/models/session.py` 的 `SessionMeta`：添加 `paused_at: str | None` 和 `resumed_at: str | None` 字段
- CLI 在 `session` subparser 下添加 `pause` 和 `resume`

### M3: Memory expire-check + 打包（1.5 天）

**`zcore memory expire-check [--older-than 90d] [--dry-run] [--json]`**
- 检查过期的记忆条目（基于 `updated_at` 时间戳）
- `--older-than` 默认 90d，使用 `parse_since_window()`
- `--dry-run` 只列出将被标记为过期的条目，不实际修改
- 非 dry-run 时，将过期条目的 `type` 标记为 `expired`（或移到 `expired/` 子目录）
- 验收：`zcore memory expire-check --dry-run --json` 列出过期条目

**实现位置**：
- 扩展 `zcore/engines/memory.py` 的 `MemoryEngine`，添加 `expire_check()` 方法
- CLI 在 `memory` subparser 下添加 `expire-check`

**pyproject.toml 打包**：
- 创建 `pyproject.toml`：
  - `[project]` name=`zcore`, version=`0.2.0`, python_requires=`>=3.11`
  - `[project.scripts]` zcore=`"zcore.cli.main:main"`
  - `[build-system]` requires=`["setuptools>=68.0"]`
  - 不引入任何运行时依赖
- 创建 `zcore/__version__.py`：`__version__ = "0.2.0"`
- 更新 `zcore/__init__.py`：导入 `__version__`
- 验收：`pip install -e .` 后 `zcore --version` 输出 `0.2.0`
- 验收：`zcore init --json` 正常运行

### M4: 测试 + 回归 + 文档（0.5 天）

**Phase 6 新增测试**：
- `tests/test_workflow.py`：workflow discover/validate/run dry-run/run with failure
- `tests/test_session_pause.py`：session pause/resume/pause-resume-end 全程
- `tests/test_memory_expire.py`：memory expire-check dry-run/actual

**测试要求**：
- 新增 ≥8 个测试，总计 37+ 测试全部通过
- `python3 -m unittest discover tests -q` 无错完成
- `python3 -m compileall zcore tests` 通过

**文档更新**：
- 更新 `v2/pm/Current-State.md`：标记 V2 全部完成
- 更新 `v2/pm/Sprint-Backlog.md`：M1-M4 标记完成
- 更新 `v2/pm/sprint-status.md`：最终状态
- 更新 `v2/pm/Decision-Log.md`：Phase 6 实现决策
- 更新 `v2/pm/Changelog.md`：Phase 6 变更

## 交付标准

1. `python3 -m compileall zcore tests` 通过
2. `python3 -m unittest discover tests -q` 全部通过（37+ tests）
3. CLI 命令 35/35 = 100% 覆盖
4. `pip install -e .` 成功，`zcore --version` 输出 `0.2.0`
5. 冒烟验证：
   - `zcore workflow list --json`
   - `zcore workflow validate <test-workflow> --json`
   - `zcore workflow run <test-workflow> --dry-run --json`
   - `zcore session pause --json` + `zcore session resume --json`
   - `zcore memory expire-check --dry-run --json`
   - `zcore --version`
6. code-review 自审通过

## 技术约束（必读）

- **零外部依赖**：不引入 click、PyYAML、tomlkit 等
- **Python ≥3.11**：可用 `tomllib`（stdlib）
- **Workflow 用 TOML**：`tomllib.loads()` 解析 workflow 定义文件
- **session pause/resume 不触发 hook**：暂停不等于结束，不执行 post-execute hook
- **memory expire-check 的过期策略**：标记 `type = "expired"` 而不是删除（可恢复）
- **pyproject.toml 打包**：使用 `setuptools`，`[project.scripts]` 声明 CLI 入口
- **使用共享 helper**：新测试 `from tests.helpers import run_zcore, TestHome`
