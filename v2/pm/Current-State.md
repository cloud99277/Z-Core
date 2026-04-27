---
project: Z-Core-V2
stage: V2 补完计划完成，Z-Core 作为统一官方接棒人
owner: yangyy
last_updated: 2026-04-11
status_source: single-source-of-truth
---

# Current State

## 当前阶段目标

全量接收原 KitClaw 的 `17 core skills` 与 `RAG(knowledge)` 模块，消灭功能代差并正式废弃原 KitClaw 仓库。目前已达成 V2 Complete Upgrade 的全部战略（Phase A/B/C 均 100% 达成），系统重归稳定维护与交付状态。

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

- [x] Phase 0 - Phase 6 全部功能及收尾
- [x] 独立安装包就绪（`zcore 0.2.0`）及 MCP 功能
- [x] **V2 补完计划全量达成** (V2 Complete Upgrade Strategy)：
  - [x] Phase A：内化 17 个 Core Skill（`Z-Core/skills/core`）并新增 `install --core` / `--available`
  - [x] Phase B：优雅内置可选 RAG 包并集成 `zcore knowledge index/search`
  - [x] Phase C：全面宣布前代仓库终结，确立唯一事实标准

## 阻塞点

无。

## 当前最大风险

- 后续迭代应避免再次违背“Z-Core 作为统一承载实体”的设计原则。

## 最新决策

- Phase 5 ✅ 收口（commit 63b5c71），审查通过
- Phase 6 定位为 **V2 收官**，不再新增"辅助引擎"级功能
- Workflow 定义使用 TOML（不用 YAML），保持零依赖
- Workflow 搜索路径确定为 `~/.zcore/workflows/*.toml` 与项目 `.zcore/workflows/*.toml`
- Memory 过期策略采用“标记为 `expired`”而非删除
- Codex 的 V3 构思（Planner/Evaluator/Dispatcher）记录在 `v2/pm/ideas/` 中，Phase 6 不实施

## 明确延期（留给 V3）

- 🖥️ Dashboard 可视化 UI 仪表盘（重大特性，需独立设计）
- Planner Engine / Evaluator Engine / Agent Dispatcher
- GhostAgent 按角色切换模型
- Context Reset 机制
- AGENTS.md 轻量化 + 知识导航
- Persona Engine (RFC-003)
- 零信任签名验签
- Embedding 语义去重

> 详细规划见 `v2/pm/ideas/V3-Roadmap.md`
> **V3.0 MVP 范围定义**见 `v2/pm/ideas/V3-MVP-Scope.md`（2026-04-27 PM 审查后产出）
