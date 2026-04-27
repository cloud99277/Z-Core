# Task0 探查报告：Claude Code + Hermes 日志格式

> **探查时间**：2026-04-27 22:27
> **探查者**：Antigravity
> **结论**：两个数据源均为 JSON/JSONL 格式，结构清晰，可用 stdlib 解析

---

## Claude Code 数据格式

### 目录结构

```
~/.claude/
├── history.jsonl              ← 用户命令历史（轻量，不含 AI 回复）
├── sessions/                  ← Session 元数据
│   └── {pid}.json             ← {"pid", "sessionId", "cwd", "startedAt", "kind", "entrypoint"}
└── projects/                  ← 按项目目录分类的完整会话
    ├── -home-yangyy-projects/ ← 路径用 `-` 替代 `/`
    │   ├── {uuid}.jsonl       ← 完整会话记录（JSONL，每行一条消息）
    │   └── {uuid}/            ← 某些会话用目录而非单文件
    ├── -home-yangyy/
    └── ...
```

### 消息格式（JSONL，每行一条）

```json
{
  "parentUuid": "uuid-of-parent",
  "isSidechain": false,
  "userType": "external",
  "cwd": "/home/yangyy/projects",
  "sessionId": "1fbbf4ad-...",
  "version": "2.1.63",
  "gitBranch": "HEAD",
  "type": "user | assistant | system | progress | file-history-snapshot",
  "message": {
    "role": "user | assistant",
    "content": "消息文本"
  },
  "uuid": "unique-id",
  "timestamp": "2026-03-23T15:57:03.500Z"
}
```

### 关键字段

| 字段 | 含义 | 用于收割 |
|------|------|---------|
| `type` | 消息类型 | ✅ 只取 `user` 和 `assistant` |
| `message.role` | 角色 | ✅ 映射到 HarvestedSession.messages |
| `message.content` | 文本内容 | ✅ 核心数据 |
| `sessionId` | 会话 ID | ✅ 用于去重 |
| `cwd` | 工作目录 | ✅ 映射到 project |
| `timestamp` | ISO 8601 | ✅ 用于排序和时间过滤 |

### 所有 type 值

`assistant`, `file-history-snapshot`, `progress`, `system`, `user`

---

## Hermes 数据格式

### 目录结构

```
~/.hermes/
├── sessions/
│   ├── sessions.json                              ← 活跃会话索引
│   ├── session_{timestamp}_{hash}.json             ← 完整会话（JSON，含 messages 数组）
│   ├── {timestamp}_{hash}.jsonl                    ← 流式日志（增量追加）
│   └── request_dump_{...}.json                     ← API 请求转储（可忽略）
├── state.db                                        ← SQLite 主状态数据库（6.3MB）
├── memories/                                       ← 记忆存储
└── checkpoints/                                    ← 会话检查点
```

### Session JSON 格式

```json
{
  "session_id": "20260413_234516_512af7",
  "model": "xiaomi/mimo-v2-pro",
  "base_url": "https://inference-api.nousresearch.com/v1",
  "platform": "cli | telegram",
  "session_start": "2026-04-13T23:45:16.879240",
  "last_updated": "2026-04-13T23:45:22.402924",
  "system_prompt": "You are Hermes Agent...",
  "tools": [],
  "message_count": 2,
  "messages": [
    {"role": "user", "content": "用户消息"},
    {"role": "assistant", "content": "AI回复"}
  ]
}
```

### sessions.json（活跃会话索引）

```json
{
  "agent:main:telegram:dm:7699757820": {
    "session_key": "agent:main:telegram:dm:7699757820",
    "session_id": "20260413_112841_508dace4",
    "created_at": "2026-04-13T11:28:41",
    "platform": "telegram",
    "chat_type": "dm",
    "display_name": "cloud young"
  }
}
```

### 关键字段

| 字段 | 含义 | 用于收割 |
|------|------|---------|
| `session_id` | 会话 ID | ✅ 用于去重 |
| `messages[].role` | user/assistant | ✅ 直接映射 |
| `messages[].content` | 文本内容 | ✅ 核心数据 |
| `session_start` | 开始时间 | ✅ |
| `last_updated` | 最后更新 | ✅ |
| `model` | 使用的模型 | ✅ metadata |
| `platform` | cli/telegram | ✅ 过滤条件 |

### 数据量

- 约 80 个 session JSON 文件（每个 200KB-700KB）
- 6 个 JSONL 流式日志文件
- 总计约 25MB

---

## 对比总结

| 维度 | Claude Code | Hermes |
|------|------------|--------|
| 格式 | JSONL（每行一条消息） | JSON（整个会话一个文件） |
| 路径 | `~/.claude/projects/{path}/{uuid}.jsonl` | `~/.hermes/sessions/session_{id}.json` |
| 消息结构 | `{type, message: {role, content}}` | `{messages: [{role, content}]}` |
| 过滤 | `type == "user" \| "assistant"` | 直接取 `messages` 数组 |
| 会话索引 | `sessions/{pid}.json` | `sessions/sessions.json` |
| 复杂度 | 中（需过滤 progress/system/file-history） | **低**（直接读 messages） |
| sqlite3 | 不需要 | `state.db` 可选（主要用 JSON） |
