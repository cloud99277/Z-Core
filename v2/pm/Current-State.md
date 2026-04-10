---
project: Z-Core-V2
stage: Phase 6 — 已完成，V2 进入维护模式
owner: yangyy
last_updated: 2026-04-10
status_source: single-source-of-truth
---

# Current State

## 当前阶段目标

关闭 V2 全部 CLI 缺口（35/35 = 100%），交付 Workflow Engine（最后一个架构设计中的 Engine），补全 session pause/resume 和 memory expire-check，打包为 `pip install` 可用的标准 Python 包。Phase 6 之后 V2 进入维护模式。

## 本阶段成功标准

- [x] `zcore workflow list/validate/run` CLI 可用
- [x] `zcore session pause/resume` CLI 可用
- [x] `zcore memory expire-check` CLI 可用
- [x] `pip install -e .` 在项目虚拟环境中验证成功，`zcore --version` 输出 `0.2.0`
- [x] CLI 覆盖率 35/35 = 100%
- [x] `unittest discover` 39 tests 全部通过
- [x] Gemini 综合审查完成（V2-Comprehensive-Review, 2026-04-11）

## 当前 P0

- [x] Workflow Engine（最后一个 Engine）
- [x] Session pause/resume
- [x] pip 打包

## 当前 P1

- [x] Memory expire-check
- [x] 文档收尾

## 已完成

- [x] Phase 0 全部（CLI skeleton, runtime bootstrap）
- [x] Phase 1 全部（Context Engine, Ghost Agent real API, Session enhancements）
- [x] Phase 2 全部（Memory Engine, auto-extraction, dedup, topics, migration）
- [x] Phase 3 全部（Skill Router, Governance Engine, Hook Framework）
- [x] Phase 4 全部（Observability Engine, Agent Setup, Config CLI, Governance extensions）
- [x] Phase 5 全部（CLI Completeness — Skill/Session/Memory/Audit + Test Cleanup）
- [x] 29 测试通过，6 个 Phase 审查报告存档
- [x] PM 管理体系精简（6→5 文件）
- [x] `delegated-sprint` skill 建立
- [x] CLI 覆盖率 89%（31/35）
- [x] Phase 6 完成，39/39 测试通过
- [x] Editable install 在虚拟环境中验证通过，`zcore 0.2.0`

## 阻塞点

无当前阻塞点；进入维护模式，等待独立审查。

## 当前最大风险

- 系统 Python 启用了 PEP 668，editable install 需在虚拟环境内验证；已用项目本地 venv 完成验证
- Workflow Engine 首版执行器采用串行 subprocess 模型，复杂条件分支/变量编排留给 V3

## 最新决策

- Phase 5 ✅ 收口（commit 63b5c71），审查通过
- Phase 6 定位为 **V2 收官**，不再新增"辅助引擎"级功能
- Workflow 定义使用 TOML（不用 YAML），保持零依赖
- Workflow 搜索路径确定为 `~/.zcore/workflows/*.toml` 与项目 `.zcore/workflows/*.toml`
- Memory 过期策略采用“标记为 `expired`”而非删除
- Codex 的 V3 构思（Planner/Evaluator/Dispatcher）记录在 `v2/pm/ideas/` 中，Phase 6 不实施

## 明确延期（留给 V3）

- Planner Engine / Evaluator Engine / Agent Dispatcher
- GhostAgent 按角色切换模型
- Context Reset 机制
- AGENTS.md 轻量化 + 知识导航
- Persona Engine (RFC-003)
- 零信任签名验签
- Embedding 语义去重
