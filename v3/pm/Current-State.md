---
project: Z-Core-V3
stage: V3.0 MVP — M1/M2 完成，M3/M4 任务已派发
owner: yangyy
last_updated: 2026-04-28
status_source: single-source-of-truth
---

# Current State

## 当前阶段目标

完成 V3.0 MVP：落地 Harvester 收割机 + GhostAgent 角色切换 + 隐私脱敏 + Session 搜索，让 Z-Core 从"辅助工具"迈向"数据主权中间件"。

## 本阶段成功标准

- [x] `zcore harvest discover/ingest/status` CLI 可用
- [x] Claude adapter 能正确解析 ≥ 90% 的会话日志（含 list content）
- [x] Hermes adapter 能正确解析 JSON session 存储
- [x] GhostAgent 支持按 role 路由到不同模型
- [ ] 收割数据经过脱敏管线（API key/密码/IP/Email 等）
- [ ] `zcore session search --query` 全文检索可用
- [x] 新增 ≥ 15 个测试用例 → 实际 21 个

## 当前 P0

- [x] M1: Harvester 收割机原型 — 🟢 完成（commit `25c7645`, 审查 `4d07b39`）
- [x] M2: GhostAgent 角色切换 — 🟢 完成（commit `25c7645`, 审查 `4d07b39`）
- [ ] M3: 隐私脱敏管线增强 — 🟡 任务已派发（Task4）
- [ ] M4: Session 全文搜索 — 🟡 任务已派发（Task5，依赖 Task4）

## 已完成

- [x] V3 构思全景梳理与 PM 审查（2026-04-27）
- [x] V3 MVP 范围定义
- [x] PM 管理体系初始化
- [x] 仓库收拢：废弃独立仓库，回归 `v3/develop` 分支（v2.0.0 Tag 已打）
- [x] PM Skill 增强：Impact 字段 + Gate Criteria + 回归验证
- [x] V3 PM 文件按新规范对齐
- [x] M1 Harvester 收割机（Task0 探查 + Task1 骨架 + Task2 Adapter）
- [x] M2 GhostAgent 角色切换（Task3）
- [x] Codex 代码审查 + 3 个 Issue 修复（ISSUE-1/2/3）
- [x] 审查报告入库 `v3/pm/reviews/`

## 阻塞点

- 无

## 当前最大风险

- Claude/Hermes 私有日志格式随版本更新而变化，导致 Harvester adapter 失效

## 最新决策

- [2026-04-27] 仓库收拢：废弃独立 Z-Core-V3 仓库，V3 在 `v3/develop` 分支开发
- [2026-04-27] V3.0 MVP = Harvester + GhostAgent 角色切换 + 脱敏 + Session 搜索
- [2026-04-27] 具身伴侣表现层（RFC-005）降级为 V3.5+ / 独立产品线
- [2026-04-27] Z-Core Vision Bridge 从表现层解耦，作为感知插件提拔至 V3.1
- [2026-04-28] Hermes 数据源采用 JSON 而非 SQLite（见 Decision-Log）
- [2026-04-28] Claude Adapter 支持 list 类型 content（ISSUE-2 已修复）

## 明确延期

- Planner / Evaluator / Dispatcher → V3.1
- Z-Core Vision Bridge (全局视觉解释能力) → V3.1
- TUI Dashboard → V3.1
- Web Dashboard → V3.2
- 预测性记忆推送 / 分歧审计器 → V3.2
- 具身伴侣表现层 (3D/Live2D等) → V3.5+ / 独立仓库
- 商业化付费功能 → V3.2+

## 技术快照

- **分支**: `v3/develop`
- **HEAD**: `8f0133a`
- **测试基线**: 83 pass / 0 fail / 1 skip
- **Python**: ≥3.11, 零外部依赖
