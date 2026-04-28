# Task 7: Codex Adapter (M6)

## 目标

实现 `zcore/adapters/codex_adapter.py`，让 Harvester 收割机支持从 `~/.codex/sessions/` 目录收割 Codex CLI 的所有对话数据。

## 上下文

- 分支 `v3/develop`，Task6 完成后执行（或与 Task6 并行，互不依赖）
- 代码基线：commit `ecd7d35`（已包含全量审查修复），当前 104 测试通过
- 已有 `zcore/adapters/base.py`：`SourceAdapter` ABC 接口
- 已有 `zcore/adapters/claude_adapter.py`：参考实现（JSONL 解析）
- 已有 `zcore/adapters/openclaw_adapter.py`：Task6 产出（类似 JSONL 事件流）
- 已有 `tests/helpers.py`：`run_zcore`, `TestHome`
- 零外部依赖

### Current-State 快照

- M1-M4 🟢 完成
- M5 OpenClaw Adapter 🟢 完成（Task6 前置）
- **M6 Codex Adapter ← 本任务**
- M7 Gemini Adapter（依赖格式探查）
- M8 SearchEngine FTS 索引化

### Codex 数据格式（已探明）

**目录结构**：
```
~/.codex/sessions/
  └── YYYY/
      └── MM/
          └── DD/
              └── rollout-<ISO8601>-<uuid>.jsonl   ← 换行分隔 JSON 事件流
```

示例路径：
`~/.codex/sessions/2026/04/03/rollout-2026-04-03T21-05-16-019d5372-a6f4-79e1-bda3-773a58baaaf9.jsonl`

**session 文件格式**（换行分隔 JSON）：

```json
{"timestamp":"2026-04-03T13:05:20.514Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"..."}}
{"timestamp":"2026-04-03T13:05:40.714Z","type":"event_msg","payload":{"type":"task_started","turn_id":"...","model_context_window":258400,...}}
{"timestamp":"2026-04-03T13:05:40.715Z","type":"turn_context","payload":{"turn_id":"...","cwd":"/mnt/c/Users/yangyy","current_date":"2026-04-03","model":"gpt-5.2-codex",...}}
{"timestamp":"2026-04-03T13:05:40.715Z","type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"开启openclaw"}]}}
{"timestamp":"...","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"text","text":"..."}]}}
{"timestamp":"...","type":"response_item","payload":{"type":"reasoning","summary":[{"type":"summary_text","text":"..."}],...}}
{"timestamp":"...","type":"event_msg","payload":{"type":"token_count","info":{...}}}
```

**关键字段**：
- `type == "response_item"` + `payload.type == "message"` → 需提取的对话行
- `payload.role` → `"user"` / `"assistant"`（只保留这两种）
- `payload.content` → list of blocks，提取 `type in ["text","input_text","output_text"]` 的 `text` 字段
- `type == "turn_context"` + `payload.cwd` → 项目路径（作为 `project` 字段）
- 文件名中的 ISO8601 时间戳 → `started_at`
- session UUID → `source_session_id`（文件名末尾的 UUID 部分）

**history.jsonl**（仅存用户输入摘要，不用于 ingest，仅用 sessions/ 目录）：
```json
{"session_id":"019ca86c-...","ts":1772352206,"text":"hi"}
```

## Allowed write set

- `zcore/adapters/codex_adapter.py` — 新建
- `zcore/adapters/__init__.py` — 修改（注册新 adapter）
- `zcore/engines/harvester.py` — 修改（默认注册 CodexAdapter）
- `tests/test_codex_adapter.py` — 新建

## Protected surface（不得修改）

- `zcore/adapters/base.py`、`claude_adapter.py`、`hermes_adapter.py`、`openclaw_adapter.py`
- `zcore/engines/session.py`、`memory.py`、`context.py`、`workflow.py`、`search.py`
- `zcore/config.py`、`zcore/runtime.py`
- `zcore/models/harvester.py`、`zcore/models/search.py`
- `zcore/utils/privacy.py`
- `tests/test_adapters.py`、`tests/test_harvester.py`、`tests/test_openclaw_adapter.py`

## 任务详情

### 1. 实现 `CodexAdapter`

```python
# zcore/adapters/codex_adapter.py
from __future__ import annotations

import json
import re
from pathlib import Path

from zcore.adapters.base import SourceAdapter
from zcore.models.harvester import HarvestedSession

# 从文件名提取 session_id 的正则
# rollout-2026-04-03T21-05-16-019d5372-a6f4-79e1-bda3-773a58baaaf9.jsonl
_FILENAME_RE = re.compile(
    r"rollout-(?P<ts>\d{4}-\d{2}-\d{2}T[\d-]+)-(?P<uuid>[0-9a-f-]{36})\.jsonl$"
)

class CodexAdapter(SourceAdapter):
    BASE_DIR = Path.home() / ".codex" / "sessions"

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or self.BASE_DIR

    def name(self) -> str:
        return "codex"

    def discover(self, project: str | None = None) -> list[dict[str, object]]:
        """遍历 YYYY/MM/DD/ 目录结构，返回 session 候选列表。"""
        ...

    def ingest(self, session_id: str) -> HarvestedSession | None:
        """加载 JSONL 事件流，提取 user/assistant 消息对。"""
        ...

    def health_check(self) -> dict[str, object]:
        ...
```

**discover() 实现要点**：
- 遍历 `~/.codex/sessions/**/*.jsonl`（glob 递归）
- 用 `_FILENAME_RE` 匹配文件名，提取 `ts`（时间戳）和 `uuid`（session ID）
- `session_id` = UUID 部分
- `started_at` = 文件名中的时间戳转为 ISO8601
- 返回列表元素**必须包含以下字段**（否则 HarvesterEngine 会打印 warning 并跳过）：
  - `source_session_id`：UUID 部分
  - `path`：完整文件路径字符串（ingest-ignore 规则匹配用）
  - `project`：从 `turn_context` 行读取的 `cwd`
  - `started_at`：文件名中的 ISO8601 时间戳

**ingest() 实现要点**：
- 通过 discover 返回的 `path` 字段定位文件
- 逐行解析，过滤 `type == "response_item"` + `payload.type == "message"`
- 只保留 `payload.role in ["user", "assistant"]`
- content 提取：遍历 `payload.content` list，取 `type in ["text","input_text","output_text"]` 的 `text`
- `project`：从同文件的 `turn_context` 行读取 `payload.cwd`，取最后一个路径组件；无则空字符串
- `ended_at`：最后一条消息的 timestamp

### 2. 注册到 HarvesterEngine

**必须修改 `harvester.py` 的 `_auto_register_known_adapters()` 方法**（不是只改 `__init__.py`）：

将以下元组追加到 `_auto_register_known_adapters` 内的 `for` 循环列表：

```python
# harvester.py: _auto_register_known_adapters() 中的元组，追加第四项
for module_name, class_name in (
    ("zcore.adapters.claude_adapter", "ClaudeAdapter"),
    ("zcore.adapters.hermes_adapter", "HermesAdapter"),
    ("zcore.adapters.openclaw_adapter", "OpenClawAdapter"),  # Task6 已加
    ("zcore.adapters.codex_adapter", "CodexAdapter"),          # ← 本任务追加
):
```

同时更新 `zcore/adapters/__init__.py` 导出 `CodexAdapter`：

```python
from zcore.adapters.codex_adapter import CodexAdapter
__all__ = ["ClaudeAdapter", "CodexAdapter", "HermesAdapter", "OpenClawAdapter", "SourceAdapter"]
```

### 3. 测试 `tests/test_codex_adapter.py`（≥ 5 用例）

使用 `tempfile.TemporaryDirectory` 构造 `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` 结构：

- `test_discover_finds_jsonl_files`：正确发现 YYYY/MM/DD 目录结构下的文件
- `test_discover_extracts_session_id_from_filename`：UUID 从文件名正确提取
- `test_ingest_extracts_user_assistant_only`：跳过 `reasoning`、`event_msg`、`token_count` 等噪声
- `test_ingest_extracts_cwd_as_project`：从 `turn_context` 行提取 `cwd` 作为项目
- `test_ingest_handles_missing_turn_context`：无 `turn_context` 时 project 降级为空字符串
- `test_health_check_ok_when_dir_exists`

**必须新增 ingest-ignore 集成测试**（通过 HarvesterEngine 验证）：

- `test_harvester_skips_codex_session_matching_ingest_ignore`：
  通过 `HarvesterEngine` 的 `ingest()` 方法，验证命中 glob 规则的 Codex session 被计入 `skipped` 而不是 `ingested`。
  使用 `_isolated_home` 模式（可参考 `tests/test_ingest_ignore.py`）。

## 交付标准

1. `python3 -m compileall zcore tests` 通过
2. `python3 -m unittest discover tests -q` 全部通过（Task6 基线 + ≥ 6 新增）
3. `zcore harvest discover --source codex` 能列出本机真实 session 数量
4. 所有现有测试不受影响

## 技术约束

- 零外部依赖（json + re + pathlib，全部 stdlib）
- JSONL 行解析错误时静默跳过（`try/except json.JSONDecodeError`）
- `~/.codex/sessions/` 不存在时 `discover()` 返回空列表
- 不引入任何新的 config.toml 区块
- 文件名正则无法匹配时跳过该文件（不报错）

## 执行协议 (delegated-sprint Step 2)

1. **Handshake**: 在编写任何代码前，先输出对任务的理解大纲和预估改动文件清单。
2. **Boundary**: 严禁修改 **Allowed Write Set** 之外的任何文件。
3. **Validation**: 完成后必须运行 `python3 -m unittest discover tests -q` 并提供 `code-review` 自审报告。
4. **Commit**: 使用 `feat(v3):` 前缀提交，消息包含测试通过数量。
