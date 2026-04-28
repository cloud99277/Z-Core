# Task 5: Session 全文搜索 (M4)

## 目标

实现 `zcore session search` CLI 命令，支持对 Z-Core 原生 Session + Harvester 收割会话进行全文搜索。

## 上下文

- 分支 `v3/develop`，Task 4 已完成
- 已有 `zcore/engines/session.py`：`SessionEngine`（管理 `~/.zcore/sessions/` 下的原生会话）
- 已有 `zcore/engines/harvester.py`：`HarvesterEngine`（管理 `~/.zcore/harvested/` 下的收割会话）
- 已有 `zcore/models/session.py`：`SessionMeta` dataclass
- 已有 `zcore/models/harvester.py`：`HarvestedSession` dataclass
- 会话数据以 JSON 文件存储，无数据库
- CLI 使用 argparse，`zcore/cli/main.py`
- 零外部依赖

### Current-State 快照

- M1 Harvester 收割机 🟢 完成
- M2 GhostAgent 角色切换 🟢 完成
- M3 隐私脱敏管线 🟢 完成（前置依赖，Task4）
- **M4 Session 全文搜索 ← 本任务**

## Allowed write set

- `zcore/engines/search.py` — 新建
- `zcore/models/search.py` — 新建
- `zcore/cli/main.py` — 修改：新增 `session search` 子命令
- `tests/test_search.py` — 新建

## Protected surface（不得修改）

- `zcore/engines/session.py`、`memory.py`、`context.py`、`workflow.py`
- `zcore/engines/harvester.py`
- `zcore/config.py`、`zcore/runtime.py`
- `zcore/models/harvester.py`、`zcore/models/session.py`

## 任务详情

### 1. 数据模型 `zcore/models/search.py`

```python
@dataclass
class SearchHit:
    source: str                     # "session" | "harvested"
    session_id: str
    project: str
    started_at: str
    snippet: str                    # 匹配行的上下文片段（前后各 50 字符）
    score: float = 1.0              # 匹配度评分

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

@dataclass
class SearchResult:
    query: str
    total_hits: int
    hits: list[SearchHit] = field(default_factory=list)
    searched_sessions: int = 0
    searched_harvested: int = 0
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
```

### 2. SearchEngine `zcore/engines/search.py`

```python
class SearchEngine:
    def __init__(self, paths: RuntimePaths | None = None):
        self.paths = paths or RuntimePaths.discover()

    def search(
        self,
        query: str,
        *,
        source: str | None = None,    # "session" | "harvested" | None (both)
        project: str | None = None,
        limit: int = 50,
    ) -> SearchResult:
        """全文搜索 session 和 harvested 会话。"""
```

**搜索逻辑**：

1. **搜索范围**：
   - 原生 Session：`~/.zcore/sessions/{id}/meta.json` 中的 `summary` 字段 + `context.json.gz` 中的消息内容（如存在）
   - 收割会话：`~/.zcore/harvested/{source}/{id}.json` 中的 `messages[].content` + `summary`
2. **关键词解析**：
   - 空格分隔的多个词用 AND 逻辑（所有词必须出现在同一消息或摘要中）
   - 大小写不敏感
3. **匹配输出**：
   - 找到匹配后生成 snippet：匹配词前后各取 50 字符
   - 按 `started_at` 倒序排列（最新的在前）
   - 限制返回 `limit` 条
4. **性能约束**：
   - 纯文件扫描，不建索引
   - 1000 条会话搜索应 < 2s（单线程遍历 JSON 文件）

### 3. CLI 命令

新增 `session search` 子命令（挂载在已有的 `session` 子命令下）：

```
zcore session search --query <keyword> [--source session|harvested] [--project <name>] [--limit 50] [--json]
```

**人类可读输出**：

```
Found 3 results for "harvester adapter" (searched 42 sessions, 89 harvested in 320ms)

[harvested] claude:abc123  /home/yangyy/projects  2026-04-27
  ...实现了 harvester adapter 的基础框架...

[session]   s_20260427_001  Z-Core  2026-04-27
  ...讨论了 adapter 接口设计...
```

**JSON 输出**：`SearchResult.to_dict()` 的 JSON 序列化

### 4. 测试 `tests/test_search.py`（≥ 5 用例）

使用 `TestHome` 或 `tempfile.TemporaryDirectory` 创建隔离环境，伪造搜索数据：

- 搜索空数据 → 0 hits
- 搜索 harvested session → 命中
- 搜索 native session meta.summary → 命中
- 多关键词 AND 搜索 → 仅当全部词匹配才命中
- `zcore session search --query <x> --json` 输出有效 JSON
- `--limit` 参数限制结果数量

## 交付标准

1. `python3 -m compileall zcore tests` 通过
2. `python3 -m unittest discover tests -q` 全部通过
3. `zcore session search --query "test" --json` 输出有效 JSON
4. 所有现有测试不受影响

## 技术约束

- 零外部依赖（json + pathlib + re + time，全部 stdlib）
- 不修改 SessionEngine 或 HarvesterEngine（只读消费它们的文件）
- 搜索是只读操作，不写入任何文件
- 不建索引文件（MVP 直接扫描，V3.1 可考虑 sqlite-fts5）
- 使用 `from tests.helpers import run_zcore, TestHome`

## 执行协议 (delegated-sprint Step 2)

1. **Handshake**: 在编写任何代码前，先输出对任务的理解大纲和预估改动文件清单。
2. **Boundary**: 严禁修改 **Allowed Write Set** 之外的任何文件。
3. **Validation**: 完成后必须运行 `python3 -m unittest discover tests -q` 并提供 `code-review` 自审报告。
4. **Commit**: 使用 `feat(v3):` 前缀提交，消息包含测试通过数量。
