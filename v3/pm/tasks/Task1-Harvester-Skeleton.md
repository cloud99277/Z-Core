# Task 1: Harvester 骨架 — 数据模型 + SourceAdapter ABC + Engine + CLI

## 目标

建立 Harvester 收割机的完整框架（不含具体 adapter 实现），包括数据模型、抽象基类、引擎骨架和 CLI 命令。

## 上下文

- 62 测试通过，commit `4112080`，分支 `v3/develop`
- Z-Core v0.2.0，零外部依赖，CLI 使用 argparse
- 已有 `zcore/utils/privacy.py`：`redact_text()` 函数
- 已有 `tests/helpers.py`：`run_zcore`, `TestHome`

## Allowed write set

- `zcore/adapters/__init__.py` — 新建
- `zcore/adapters/base.py` — 新建：SourceAdapter ABC
- `zcore/models/harvester.py` — 新建
- `zcore/engines/harvester.py` — 新建
- `zcore/cli/main.py` — 修改：新增 `harvest` 子命令
- `tests/test_harvester.py` — 新建

## Protected surface（不得修改）

- `zcore/engines/session.py`、`memory.py`、`context.py`、`workflow.py`
- `zcore/config.py`、`zcore/runtime.py`
- 所有 `v2/pm/` 文件

## 任务详情

### 1. 数据模型 `zcore/models/harvester.py`

```python
@dataclass
class HarvestedSession:
    source: str                          # "claude" | "hermes"
    source_session_id: str
    project: str
    started_at: str                      # ISO 8601
    ended_at: str | None = None
    messages: list[dict[str, str]] = field(default_factory=list)  # [{"role": "user"|"assistant", "content": "..."}]
    summary: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

@dataclass
class HarvestResult:
    source: str
    discovered: int
    ingested: int
    skipped: int
    errors: list[str] = field(default_factory=list)
```

### 2. SourceAdapter ABC `zcore/adapters/base.py`

```python
class SourceAdapter(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def discover(self, project: str | None = None) -> list[dict[str, object]]: ...

    @abstractmethod
    def ingest(self, session_id: str) -> HarvestedSession | None: ...

    @abstractmethod
    def health_check(self) -> dict[str, object]: ...
```

### 3. HarvesterEngine `zcore/engines/harvester.py`

```python
class HarvesterEngine:
    def __init__(self, paths=None):
        # 维护 adapter 注册表（dict[str, SourceAdapter]）
        # 自动尝试导入已知 adapter（claude/hermes），导入失败不 crash

    def register_adapter(self, adapter: SourceAdapter) -> None: ...
    def discover(self, source=None, project=None) -> list[dict]: ...
    def ingest(self, source=None, project=None, *, dry_run=False) -> dict: ...
    def status(self) -> dict: ...
```

- 收割结果存入 `~/.zcore/harvested/{source}/{session_id}.json`
- 已收割 session 记录在 `~/.zcore/harvested/index.json` 避免重复
- 收割时调用 `redact_text()` 脱敏

### 4. CLI 命令（追加到 `zcore/cli/main.py`）

- `zcore harvest discover [--source X] [--json]`
- `zcore harvest ingest [--source X] [--dry-run] [--json]`
- `zcore harvest status [--json]`

### 5. 测试 `tests/test_harvester.py`（≥ 5 用例）

- HarvestedSession / HarvestResult dataclass 创建
- HarvesterEngine 初始化（无 adapter 时不 crash）
- discover/ingest 空 adapter 返回空列表
- status 输出格式正确
- CLI `harvest status --json` 返回有效 JSON

## 交付标准

1. `python3 -m compileall zcore tests` 通过
2. `python3 -m unittest discover tests -q` 全部通过（62 + ≥ 5 新增）
3. `zcore harvest status --json` 输出有效 JSON
4. `zcore harvest discover --json` 输出空列表（无 adapter 注册时）
5. code-review 自审通过

## 技术约束

- 零外部依赖
- Python ≥3.11
- adapter 导入失败时静默跳过（不 crash）
- 使用 `from tests.helpers import run_zcore, TestHome`
