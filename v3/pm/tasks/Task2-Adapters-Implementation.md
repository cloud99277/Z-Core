# Task 2: Claude + Hermes Adapter 实现

## 目标

基于 Task0 探查到的真实数据格式，实现 Claude Code 和 Hermes 的 SourceAdapter。

## 前置条件

Task 1（Harvester 骨架）已完成。`SourceAdapter` ABC、`HarvestedSession` dataclass、`HarvesterEngine` 已存在。

## 上下文

- 分支 `v3/develop`，Task 1 已合并
- **已有** `zcore/adapters/base.py`（SourceAdapter ABC）
- **已有** `zcore/models/harvester.py`（HarvestedSession, HarvestResult）
- **已有** `zcore/engines/harvester.py`（HarvesterEngine，支持 register_adapter）
- 数据格式详见 `v3/pm/tasks/Task0-DataFormat-Report.md`

## Allowed write set

- `zcore/adapters/claude_adapter.py` — 新建
- `zcore/adapters/hermes_adapter.py` — 新建
- `zcore/adapters/__init__.py` — 修改：导出新 adapter
- `zcore/engines/harvester.py` — 修改：自动注册 claude/hermes adapter
- `tests/test_adapters.py` — 新建

## Protected surface

- `zcore/adapters/base.py` — 不得修改
- `zcore/models/harvester.py` — 不得修改
- `zcore/engines/` 下除 harvester.py 外的所有文件

## Claude Adapter 实现要求

### 数据源位置

```
~/.claude/projects/{path-with-dashes}/{session-uuid}.jsonl
```

路径名将 `/` 替换为 `-`，例如 `/home/yangyy/projects` → `-home-yangyy-projects`。

### 解析逻辑

每个 `.jsonl` 文件包含一个完整会话，每行一条 JSON：

```json
{"type": "user", "message": {"role": "user", "content": "文本"}, "sessionId": "uuid", "cwd": "/path", "timestamp": "ISO8601", "uuid": "msg-uuid"}
```

- **只提取** `type == "user"` 或 `type == "assistant"` 的行
- 忽略 `progress`、`system`、`file-history-snapshot` 类型
- `message.content` 是消息文本
- `cwd` 映射为 `project`
- `sessionId` 映射为 `source_session_id`
- 取所有消息中最早的 `timestamp` 作为 `started_at`

### health_check

检查 `~/.claude/projects/` 目录是否存在。

### discover

扫描 `~/.claude/projects/` 下所有 `*.jsonl` 文件，返回 session 列表。

### 容错

- 目录不存在 → 返回空列表，不 crash
- JSONL 某行解析失败 → 跳过该行，记入 errors，继续

---

## Hermes Adapter 实现要求

### 数据源位置

```
~/.hermes/sessions/session_{timestamp}_{hash}.json
```

### 解析逻辑

每个 `session_*.json` 是一个完整 JSON 对象：

```json
{
  "session_id": "20260413_234516_512af7",
  "model": "model-name",
  "platform": "cli | telegram",
  "session_start": "ISO8601",
  "last_updated": "ISO8601",
  "message_count": 2,
  "messages": [
    {"role": "user", "content": "文本"},
    {"role": "assistant", "content": "回复"}
  ]
}
```

- `messages` 数组直接映射到 `HarvestedSession.messages`
- `session_id` 映射为 `source_session_id`
- `session_start` 映射为 `started_at`
- `model` 和 `platform` 存入 `metadata`
- 忽略 `request_dump_*.json` 和 `*.jsonl` 文件（只处理 `session_*.json`）

### health_check

检查 `~/.hermes/sessions/` 目录是否存在。

### discover

扫描 `~/.hermes/sessions/session_*.json` 文件，返回 session 列表。

### 容错

- 目录不存在 → 返回空列表
- JSON 解析失败 → 跳过该文件，记入 errors

---

## 测试 `tests/test_adapters.py`（≥ 5 用例）

使用 `TestHome` 创建临时目录，在其中伪造 Claude/Hermes 格式的测试数据：

- Claude adapter: discover 空目录 → 空列表
- Claude adapter: discover + ingest 一个伪造的 JSONL 会话
- Claude adapter: 跳过 progress/system 类型的行
- Hermes adapter: discover 空目录 → 空列表
- Hermes adapter: discover + ingest 一个伪造的 session JSON
- Hermes adapter: 忽略 request_dump 文件

## 交付标准

1. `python3 -m compileall zcore tests` 通过
2. `python3 -m unittest discover tests -q` 全部通过
3. `zcore harvest discover --json` 输出发现的会话（如有 Claude/Hermes 数据）
4. `zcore harvest status --json` 显示两个 adapter 的健康状态
5. code-review 自审通过

## 技术约束

- 零外部依赖（json + pathlib + glob，全部 stdlib）
- 不使用 sqlite3 读 state.db（直接读 session JSON 更简单可靠）
- 所有收割内容经过 `redact_text()` 脱敏后再存储
- 解析失败时返回结构化错误，绝不 crash
