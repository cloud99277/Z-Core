---
sprint: Phase6-Week1
start: 2026-04-11
end: 2026-04-25
goal: V2 收官 — Workflow Engine + Session/Memory 补全 + pip 打包（CLI 100%）
---

# Sprint Backlog

## 里程碑

| 里程碑 | 目标 | 预计时间 | 状态 |
|--------|------|----------|:----:|
| **M1** | Workflow Engine + CLI（list/run/validate） | 2 天 | ✅ 完成 |
| **M2** | Session pause/resume | 1 天 | ✅ 完成 |
| **M3** | Memory expire-check + pyproject.toml 打包 | 1.5 天 | ✅ 完成 |
| **M4** | 测试 + 回归 + 文档 | 0.5 天 | ✅ 完成 |

## 当前 Sprint 任务

### M1: Workflow Engine

- [x] 新增 `zcore/models/workflow.py`：`WorkflowDefinition`, `WorkflowStep`, `StepResult`, `WorkflowResult`
- [x] 新增 `zcore/engines/workflow.py`：`WorkflowEngine`（discover/load/validate/run）
- [x] `zcore workflow list [--json]` — 列出全局+项目级 workflow
- [x] `zcore workflow validate <name|file> [--json]` — 校验 TOML 结构 + skill 引用
- [x] `zcore workflow run <name|file> [--dry-run] [--json]` — 按序执行 steps

### M2: Session pause/resume

- [x] 扩展 `SessionMeta`：添加 `paused_at`, `resumed_at` 字段
- [x] `SessionManager.pause()` / `resume()` 方法（状态机：active↔paused）
- [x] `zcore session pause [--session-id] [--json]`
- [x] `zcore session resume [--session-id] [--json]`

### M3: Memory expire-check + 打包

- [x] `MemoryEngine.expire_check()` — 基于 `updated_at` + `parse_since_window()`
- [x] `zcore memory expire-check [--older-than 90d] [--dry-run] [--json]`
- [x] 更新 `pyproject.toml`（name=zcore, version=0.2.0, scripts entry）
- [x] 创建 `zcore/__version__.py`
- [x] `pip install -e .` + `zcore --version` 在项目虚拟环境验证通过

### M4: 测试 + 回归 + 文档

- [x] `tests/test_workflow.py`（5 tests）
- [x] `tests/test_session_pause.py`（3 tests）
- [x] `tests/test_memory_expire.py`（2 tests）
- [x] `unittest discover` 39 tests 全部通过
- [x] PM 文件同步

## 前置依赖（已就绪）

- [x] `SkillRouter.list_skills()` / `match_skills()`（workflow validate 检查 skill 引用）
- [x] `SessionManager`（pause/resume 扩展）
- [x] `MemoryEngine` / `TopicStore`（expire-check 扩展）
- [x] `parse_since_window()`（expire-check 时间解析）
- [x] `tests/helpers.py`（共享测试 helper）

## V2 明确不做（留给 V3）

- ❌ Planner Engine（需求展开 → 结构化计划）→ V3
- ❌ Evaluator Engine（独立验收，不靠自评）→ V3
- ❌ Agent Dispatcher（任务分派给 Claude/Codex/Gemini）→ V3
- ❌ GhostAgent 按角色切换模型 → V3
- ❌ Context Reset 机制 → V3
- ❌ AGENTS.md 轻量化 + 知识导航 → V3
- ❌ Persona Engine (RFC-003) → V3
- ❌ 零信任签名验签 → V3
- ❌ Embedding 语义去重 → V3
