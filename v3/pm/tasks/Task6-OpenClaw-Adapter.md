# Task 6: OpenClaw Adapter (M5)

## 目标

实现 `zcore/adapters/openclaw_adapter.py`，让 Harvester 收割机支持从 `~/.openclaw/agents/*/sessions/` 目录收割 OpenClaw 的所有对话数据。

## 上下文

- 分支 `v3/develop`，104 测试通过，commit `ecd7d35`（已包含全量审查修复）
- 已有 `zcore/adapters/base.py`：`SourceAdapter` ABC 接口（`name/discover/ingest/health_check`）
- 已有 `zcore/adapters/claude_adapter.py`：参考实现（JSONL 解析模式）
- 已有 `zcore/engines/harvester.py`：`HarvesterEngine`，注册 adapter 用 `register_adapter()`
- 已有 `tests/helpers.py`：`run_zcore`, `TestHome`
- 零外部依赖

### Current-State 快照

- M1 Harvester 收割机 🟢 完成
- M2 GhostAgent 角色切换 🟢 完成
- M3 隐私脱敏管线 🟢 完成
- M4 Session 全文搜索 🟢 完成
- **M5 OpenClaw Adapter ← 本任务**
- M6 Codex Adapter（并行，互不依赖）
- M7 Gemini Adapter（依赖格式探查）
- M8 SearchEngine FTS 索引化

### OpenClaw 数据格式（已探明）

**目录结构**：
```
~/.openclaw/agents/
  ├── main/sessions/
  │   └── <session-id>.json   ← 换行分隔 JSON 事件流
  ├── antigravity/sessions/
  ├── gemini-pro/sessions/
  ├── gemini-2-5-pro/sessions/
  └── gemini-3-1-pro-preview/sessions/
```

**session 文件格式**（换行分隔 JSON，每行一个事件）：
```json
{"type":"message","id":"f509d393","parentId":"0b283450","timestamp":"2026-04-24T14:38:44.933Z","message":{"role":"assistant","content":[{"type":"text","text":"..."}],"api":"google-generative-ai","provider":"google","model":"gemini-3.1-pro-preview",...}}
{"type":"message","id":"...","message":{"role":"user","content":[{"type":"input_text","text":"..."}],...}}
{"type":"message","id":"...","message":{"role":"toolResult","toolCallId":"...","content":[...],...}}
{"type":"custom","customType":"openclaw:bootstrap-context:full","data":{...}}
```

**关键字段**：
- `type == "message"` → 需要提取的行
- `message.role` → `"user"` / `"assistant"` / `"toolResult"` （只保留 user 和 assistant）
- `message.content` → list of blocks，只提取 `type in ["text","input_text"]` 的 `text` 字段
- `message.model` → 使用的模型名
- `message.api` → 后端类型（`google-generative-ai` / `openai-responses`）
- `timestamp` → ISO8601 时间戳
- 目录名（agent name）→ 作为 `project` 字段（`main` / `antigravity` 等）

## Allowed write set

- `zcore/adapters/openclaw_adapter.py` — 新建
- `zcore/adapters/__init__.py` — 修改（注册新 adapter）
- `zcore/engines/harvester.py` — 修改（默认注册 OpenClawAdapter）
- `tests/test_openclaw_adapter.py` — 新建

## Protected surface（不得修改）

- `zcore/adapters/base.py`、`claude_adapter.py`、`hermes_adapter.py`
- `zcore/engines/session.py`、`memory.py`、`context.py`、`workflow.py`、`search.py`
- `zcore/config.py`、`zcore/runtime.py`
- `zcore/models/harvester.py`、`zcore/models/search.py`
- `zcore/utils/privacy.py`
- `tests/test_adapters.py`、`tests/test_harvester.py`（不得修改，只能新建）

## 任务详情

### 1. 实现 `OpenClawAdapter`

```python
# zcore/adapters/openclaw_adapter.py
from __future__ import annotations

import json
from pathlib import Path

from zcore.adapters.base import SourceAdapter
from zcore.models.harvester import HarvestedSession


class OpenClawAdapter(SourceAdapter):
    BASE_DIR = Path.home() / ".openclaw" / "agents"

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or self.BASE_DIR

    def name(self) -> str:
        return "openclaw"

    def discover(self, project: str | None = None) -> list[dict[str, object]]:
        """扫描所有 agent 的 sessions 目录，返回 session 候选列表。"""
        # project 对应 agent 目录名（如 "main"、"antigravity"）
        ...

    def ingest(self, session_id: str) -> HarvestedSession | None:
        """加载单个 session 文件，解析事件流，提取 user/assistant 消息。"""
        ...

    def health_check(self) -> dict[str, object]:
        ...
```

**discover() 实现要点**：
- 遍历 `~/.openclaw/agents/<agent>/sessions/*.json`
- `project` 参数过滤 agent 目录名
- 返回列表元素**必须包含以下字段**（否则 HarvesterEngine 会打印 warning 并跳过）：
  - `source_session_id`：文件名去掉 `.json`（如 `abc-123-def`）
  - `path`：完整文件路径字符串（ingest-ignore 规则匹配用）
  - `project`：agent 目录名（如 `main`、`antigravity`）
  - `started_at`：文件首行 timestamp（ISO8601）

**ingest() 实现要点**：
- `session_id` 格式：`<agent_name>/<filename_without_ext>`（如 `main/abc-123`）
- 逐行解析 JSON，过滤 `type == "message"`
- 只保留 `message.role in ["user", "assistant"]`
- 提取 content：遍历 `message.content` list，只取 `block.type in ["text", "input_text"]` 的 `block.text`，拼接为字符串
- `started_at`：取第一条 user 消息的 timestamp
- `ended_at`：取最后一条消息的 timestamp
- 忽略解析错误的行（`try/except json.JSONDecodeError`）

### 2. 注册到 HarvesterEngine

**必须修改 `harvester.py` 的 `_auto_register_known_adapters()` 方法**（不是只改 `__init__.py`）：

将以下元组追加到 `_auto_register_known_adapters` 内的 `for` 循环列表：

```python
# harvester.py: _auto_register_known_adapters() 中的元组，追加第三项
for module_name, class_name in (
    ("zcore.adapters.claude_adapter", "ClaudeAdapter"),
    ("zcore.adapters.hermes_adapter", "HermesAdapter"),
    ("zcore.adapters.openclaw_adapter", "OpenClawAdapter"),  # ← 追加这一行
):
```

同时更新 `zcore/adapters/__init__.py` 导出 `OpenClawAdapter`：

```python
from zcore.adapters.openclaw_adapter import OpenClawAdapter
__all__ = ["ClaudeAdapter", "HermesAdapter", "OpenClawAdapter", "SourceAdapter"]
```

### 3. 测试 `tests/test_openclaw_adapter.py`（≥ 5 用例）

使用 `tempfile.TemporaryDirectory` 创建隔离的 `~/.openclaw/agents/` 结构：

- `test_discover_finds_sessions_across_agents`：发现多个 agent 目录下的 session 文件
- `test_discover_filters_by_project`：`project="main"` 只返回 main agent 的 session
- `test_ingest_extracts_user_assistant_messages`：正确提取 user/assistant，跳过 toolResult
- `test_ingest_handles_list_content_blocks`：content 为 list 时正确提取 text 块
- `test_ingest_skips_unknown_event_types`：`type != "message"` 的行被安全跳过
- `test_health_check_returns_ok_when_dir_exists`：目录存在时 health_check ok

使用 `unittest.mock.patch.dict("os.environ", ...)` 隔离 HOME 环境，或直接传入 `base_dir` 参数。

**必须新增 ingest-ignore 集成测试**（通过 HarvesterEngine 验证）：

- `test_harvester_skips_openclaw_session_matching_ingest_ignore`：
  通过 `HarvesterEngine` 的 `ingest()` 方法（传入带 ingest-ignore 文件的 `paths`），验证命中 glob 规则的 OpenClaw session 被计入 `skipped` 而不是 `ingested`。
  使用 `_isolated_home` 模式（可参考 `tests/test_ingest_ignore.py` 的实现方式）。

## 交付标准

1. `python3 -m compileall zcore tests` 通过
2. `python3 -m unittest discover tests -q` 全部通过（104 基线 + ≥ 7 新增）
3. `zcore harvest discover --source openclaw` 能列出本机真实 session 数量
4. 所有现有测试不受影响

## 技术约束

- 零外部依赖（json + pathlib，全部 stdlib）
- session 文件解析错误时静默跳过（不抛出异常）
- `~/.openclaw/agents/` 不存在时 `discover()` 返回空列表，`health_check()` 返回 `{"ok": False, "reason": "..."}`
- 不引入任何新的 config.toml 区块

## 执行协议 (delegated-sprint Step 2)

1. **Handshake**: 在编写任何代码前，先输出对任务的理解大纲和预估改动文件清单。
2. **Boundary**: 严禁修改 **Allowed Write Set** 之外的任何文件。
3. **Validation**: 完成后必须运行 `python3 -m unittest discover tests -q` 并提供 `code-review` 自审报告。
4. **Commit**: 使用 `feat(v3):` 前缀提交，消息包含测试通过数量。
