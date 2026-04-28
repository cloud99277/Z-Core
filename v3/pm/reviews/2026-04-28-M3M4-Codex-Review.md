# Code Review — V3 Sprint M3 + M4 (Codex Task4 + Task5)

> **审查日期**: 2026-04-28
> **审查者**: Antigravity (delegated-sprint Step 3)
> **审查范围**: Commit `731c5ae` (Task4) + `367fee9` (Task5) — 8 files, +647 lines
> **变更意图**: 完成 V3.0 MVP 剩余两个里程碑：隐私脱敏管线增强 (M3) + Session 全文搜索 (M4)
> **代码语言**: Python 3.11+, 零外部依赖

## 总评

两个任务均高质量完成，严格遵守了 Allowed Write Set 边界和 Protected Surface 约束。代码风格一致，测试覆盖充分（18 个新增用例），所有 101 tests 通过。**无 Blocking 问题。**

## 🔴 Blocking（0 个）

无。

## 🟡 Non-blocking（2 个）

### 1. IPv4 模式可能误伤版本号字符串
**位置**: `zcore/utils/privacy.py:14`
**当前**: `r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"` 会匹配 `Python 3.11.0` 或 `v2.0.0.1`
**建议**: 对于 MVP 可接受，但 V3.1 应考虑排除常见误伤场景（如后跟 `.d+` 的版本号）
**原因**: 目前脱敏场景以会话文本为主，版本号出现频率较低，风险可控

### 2. SearchEngine snippet 在极短文本时可能输出空 snippet
**位置**: `zcore/engines/search.py:147-154`
**当前**: `_snippet()` 在 `positions` 为空时 `first=0`，可能输出无意义的前 50 字符
**建议**: 当 `positions` 为空时返回 `""` 或 `"(no snippet)"`
**原因**: 只在理论边界条件下触发（match 发生在 `all(term in folded for term in terms)` 之后，`find` 不应找不到），实际风险极低

## 💬 Nit（2 个）

- [Nit] `zcore/utils/privacy.py:12` — `sk-` 模式从 `{20,}` 改为 `{18,}`，Task Spec 原始要求是保持 `{20,}`。差异无实际影响（18 也安全），但建议保持和 spec 一致
- [Nit] `tests/test_search.py` — `_paths()` helper 手动构造了完整的 `RuntimePaths`，可考虑提取到 `tests/helpers.py` 作为共享工具。但当前只有一个测试文件使用，可 defer

## 👍 亮点

- **边界严格合规**: 两个 Task 改动的文件完全匹配 Allowed Write Set，零越界
- **Protected Surface 零触碰**: session.py、memory.py、config.py 等全部未修改
- **Task4 `sanitize_transcript()`**: 使用 `deepcopy` 确保不可变性，测试中显式验证了 `assertIsNot` — 规范的防御性编程
- **Task4 `ingest-ignore` 集成**: Harvester 改动仅 +7 行，最小化侵入，完美遵循了最小破坏准则
- **Task5 SearchEngine**: 架构清晰（`_iter_native_sessions` / `_iter_harvested_sessions` / `_match_record` 三层分离），支持 gzip 上下文文件读取
- **Task5 AND 搜索**: `all(term in folded for term in terms)` 实现简洁正确
- **Task5 CLI 输出**: 同时支持人类可读和 `--json` 格式，CLI 标准符合项目约定
- **测试设计**: `test_search.py` 的 `_write_native` / `_write_harvested` helper 方法构造了完整的真实数据结构，测试了 gzip 上下文读取等深层路径

## 边界校验

```
Task4 (731c5ae) 实际改动:
  tests/test_ingest_ignore.py     ✅ in Allowed
  tests/test_privacy.py           ✅ in Allowed
  zcore/engines/harvester.py      ✅ in Allowed
  zcore/utils/privacy.py          ✅ in Allowed

Task5 (367fee9) 实际改动:
  tests/test_search.py            ✅ in Allowed
  zcore/cli/main.py               ✅ in Allowed
  zcore/engines/search.py         ✅ in Allowed
  zcore/models/search.py          ✅ in Allowed

Protected Surface diff: (empty) ✅ 零违规
```

## 测试覆盖

| 测试文件 | 用例数 | Spec 最低 | 覆盖场景 |
|----------|:------:|:---------:|---------|
| test_privacy.py | 8 | 5 | API key, IPv4, Email, 手机号, Bearer, 混合, transcript 批量, 不可变性 |
| test_ingest_ignore.py | 3 | 3 | 文件解析, glob 匹配, Harvester 集成 |
| test_search.py | 7 | 5 | 空数据, harvested 命中, native summary, context.gz, AND 搜索, CLI JSON, limit |
| **总计** | **18** | **13** | — |

## 契约校验

| 函数/类 | Spec 定义 | 实际实现 | 匹配？ |
|---------|-----------|---------|:-----:|
| `redact_text()` 签名不变 | `(text, patterns=None, redact_file_paths=True)` | ✅ | ✅ |
| `sanitize_transcript()` | `(messages, *, patterns=None, redact_file_paths=True) -> list` | ✅ | ✅ |
| `load_ingest_ignore()` | `(path: Path) -> list[str]` | ✅ | ✅ |
| `should_ignore()` | `(session_path: str, patterns: list[str]) -> bool` | ✅ | ✅ |
| `SearchHit` dataclass | 6 字段 + `to_dict()` | ✅ | ✅ |
| `SearchResult` dataclass | 6 字段 + `to_dict()` | ✅ | ✅ |
| `SearchEngine.search()` | `(query, *, source, project, limit) -> SearchResult` | ✅ | ✅ |
| CLI `session search` | `--query --source --project --limit --json` | ✅ | ✅ |

## 结论

**结论**: ✅ **LGTM** — 无阻塞性问题，2 个 Non-blocking 建议可 defer 到 V3.1。

V3.0 MVP 四个里程碑 (M1-M4) 全部完成。
