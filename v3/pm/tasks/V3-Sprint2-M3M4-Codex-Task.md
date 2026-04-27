# V3 Sprint 2: 隐私脱敏管线 + Session 全文搜索（M3 + M4）

## 目标

增强隐私脱敏能力，确保 Harvester 收割的数据在入库前完全脱敏。实现 Session 全文搜索，让用户通过关键词快速定位历史会话。

## 上下文

- **前置条件**：V3 Sprint 1（M1 + M2）准出标准已全部通过
- 分支 `v3/develop`
- M1 已交付：`zcore/engines/harvester.py`、`zcore/adapters/`、`zcore/models/harvester.py`
- 已有 `zcore/utils/privacy.py`：`redact_text()` 函数，支持 API key/token/secret/password + 文件路径脱敏
- 已有 `zcore/engines/session.py`：`SessionManager` 支持 `list()`, `get()`, `show_session()`
- 已有 `zcore/engines/memory.py`：`MemoryEngine` 支持 `search()`
- 已有共享测试 helper：`tests/helpers.py`
- **保持零外部依赖原则**

## 文件边界

### Allowed write set

- `zcore/utils/privacy.py` — 修改：新增 `sanitize_transcript()` + 扩展模式
- `zcore/engines/session.py` — 修改：新增 `search()` 方法
- `zcore/cli/main.py` — 修改：新增 `session search` 子命令
- `tests/test_privacy_enhanced.py` — 新建
- `tests/test_session_search.py` — 新建

### Shared files (mainline only)

- `zcore/cli/main.py` — 仅追加新的 subparser

### Protected surface (read-only unless task explicitly targets it)

- `zcore/engines/harvester.py` — 不得修改（M1 交付物）
- `zcore/adapters/` — 不得修改（M1 交付物）
- `zcore/engines/ghost_agent.py` — 不得修改（M2 交付物）
- `zcore/engines/context.py` — 不得修改
- `zcore/engines/memory.py` — 不得修改
- `zcore/engines/workflow.py` — 不得修改
- `zcore/config.py` — 不得修改
- `zcore/runtime.py` — 不得修改

## 回归保护基线

### Must preserve

- 所有 Sprint 1 交付的测试 + 62 个原有测试必须继续通过
- `redact_text()` 的已有行为不变（现有 3 个默认模式 + 文件路径脱敏）
- `SessionManager.list()`, `.get()`, `.show_session()` 行为不变
- `zcore harvest` 系列命令正常工作

### Forbidden regressions

- 不得修改 `redact_text()` 的默认模式列表（只能新增）
- 不得修改 `SessionMeta` 已有字段的语义
- 不得引入任何 `import` 失败

### Required checks

```bash
python3 -m compileall zcore tests
python3 -m unittest discover tests -q
zcore --version
zcore harvest status --json  # 确认 Sprint 1 交付物正常
```

## 执行方法论

### 执行 Agent 必须遵守的规则

1. **🔒 code-review 自审不可跳过**
2. **测试先行**
3. **回归保护**：`python3 -m unittest discover tests -q` 全部通过
4. **PM 文件同步**：编码完成后更新 `v3/pm/` 下的 PM 文件
5. **使用共享 helper**
6. **里程碑准出门禁**：M3 准出标准全部通过后才能开始 M4

## 任务详情

### M3: 隐私脱敏管线增强（2-3 天）

**前置条件**：Sprint 1 全部完成。

#### M3.1 扩展 `zcore/utils/privacy.py`

在现有 `redact_text()` 基础上新增 `sanitize_transcript()` 函数：

```python
# 新增脱敏模式（追加到 DEFAULT_PATTERNS，不修改已有的）
EXTENDED_PATTERNS = [
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",    # email
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",                  # IPv4
    r"ghp_[a-zA-Z0-9]{36}",                                       # GitHub PAT
    r"gho_[a-zA-Z0-9]{36}",                                       # GitHub OAuth
    r"glpat-[a-zA-Z0-9\-]{20,}",                                  # GitLab PAT
    r"Bearer\s+[A-Za-z0-9\-._~+/]+=*",                           # Bearer token
]

def sanitize_transcript(
    messages: list[dict[str, str]],
    *,
    extra_patterns: list[str] | None = None,
    redact_file_paths: bool = True,
) -> list[dict[str, str]]:
    """对完整会话记录进行脱敏处理。
    
    每条消息的 content 字段都会经过 redact_text() 处理。
    返回脱敏后的消息列表（原始列表不变）。
    """
```

#### M3.2 Ingest-Ignore 规则文件

支持 `~/.zcore/ingest-ignore` 文件，格式类似 `.gitignore`：

```
# 项目级别忽略
/home/user/projects/secret-project/
# 关键词忽略（包含这些关键词的会话不收割）
*password*
*credential*
```

Harvester 在收割前检查 ingest-ignore 规则：
- 在 `zcore/utils/privacy.py` 中新增 `load_ingest_ignore(paths)` 函数
- 返回 `{"ignored_paths": [...], "ignored_keywords": [...]}`
- Harvester 的 `ingest()` 在调用 adapter 之前检查此规则

#### M3.3 Session 级 private 标记

支持在 session 元数据中标记 `private: true`：
- 被标记为 private 的 session 不会被 Harvester 收割
- 不需要修改 `SessionMeta` dataclass（使用现有的 `metadata` dict 字段：`meta.metadata["private"] = True`）

#### M3 准出标准

- [ ] `sanitize_transcript()` 正确脱敏 email / IPv4 / GitHub PAT / Bearer token
- [ ] `redact_text()` 的现有 3 个默认模式行为不变
- [ ] `~/.zcore/ingest-ignore` 规则文件被正确加载和解析
- [ ] `private: true` 标记的 session 不被收割
- [ ] `tests/test_privacy_enhanced.py` ≥ 3 个测试全部通过
- [ ] 全量回归测试通过

---

### M4: Session 全文搜索（2-3 天）

**前置条件**：M3 准出标准全部通过。

#### M4.1 SessionManager.search()

在 `zcore/engines/session.py` 中新增 `search()` 方法：

```python
def search(
    self,
    query: str,
    *,
    limit: int = 20,
    source: str | None = None,     # 可选：只搜特定来源 (session / harvested)
) -> list[dict[str, object]]:
    """全文搜索会话内容。
    
    搜索范围：
    1. Session 元数据（project, agent, tags）
    2. Session 压缩摘要（~/.zcore/sessions/{id}/summary.md）
    3. Harvester 收割结果（~/.zcore/harvested/）
    
    返回: [{"session_id": str, "source": str, "score": float, "highlights": [str], "meta": {...}}]
    """
```

实现策略：
- 纯文本搜索（不需要向量/embedding），使用关键词匹配
- 支持多关键词（空格分隔，AND 语义）
- 匹配时提取上下文片段（前后 50 字符）作为 highlights
- 按匹配度排序（匹配关键词数 × 出现次数）
- 搜索文件使用 `pathlib.Path.rglob()` + 逐文件 `open/read`

#### M4.2 CLI 命令

在 `zcore/cli/main.py` 中新增 `session search` 子命令：

**`zcore session search --query <keywords> [--limit N] [--source session|harvested] [--json]`**

```
$ zcore session search --query "harvester adapter" --json
{
  "query": "harvester adapter",
  "results": [
    {
      "session_id": "s_20260427_abc",
      "source": "session",
      "score": 3.5,
      "highlights": ["...实现 Harvester adapter 框架..."],
      "project": "Z-Core",
      "started_at": "2026-04-27T14:00:00"
    }
  ],
  "total": 1
}
```

#### M4 准出标准

- [ ] `zcore session search --query "test" --json` 输出有效 JSON
- [ ] 多关键词 AND 搜索正确（"harvester adapter" 必须两个词都匹配）
- [ ] 搜索结果包含 highlights（上下文片段）
- [ ] 搜索结果按匹配度排序
- [ ] 1000 条会话搜索 < 2s（性能基线）
- [ ] `tests/test_session_search.py` ≥ 4 个测试全部通过
- [ ] 全量回归测试通过

## 交付标准

1. `python3 -m compileall zcore tests` 通过
2. `python3 -m unittest discover tests -q` 全部通过（Sprint 1 + ≥ 7 新增）
3. 冒烟验证：
   - `zcore --version` → `0.2.0`
   - `zcore harvest status --json` — Sprint 1 交付物正常
   - `zcore session search --query "test" --json` — 新功能
4. code-review 自审通过
5. 文件边界未越界
6. 回归保护基线全部通过

## 技术约束（必读）

- **零外部依赖**：不引入任何第三方库（搜索用纯 Python 实现）
- **Python ≥3.11**
- **脱敏不可逆**：`sanitize_transcript()` 产出的数据不可反向还原
- **搜索性能**：纯文本搜索，不引入 SQLite FTS 或 embedding
- **向下兼容**：`redact_text()` 现有默认模式不可修改，只可追加
- **使用共享 helper**：新测试 `from tests.helpers import run_zcore, TestHome`
