# V3 Sprint 1: Harvester 收割机 + GhostAgent 角色切换（M1 + M2）

## 目标

为 Z-Core 新增"数据主动获取"能力：实现 Harvester Engine 和 Source Adapter 框架，使 Z-Core 能从 Claude Code 和 Hermes 的本地日志中自动收割会话数据。同时增强 GhostAgent 支持按角色路由到不同模型。

## 上下文

- 当前 62 测试通过，commit `4112080`，分支 `v3/develop`
- Z-Core v0.2.0，9 个 Engine，35 CLI 命令，零外部依赖
- 已有 `zcore/engines/ghost_agent.py`：`GhostAgent` 类，`generate()` 方法已有 `prompt`, `fallback_text`, `session_id`, `skill_name` 参数
- 已有 `zcore/utils/privacy.py`：`redact_text()` 函数（支持 API key/token/secret/password 模式）
- 已有 `zcore/models/` 目录：`memory.py`, `session.py`, `skill.py`, `workflow.py`
- 已有共享测试 helper：`tests/helpers.py`（`run_zcore`, `TestHome`, `pushd`）
- 已有 `zcore/config.py`：`load_config()`, `get_nested()` 用于读取 `config.toml`
- CLI 框架使用 `argparse`（stdlib），入口在 `zcore/cli/main.py`
- **保持零外部依赖原则**

## 文件边界

### Allowed write set

- `zcore/adapters/__init__.py` — 新建
- `zcore/adapters/base.py` — 新建：SourceAdapter ABC
- `zcore/adapters/claude_adapter.py` — 新建
- `zcore/adapters/hermes_adapter.py` — 新建
- `zcore/engines/harvester.py` — 新建
- `zcore/models/harvester.py` — 新建
- `zcore/engines/ghost_agent.py` — 修改：新增 role 路由
- `zcore/cli/main.py` — 修改：新增 `harvest` + `ghost` 子命令
- `tests/test_harvester.py` — 新建
- `tests/test_adapters.py` — 新建
- `tests/test_ghost_roles.py` — 新建

### Shared files (mainline only)

- `zcore/cli/main.py` — 仅追加新的 subparser，不修改已有命令的逻辑
- `zcore/__init__.py` — 如需导出新模块可修改

### Protected surface (read-only unless task explicitly targets it)

- `zcore/engines/session.py` — 不得修改
- `zcore/engines/memory.py` — 不得修改
- `zcore/engines/context.py` — 不得修改
- `zcore/engines/workflow.py` — 不得修改
- `zcore/config.py` — 不得修改
- `zcore/runtime.py` — 不得修改
- 所有 `v2/pm/` 文件 — 不得修改

## 回归保护基线

### Must preserve

- 所有 62 个现有测试必须继续通过
- `zcore --version` 输出 `0.2.0`
- `zcore init --json` 正常工作
- `GhostAgent.generate()` 不传 `role` 参数时行为完全不变

### Forbidden regressions

- 不得引入任何 `import` 失败（`python3 -m compileall zcore tests`）
- 不得修改 `redact_text()` 的现有行为
- 不得修改 `config.toml` 的已有字段语义

### Required checks

```bash
python3 -m compileall zcore tests
python3 -m unittest discover tests -q
# 确认 62+ 原有测试通过
zcore --version  # 输出 0.2.0
```

## 执行方法论

### 执行 Agent 必须遵守的规则

1. **🔒 code-review 自审不可跳过**：编码完成后，先 `view_file` 读取 `~/.ai-skills/code-review/SKILL.md`，然后按其流程执行 self-review。
2. **测试先行**：每个 Milestone 完成后先验证该 Milestone 的测试通过。
3. **回归保护**：最终交付前，`python3 -m unittest discover tests -q` 必须全部通过（62+ 原有 + 新增）。
4. **PM 文件同步**：编码完成后更新 `v3/pm/` 下的 PM 文件。
5. **使用共享 helper**：从 `tests/helpers.py` 导入 `run_zcore`, `TestHome`。
6. **里程碑准出门禁**：M1 准出标准全部通过后才能开始 M2。

## 任务详情

### M1: Harvester 收割机原型（5-7 天）

#### M1.1 数据模型定义

新增 `zcore/models/harvester.py`：

```python
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class HarvestedSession:
    """从外部 Agent 收割的单次会话。"""
    source: str                          # "claude" | "hermes" | "cursor"
    source_session_id: str               # 外部系统的会话 ID
    project: str                         # 项目名/路径
    started_at: str                      # ISO 8601
    ended_at: str | None = None
    messages: list[dict[str, str]] = field(default_factory=list)  # [{"role": "user"|"assistant", "content": "..."}]
    summary: str = ""                    # 可选的会话摘要
    metadata: dict[str, object] = field(default_factory=dict)

@dataclass
class HarvestResult:
    """一次收割操作的结果。"""
    source: str
    discovered: int                      # 发现的会话数
    ingested: int                        # 成功收割的会话数
    skipped: int                         # 跳过的（已收割/不符合条件）
    errors: list[str] = field(default_factory=list)
```

#### M1.2 SourceAdapter ABC

新增 `zcore/adapters/base.py`：

```python
from __future__ import annotations
from abc import ABC, abstractmethod

class SourceAdapter(ABC):
    """外部 Agent 数据源适配器基类。"""

    @abstractmethod
    def name(self) -> str:
        """适配器名称，如 "claude", "hermes"。"""

    @abstractmethod
    def discover(self, project: str | None = None) -> list[dict[str, object]]:
        """发现可收割的会话列表。
        返回: [{"session_id": str, "project": str, "started_at": str, "status": str}]
        """

    @abstractmethod
    def ingest(self, session_id: str) -> dict[str, object]:
        """收割指定会话的完整数据。
        返回: HarvestedSession 的 dict 表示。
        """

    @abstractmethod
    def health_check(self) -> dict[str, object]:
        """检查数据源是否可用。
        返回: {"available": bool, "reason": str, "path": str}
        """
```

#### M1.3 Claude Adapter

新增 `zcore/adapters/claude_adapter.py`：

- 扫描 `~/.claude/projects/` 目录（如果存在）
- 解析 Claude Code 的会话 JSON 文件
- **重要**：Claude 的日志格式可能随版本变化，adapter 必须在解析失败时返回结构化错误而不是 crash
- `health_check()` 检查 `~/.claude/` 目录是否存在

#### M1.4 Hermes Adapter

新增 `zcore/adapters/hermes_adapter.py`：

- 使用 `sqlite3`（stdlib）读取 Hermes 的 session 数据库
- 扫描 `~/.hermes/` 目录（如果存在）
- 解析 session 表的 messages 字段
- `health_check()` 检查数据库文件是否存在且可读

#### M1.5 Harvester Engine

新增 `zcore/engines/harvester.py`：

```python
class HarvesterEngine:
    """收割机引擎：管理多个 SourceAdapter，统一收割和存储。"""

    def __init__(self, paths: RuntimePaths | None = None):
        # 自动注册已有的 adapter

    def discover(self, source: str | None = None, project: str | None = None) -> list[dict]:
        """发现所有可收割的会话（支持按 source 过滤）。"""

    def ingest(self, source: str | None = None, project: str | None = None, *, dry_run: bool = False) -> dict:
        """执行收割（支持 dry_run）。"""

    def status(self) -> dict:
        """返回各 adapter 的健康状态和历史收割统计。"""

    def _persist_harvested(self, session: HarvestedSession) -> None:
        """将收割结果写入 ~/.zcore/harvested/{source}/{session_id}.json。"""
```

- 收割结果存储路径：`~/.zcore/harvested/{source}/{session_id}.json`
- 已收割的 session 记录在 `~/.zcore/harvested/index.json` 中，避免重复收割
- 收割时自动调用 `redact_text()` 对内容脱敏

#### M1.6 CLI 命令

在 `zcore/cli/main.py` 中新增 `harvest` subparser：

- **`zcore harvest discover [--source claude|hermes] [--project <path>] [--json]`**
  - 列出可收割的会话
  - 验收：输出会话列表（ID / 来源 / 项目 / 时间）

- **`zcore harvest ingest [--source claude|hermes] [--project <path>] [--dry-run] [--json]`**
  - 执行收割
  - `--dry-run` 只显示将要收割的会话，不实际写入
  - 验收：`--dry-run` 输出计划，非 dry-run 写入 `~/.zcore/harvested/`

- **`zcore harvest status [--json]`**
  - 显示各 adapter 健康状态和收割统计
  - 验收：输出每个 adapter 的 available/reason/harvest_count

#### M1 准出标准

- [ ] `SourceAdapter` ABC 定义完成，包含 `discover/ingest/health_check` 三个抽象方法
- [ ] Claude adapter 能正确解析 `~/.claude/` 目录中的会话文件（如不存在返回空列表而不是报错）
- [ ] Hermes adapter 能通过 SQLite 读取会话数据（如不存在返回空列表而不是报错）
- [ ] `zcore harvest discover --json` 输出有效 JSON
- [ ] `zcore harvest ingest --dry-run --json` 输出有效 JSON
- [ ] `zcore harvest status --json` 输出有效 JSON
- [ ] `tests/test_harvester.py` + `tests/test_adapters.py` ≥ 5 个测试全部通过
- [ ] `python3 -m unittest discover tests -q` 全部通过（62+ 原有 + 新增）

---

### M2: GhostAgent 角色切换（1-2 天）

**前置条件**：M1 准出标准全部通过。

#### M2.1 config.toml 角色配置

在 `config.toml` 中新增可选的 `[llm_backend.roles]` 区块：

```toml
[llm_backend]
enabled = true
provider = "google"
model = "gemini-2.5-flash"          # 默认模型

[llm_backend.roles]
compact = "gemini-2.5-flash"        # 轻量压缩任务
planner = "claude-sonnet-4-20250514"  # 复杂推理任务
evaluator = "gemini-2.5-flash"      # 质量评估
```

#### M2.2 修改 GhostAgent.generate()

在 `zcore/engines/ghost_agent.py` 中修改 `generate()` 方法签名：

```python
def generate(
    self,
    prompt: str,
    fallback_text: str | None = None,
    *,
    role: str | None = None,        # 新增：角色名，用于路由到对应模型
    session_id: str | None = None,
    skill_name: str | None = None,
) -> dict[str, object]:
```

实现逻辑：
1. 如果 `role` 不为 None，从 `config.toml` 的 `[llm_backend.roles]` 中查找对应模型
2. 如果找到角色模型，临时用该模型替代默认模型进行请求
3. 如果角色模型不存在或请求失败，fallback 到默认模型
4. **不传 `role` 参数时，行为与 V2 完全一致**（向下兼容）
5. 返回的 dict 中新增 `"role": role` 字段（如果使用了角色路由）

#### M2.3 新增 `zcore ghost roles [--json]` CLI

新增 CLI 命令用于查看当前配置的角色和对应模型：

```
$ zcore ghost roles --json
{
  "default_model": "gemini-2.5-flash",
  "roles": {
    "compact": "gemini-2.5-flash",
    "planner": "claude-sonnet-4-20250514",
    "evaluator": "gemini-2.5-flash"
  }
}
```

#### M2 准出标准

- [ ] `generate(role="compact")` 正确路由到 `[llm_backend.roles]` 中配置的模型
- [ ] `generate()` 不传 `role` 时行为与 V2 完全一致（回归保护）
- [ ] 角色模型不存在时 fallback 到 default_model，不报错
- [ ] `zcore ghost roles --json` 输出当前角色配置
- [ ] `tests/test_ghost_roles.py` ≥ 3 个测试全部通过
- [ ] `python3 -m unittest discover tests -q` 全部通过（62+ 原有 + M1 新增 + M2 新增）

## 交付标准

1. `python3 -m compileall zcore tests` 通过
2. `python3 -m unittest discover tests -q` 全部通过（62+ 原有 + ≥ 8 新增）
3. `zcore harvest discover --json` / `zcore harvest ingest --dry-run --json` / `zcore harvest status --json` 正常工作
4. `zcore ghost roles --json` 正常工作
5. 冒烟验证：
   - `zcore --version` → `0.2.0`
   - `zcore harvest discover --json`
   - `zcore harvest ingest --dry-run --json`
   - `zcore harvest status --json`
   - `zcore ghost roles --json`
6. code-review 自审通过
7. 文件边界未越界
8. 回归保护基线全部通过

## 技术约束（必读）

- **零外部依赖**：不引入任何第三方库
- **Python ≥3.11**：可用 `tomllib`、`sqlite3`、`json`、`pathlib`（全部 stdlib）
- **adapter 容错**：数据源不存在时返回空结果 + 结构化错误，绝不 crash
- **脱敏前置**：所有收割内容在写入 `harvested/` 之前必须经过 `redact_text()` 处理
- **config.toml 向下兼容**：`[llm_backend.roles]` 是可选配置，不配也正常工作
- **使用共享 helper**：新测试 `from tests.helpers import run_zcore, TestHome`
- **CLI 框架**：使用 `argparse`（与已有命令一致），不得引入 click/typer
