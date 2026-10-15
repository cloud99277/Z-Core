# Z-Core V3 全量架构审查 — 2026-04-29

> **审查视角**: 顶级系统架构师（破坏性视角）
> **审查范围**: V3.0 全部已交付代码（M1-M4）+ V3.1 规划文档（M5-M8）
> **审查日期**: 2026-04-29
> **代码基线**: commit `ecd7d35`，101 tests pass / 0 fail / 1 skip
> **方法**: 代码直读 + 实机 CLI 验证 + 测试矩阵对比 + 架构一致性校验

## 总评

**方向正确率：8.5/10**

V3.0 MVP 架构设计清晰，模块职责分离，零外部依赖坚守得很好。测试覆盖新开发模块，核心流程验收逻辑可靠。但在 **安全性**（index 幂等性）、**可观测性**（harvested session 无时间戳索引）、**接口契约**（discover 返回结构未严格校验）等方面存在若干系统性盲点，且 V3.1 的 Task Spec 有一处规格遗漏可能导致 Codex 实现偏差。

**最大风险**：Harvester index 目前无法防止跨会话 ID 冲突（source:id 合并键设计正确，但 `_safe_filename` 可能将不同 session 映射到同一文件名）。

---

## 🔴 结构性问题（2 个）

### 问题 1：`_safe_filename` 哈希冲突导致静默数据覆盖

**位置**: `zcore/engines/harvester.py:183`

```python
def _safe_filename(self, value: str) -\u003e str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value).strip("._") or "session"
```

**诊断**: `source_session_id` 中的 `/`、`:` 等特殊字符均被替换为 `_`。
例如 OpenClaw 的 session_id 格式为 `main/abc-123-def`，将被映射为 `main_abc-123-def.json`；Codex 的 UUID `019d5372-a6f4-79e1-bda3-773a58baaaf9` 则正常。
但若未来 session_id 为 `main/abc` 和 `main_abc`，两者将映射到同一文件名 `main_abc.json`，**后者静默覆盖前者**。

**后果**: 数据静默丢失，且无任何错误日志，难以察觉。

**建议**: 在文件名中加入 session_id 的哈希后缀防冲突，或改用 `hashlib.sha256(session_id.encode()).hexdigest()[:16]` 作为文件名（完全消除冲突），同时在 index 中保留原始 session_id 作为查找键。

---

### 问题 2：`discover()` 返回结构无 Schema 校验，导致 ingest 静默跳过

**位置**: `zcore/engines/harvester.py:53-62`

```python
session_id = str(
    item.get("source_session_id")
    or item.get("session_id")
    or item.get("id")
    or ""
)
if not session_id:
    result.skipped += 1
    result.errors.append("missing session id")
    continue
```

**诊断**: `discover()` 返回的 dict 结构没有任何 Schema 约束，如果 adapter 的 `discover()` 返回了缺少 `source_session_id` 字段的 dict（新 adapter 作者遗漏），会被静默跳过并计入 `errors` 列表，但 `totals["errors"]` 在 CLI 输出中不显示。这意味着 Codex 实现 Task6/Task7 时，如果 discover 返回结构有误，用户看到的只是 `ingested: 0`，没有任何错误提示。

**后果**: 新 adapter 的集成 Bug 极难调试。

**建议**:
1. 在 `SourceAdapter.discover()` 的文档中明确定义必须包含 `source_session_id` 和 `path` 字段的 Schema
2. CLI `harvest discover --json` 输出中包含 `errors` 字段
3. 或引入简单的 `_validate_discover_item(item)` 检查器，发现缺字段时打印 warning 而不是静默跳过

---

## 🟡 设计盲点（5 个）

### 盲点 1：Harvested session 存储无时间范围索引，ingest 重复性检查依赖 index.json 全量加载

**位置**: `harvester.py:133-140`

当 `~/.zcore/harvested/index.json` 增长到数千条时（3 个 Adapter × 数百 session），每次 `ingest()` 都需要全量读入 index.json 到内存。目前 MVP 规模可接受，但 M8 sqlite-fts5 计划中应考虑同步将 index 也迁移到 SQLite，避免 V3.1 完成后出现性能拐点。

**建议**: 在 Task8 规格中明确将 `index.json` 迁移到 SQLite `harvested_index` 表。

---

### 盲点 2：`SearchEngine._match_record()` 每条文本只匹配一次即返回，忽略了同一 session 的多条 snippet

**位置**: `search.py:136-146`

```python
for text in texts:
    folded = text.casefold()
    if all(term in folded for term in terms):
        return SearchHit(...)  # ← 第一条 text 命中就返回，不继续搜索
```

**诊断**: 如果第一条命中的 text 是空 summary，snippet 会输出空字符串；更好的命中 snippet 在后续 messages 里但被跳过了。

**建议**: 改为"收集所有命中 text，选 snippet 最丰富的一条"，或至少在 summary 为空时继续搜索 messages。

---

### 盲点 3：`privacy.py` 的 `redact_file_paths` 只处理 `/home/` 和 `/Users/`，遗漏 Windows 路径和 WSL 路径

**位置**: `privacy.py:26-28`

```python
result = re.sub(r"/home/([^/\s]+)/", "/home/[USER]/", result)
result = re.sub(r"/Users/([^/\s]+)/", "/Users/[USER]/", result)
```

**诊断**: Codex 的 `turn_context` 中 `cwd` 是 `/mnt/c/Users/yangyy`，其中的 `yangyy` 不会被脱敏（因为路径格式不是 `/home/` 或 `/Users/`，而是 `/mnt/c/Users/`）。OpenClaw session 也有同样风险。

**建议**: 增加 `/mnt/[a-z]/Users/([^/\s]+)/` 和 `\\Users\\([^\\s]+)\\` 两条规则。这是 V3.1 Adapter 上线后的真实泄露风险。

---

### 盲点 4：`HarvesterEngine._auto_register_known_adapters()` 使用 importlib 动态加载，Task6/Task7 新 Adapter 未被自动包含

**位置**: `harvester.py:108-118`

```python
for module_name, class_name in (
    ("zcore.adapters.claude_adapter", "ClaudeAdapter"),
    ("zcore.adapters.hermes_adapter", "HermesAdapter"),
):
```

**诊断**: 这是一个硬编码列表。Task6 完成后，`OpenClawAdapter` 需要手动追加到这个元组里。Task7 规格文件里确实提到了"注册到 HarvesterEngine"，但实现细节是追加到这个硬编码列表还是修改 `__init__.py` 并不明确，**Codex 很可能两个地方都改或者只改一个**，导致行为不一致。

**建议**: 在 Task6/Task7 规格文件中明确指出"修改 `harvester.py` 的 `_auto_register_known_adapters` 中的元组，追加 `('zcore.adapters.openclaw_adapter', 'OpenClawAdapter')`"，而不是依赖 Codex 自行判断。

---

### 盲点 5：`ingest-ignore` 的 `session_path` 对比依赖 adapter 返回的 `path` 字段，但 path 字段不强制要求存在

**位置**: `harvester.py:49-51`

```python
session_path = str(item.get("path") or "")
if session_path and should_ignore(session_path, ignore_patterns):
```

**诊断**: 如果新 Adapter 的 `discover()` 没有返回 `path` 字段（如 Gemini Adapter 可能以 project 名为 key 而非文件路径），`ingest-ignore` 规则将完全失效，且无任何提示。

**建议**: 在 `SourceAdapter.discover()` 的文档/注释中明确 `path` 字段为**推荐必填**，并在 Task6/Task7 规格文件中明确要求 discover 返回包含 `path` 字段。

---

## 🟢 优化建议（4 个）

### 建议 1：CLI `harvest ingest` 缺少 `--dry-run` 标志的用户提示

`ingest()` 方法支持 `dry_run=True`，但 CLI 中 `zcore harvest ingest --dry-run` 的输出和实际 ingest 的输出格式完全相同，用户无法直观区分是否真的写入了数据。建议在 dry_run 时在输出首行打印 `[DRY RUN] 以下数据不会被写入`。

---

### 建议 2：Task6 规格文件缺少对 `ingest-ignore` 的测试要求

Task4（M3）实现了 `ingest-ignore`，Task6 的 OpenClaw Adapter 将被 `HarvesterEngine` 集成，但 Task6 规格文件没有要求验证 OpenClaw session 也遵守 `ingest-ignore` 规则。建议在 `test_openclaw_adapter.py` 中补充一个"通过 HarvesterEngine 触发 ingest 时，命中 ingest-ignore 的 OpenClaw session 被跳过"的测试。

---

### 建议 3：`hermes_adapter.py` 中 `ended_at` 字段未被填充

从 Hermes JSON 格式可推断 `ended_at` 可以从最后一条消息的时间戳提取，但目前留空（`None`）。这导致 SearchEngine 排序时 `ended_at` 为 None 的 session 全部归在末尾。M5/M6 实现时应保持一致（都填或都不填）。

---

### 建议 4：`v3/pm/Sprint-Backlog.md`（V3.0）和 `v3/pm/Sprint-Backlog-V3.1.md` 并存，命名语义冲突

当前 PM 目录有两个 Sprint Backlog 文件：
- `Sprint-Backlog.md`（V3.0，已完成）
- `Sprint-Backlog-V3.1.md`（进行中）

建议将 V3.0 的重命名为 `Sprint-Backlog-V3.0.md` 以消除歧义；或在文件头部加上明确的 `archived: true` 标记。

---

## 修改建议汇总表

| # | 类型 | 建议 | 影响范围 | 优先级 |
|---|------|------|---------|:------:|
| 1 | 🔴 | `_safe_filename` 改用 sha256 后缀防冲突 | `harvester.py` | V3.1 前修复 |
| 2 | 🔴 | `discover()` 返回结构缺字段时打 warning 而非静默跳过 | `harvester.py` + CLI | V3.1 前修复 |
| 3 | 🟡 | `privacy.py` 补充 WSL/Windows 路径脱敏规则 | `privacy.py` + `test_privacy.py` | M5 前修复 |
| 4 | 🟡 | Task6/Task7 规格文件补充 `_auto_register_known_adapters` 修改点 | `Task6/Task7 spec` | 立即更新 |
| 5 | 🟡 | `ingest-ignore` 要求 `path` 字段为推荐必填 | `base.py` 注释 + Task6/7 spec | 立即更新 |
| 6 | 🟡 | `SearchEngine._match_record` 改为选最优 snippet | `search.py` | V3.1 |
| 7 | 🟡 | M8 Task 规格中将 `index.json` 同步迁移到 SQLite | `Task8 spec（待生成）` | Task8 规格时处理 |
| 8 | 🟢 | CLI `--dry-run` 首行打印提示 | `cli/main.py` | 低优先级 |
| 9 | 🟢 | Task6 补充 `ingest-ignore` 集成测试要求 | `Task6 spec` | 立即更新 |
| 10 | 🟢 | `Sprint-Backlog.md` 重命名为 `Sprint-Backlog-V3.0.md` | PM 文件 | 低优先级 |

---

## 专项：V3.1 Task Spec 完整性校验

| Task Spec | Handshake 要求 | Boundary 清晰 | Format 已知 | ingest-ignore 集成测试 | _auto_register 明确 |
|-----------|:-------------:|:------------:|:-----------:|:--------------------:|:-------------------:|
| Task6 (OpenClaw) | ✅ | ✅ | ✅ | ❌ 缺失 | ❌ 不明确 |
| Task7 (Codex) | ✅ | ✅ | ✅ | ❌ 缺失 | ❌ 不明确 |
| Task8 (FTS) | — (未生成) | — | — | — | — |

---

## 亮点（值得保留的好设计）

- `HarvesterEngine.ingest()` 对 adapter 失败的容错包装（`try/except`）设计干净
- `ClaudeAdapter._extract_content_text()` 处理 str/list 双模式是正确的防御性编程
- `SearchEngine` 的 OR-by-text / AND-by-term 架构简洁高效
- `sanitize_transcript()` 的 `deepcopy` 不可变性设计值得所有新 Adapter 学习
- `_auto_register_known_adapters()` 的 `importlib + try/except` 设计使得 Adapter 缺失时不崩溃

---

## 结论

**审查结论：条件通过（Conditional LGTM）**

存在 2 个 🔴 结构性问题，建议 **V3.1 第一批任务中同步修复**（可由 Codex 在 Task6 之前或 Antigravity 直接处理）。5 个 🟡 盲点中，**第 3、4、5 项需要在 Task6/Task7 执行前处理**，否则新 Adapter 可能引入隐性问题。

**建议处理顺序**：
1. 立即修复 🔴1（`_safe_filename`）和 🟡3（WSL 路径脱敏），影响所有 Adapter
2. 立即更新 Task6/Task7 规格文件（🟡4、🟡5），防止 Codex 实现偏差
3. 再派发 Task6/Task7 给 Codex
