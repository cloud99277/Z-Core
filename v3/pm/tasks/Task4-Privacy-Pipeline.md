# Task 4: 隐私脱敏管线增强 (M3)

## 目标

增强 `utils/privacy.py`，支持更多脱敏模式（IP/email/phone），新增 `sanitize_transcript()` 函数用于会话级批量脱敏，并实现 `ingest-ignore` 规则文件。

## 上下文

- 分支 `v3/develop`，83 测试通过，commit `4d07b39`
- 已有 `zcore/utils/privacy.py`：`redact_text()` 函数（3 个 DEFAULT_PATTERNS + 文件路径脱敏）
- 已有 `zcore/engines/harvester.py`：`_redact_session()` 调用 `redact_text()` 逐字段脱敏
- 已有 `tests/helpers.py`：`run_zcore`, `TestHome`
- 零外部依赖

## Allowed write set

- `zcore/utils/privacy.py` — 修改
- `zcore/engines/harvester.py` — 修改（集成 ingest-ignore）
- `tests/test_privacy.py` — 新建
- `tests/test_ingest_ignore.py` — 新建

## Protected surface（不得修改）

- `zcore/adapters/base.py`、`claude_adapter.py`、`hermes_adapter.py`
- `zcore/engines/session.py`、`memory.py`、`context.py`、`workflow.py`
- `zcore/config.py`、`zcore/runtime.py`
- `zcore/models/harvester.py`

## 任务详情

### 1. 增强 `redact_text()` 默认模式

在 `DEFAULT_PATTERNS` 中新增以下模式：

```python
# IPv4
r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"
# Email
r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
# 中国手机号
r"\b1[3-9]\d{9}\b"
# AWS Access Key
r"AKIA[0-9A-Z]{16}"
# Bearer Token
r"Bearer\s+[A-Za-z0-9\-._~+/]+=*"
```

**关键约束**：现有 `redact_text()` 签名和行为不变，`patterns` 参数仍可覆盖默认列表。

### 2. 新增 `sanitize_transcript()`

```python
def sanitize_transcript(
    messages: list[dict[str, str]],
    *,
    patterns: Iterable[str] | None = None,
    redact_file_paths: bool = True,
) -> list[dict[str, str]]:
    """批量脱敏会话消息列表，返回新列表（不修改原数据）。"""
```

对每条消息的 `content` 字段调用 `redact_text()`，返回深拷贝后的脱敏列表。

### 3. `ingest-ignore` 规则文件

**位置**：`~/.zcore/ingest-ignore`

**格式**：每行一条 glob pattern，`#` 开头为注释，空行跳过：

```
# 忽略包含 secret 目录的路径
**/secret/**
# 忽略特定项目
**/private-project/**
```

**实现**：

```python
# zcore/utils/privacy.py
def load_ingest_ignore(path: Path) -> list[str]:
    """读取 ingest-ignore 文件，返回 glob pattern 列表。"""

def should_ignore(session_path: str, patterns: list[str]) -> bool:
    """判断 session 路径是否匹配任何 ignore pattern。"""
```

使用 `fnmatch.fnmatch` 匹配（stdlib）。

### 4. Harvester 集成 ingest-ignore

修改 `HarvesterEngine.ingest()`：

- 初始化时加载 `~/.zcore/ingest-ignore`
- 在 ingest 循环中，对每个 discovered session 的 `path` 字段执行 `should_ignore()` 检查
- 匹配 ignore 的 session 标记为 `skipped`，记入 result
- `ingest-ignore` 文件不存在时，行为与修改前一致（空 pattern 列表）

### 5. 测试

#### `tests/test_privacy.py`（≥ 5 用例）

- `redact_text()` 脱敏 API key → `[REDACTED]`
- `redact_text()` 脱敏 IPv4 地址 → `[REDACTED]`
- `redact_text()` 脱敏 Email 地址 → `[REDACTED]`
- `redact_text()` 脱敏中国手机号 → `[REDACTED]`
- `sanitize_transcript()` 批量脱敏消息列表
- `sanitize_transcript()` 不修改原始输入（深拷贝验证）

#### `tests/test_ingest_ignore.py`（≥ 3 用例）

- `load_ingest_ignore()` 读取文件，跳过注释和空行
- `should_ignore()` 匹配 glob pattern
- HarvesterEngine 集成：ingest 时跳过被 ignore 的 session

## 交付标准

1. `python3 -m compileall zcore tests` 通过
2. `python3 -m unittest discover tests -q` 全部通过（83 + ≥ 8 新增）
3. 所有现有测试不受影响
4. `redact_text("Send to sk-abc123def456ghi789 at user@example.com")` → 所有敏感信息被替换

## 技术约束

- 零外部依赖（re + fnmatch + pathlib，全部 stdlib）
- 现有 `redact_text()` 调用方（harvester, ghost_agent, session）行为自动增强（因为 DEFAULT_PATTERNS 扩展）
- 不引入新的 config.toml 区块
