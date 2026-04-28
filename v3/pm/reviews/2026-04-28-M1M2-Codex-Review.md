# Codex 任务审查报告：V3 Sprint 1 (M1 + M2)

> **审查时间**: 2026-04-28
> **审查者**: Antigravity
> **审查范围**: Commit `25c7645` — `feat(v3): add harvester and ghost roles`
> **分支**: `v3/develop`
> **总变更**: 11 files, +1126 / -40 lines
> **修复提交**: `4fc0656` (ISSUE-1) + 后续提交 (ISSUE-2, ISSUE-3)

---

## 审查总结

| 维度 | 评级 | 说明 |
|------|:----:|------|
| **Task0 探查报告** | ✅ PASS | 格式规范，Claude/Hermes 双源分析完整 |
| **Task1 骨架** | ✅ PASS | 数据模型、ABC、Engine、CLI 全部就位 |
| **Task2 Adapter 实现** | ✅ PASS | 功能正确，3 个 Issue 均已修复 |
| **Task3 GhostAgent 角色切换** | ✅ PASS | 向下兼容，角色路由 + fallback 链完备 |
| **保护面合规** | ✅ PASS | 零违规 |
| **测试质量** | ✅ PASS | 21 新增用例全部通过 (83 total, 0 fail, 1 skip) |
| **编译检查** | ✅ PASS | `compileall` 零错误 |

### 综合裁定：**PASS** — 所有 Issue 已修复

---

## 一、逐任务详审

### Task0: 数据格式探查报告

**文件**: `v3/pm/tasks/Task0-DataFormat-Report.md`

| 检查项 | 结果 |
|--------|:----:|
| Claude JSONL 格式分析 | ✅ |
| Hermes JSON 格式分析 | ✅ |
| `type` 枚举值完整列出 | ✅ |
| 对比总结表格 | ✅ |
| 数据量估算 | ✅ |

报告质量优秀。识别出了 Claude 的 `file-history-snapshot` 类型和 Hermes 的 `request_dump_*.json` 需忽略的细节。

---

### Task1: Harvester 骨架

**涉及文件**: `zcore/models/harvester.py`, `zcore/adapters/base.py`, `zcore/engines/harvester.py`, `zcore/cli/main.py`, `tests/test_harvester.py`

| 检查项 | Spec 要求 | 实际 | 结果 |
|--------|-----------|------|:----:|
| `HarvestedSession` dataclass | 8 字段 | 8 字段 + `to_dict()` 方法 | ✅ |
| `HarvestResult` dataclass | 5 字段 | 5 字段 + `to_dict()` 方法 | ✅ |
| `SourceAdapter` ABC | 4 抽象方法 | 4 抽象方法 + docstrings | ✅ |
| `HarvesterEngine` 初始化 | adapter 自动注册，失败不 crash | `_auto_register_known_adapters()` 静默 | ✅ |
| 存储路径 `~/.zcore/harvested/{source}/{id}.json` | 按源分目录 | ✅ | ✅ |
| 去重 index `~/.zcore/harvested/index.json` | 有 | ✅ | ✅ |
| `redact_text()` 脱敏 | ingest 时调用 | `_redact_session()` 完整实现 | ✅ |
| CLI 三命令 | discover / ingest / status | 全部挂载 + `--json` | ✅ |
| 测试 ≥5 用例 | 5+ | 7 用例 | ✅ |

**额外加分**: Engine 实现了 `_redact_metadata()` 递归脱敏（dict/list/str），比 spec 要求更完善。

---

### Task2: Adapter 实现

**涉及文件**: `zcore/adapters/claude_adapter.py`, `zcore/adapters/hermes_adapter.py`, `zcore/adapters/__init__.py`, `tests/test_adapters.py`

| 检查项 | Spec 要求 | 实际 | 结果 |
|--------|-----------|------|:----:|
| Claude: 解析 JSONL | 只取 user/assistant | 正确过滤 | ✅ |
| Claude: sessionId → source_session_id | 映射 | ✅ | ✅ |
| Claude: list 类型 content | 支持 tool_use blocks | ✅ 已修复 (ISSUE-2) | ✅ |
| Hermes: 解析 session_*.json | messages 直接映射 | ✅ | ✅ |
| Hermes: project 字段 | 语义正确 | ✅ 已修复 (ISSUE-1) | ✅ |
| Hermes: model/platform → metadata | 存入 | ✅ | ✅ |
| 容错 | 目录不存在/JSON 解析失败 | 全部静默处理 | ✅ |
| 测试 ≥5 用例 | 5+ | 9 用例 (+1 for list content) | ✅ |

---

### Task3: GhostAgent 角色切换

**涉及文件**: `zcore/engines/ghost_agent.py`, `zcore/cli/main.py`, `tests/test_ghost_roles.py`

| 检查项 | Spec 要求 | 实际 | 结果 |
|--------|-----------|------|:----:|
| `generate()` 新增 `role` 参数 | keyword-only | ✅ | ✅ |
| role=None → 行为不变 | 向下兼容 | ✅ | ✅ |
| role 存在 → 使用角色模型 | 路由 | ✅ | ✅ |
| 角色模型不存在 → fallback | 降级 | ✅ | ✅ |
| 角色模型请求失败 → fallback | 降级 | ✅ | ✅ |
| CLI `ghost roles --json` | 有效 JSON | ✅ | ✅ |
| 测试 ≥4 用例 | 4+ | 5 用例 | ✅ |

**设计亮点**: `try_model()` 内联函数将"请求+重试+observability 日志"封装为可复用单元，fallback 链 `role_model → default_model → fallback_text` 三级降级完备。

---

## 二、保护面合规检查

```
git diff 4112080..25c7645 -- zcore/engines/session.py zcore/engines/memory.py \
  zcore/engines/context.py zcore/engines/workflow.py zcore/config.py \
  zcore/runtime.py zcore/utils/privacy.py
→ (empty diff)
```

✅ **所有受保护文件零修改**

---

## 三、已发现 Issue 及修复记录

| ID | 严重度 | 文件 | 描述 | 修复状态 |
|----|:------:|------|------|:--------:|
| ISSUE-1 | ⚠️ MEDIUM | hermes_adapter.py:82 | `project = platform` 语义错误 | ✅ 已修复 (`4fc0656`) |
| ISSUE-2 | 🔵 LOW | claude_adapter.py:110 | 跳过 list 类型 content (tool_use blocks) | ✅ 已修复 (`_extract_content_text()`) |
| ISSUE-3 | 🔵 LOW | test_harvester.py:47 | `Path.home()` 隔离不完美 | ✅ 已修复 (`engine.adapters.clear()`) |

---

## 四、测试覆盖

| 测试文件 | 用例数 | Spec 最低 |
|----------|:------:|:---------:|
| test_harvester.py | 7 | 5 |
| test_adapters.py | 9 | 5 |
| test_ghost_roles.py | 5 | 4 |
| **总计** | **21** | **14** |

---

## 五、Decision-Log 新增条目

- `[2026-04-28] Hermes 数据源采用 JSON 而非 SQLite` — 决策记录
- `[2026-04-28] Claude Adapter list 类型 content 处理` — Follow-up 记录（已修复）
