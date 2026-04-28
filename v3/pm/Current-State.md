---
project: Z-Core-V3
stage: V3.0 MVP — 🟢 全部里程碑完成，Sprint 关闭
owner: yangyy
last_updated: 2026-04-28
status_source: single-source-of-truth
---

# Current State

## 当前阶段目标

~~完成 V3.0 MVP~~ → ✅ **已完成**。Harvester 收割机 + GhostAgent 角色切换 + 隐私脱敏 + Session 搜索全部落地。

## 本阶段成功标准

- [x] `zcore harvest discover/ingest/status` CLI 可用
- [x] Claude adapter 能正确解析 ≥ 90% 的会话日志（含 list content）
- [x] Hermes adapter 能正确解析 JSON session 存储
- [x] GhostAgent 支持按 role 路由到不同模型
- [x] 收割数据经过脱敏管线（API key/密码/IP/Email/手机号/Bearer Token）
- [x] `zcore session search --query` 全文检索可用（AND 搜索 + snippet + gzip 上下文）
- [x] 新增 ≥ 15 个测试用例 → 实际 39 个（101 总计）

## 里程碑总结

| 里程碑 | 状态 | 提交 | 测试 |
|--------|:----:|------|:----:|
| M1 Harvester 收割机 | 🟢 完成 | `25c7645` + `4d07b39` (review fix) | 15 |
| M2 GhostAgent 角色切换 | 🟢 完成 | `25c7645` + `4d07b39` (review fix) | 5 |
| M3 隐私脱敏管线 | 🟢 完成 | `731c5ae` | 11 |
| M4 Session 全文搜索 | 🟢 完成 | `367fee9` | 7 |

## 已完成

- [x] V3 构思全景梳理与 PM 审查（2026-04-27）
- [x] V3 MVP 范围定义
- [x] PM 管理体系初始化
- [x] 仓库收拢：废弃独立仓库，回归 `v3/develop` 分支（v2.0.0 Tag 已打）
- [x] PM Skill 增强：Impact 字段 + Gate Criteria + 回归验证
- [x] V3 PM 文件按新规范对齐
- [x] M1 Harvester 收割机（Task0 探查 + Task1 骨架 + Task2 Adapter）
- [x] M2 GhostAgent 角色切换（Task3）
- [x] Codex M1/M2 代码审查 + 3 个 Issue 修复
- [x] M3 隐私脱敏管线增强（Task4）
- [x] M4 Session 全文搜索（Task5）
- [x] Codex M3/M4 代码审查 — LGTM
- [x] 审查报告入库 `v3/pm/reviews/`
- [x] Sprint Backlog 全部子任务关闭

## 下一步 (V3.1)

- [ ] Planner Engine
- [ ] Z-Core Vision Bridge (全局视觉解释能力)
- [ ] TUI Dashboard
- [ ] 合并 `v3/develop` → `main` 并打 `v3.0.0` Tag

## 最新决策

- [2026-04-27] 仓库收拢：废弃独立 Z-Core-V3 仓库，V3 在 `v3/develop` 分支开发
- [2026-04-27] V3.0 MVP = Harvester + GhostAgent 角色切换 + 脱敏 + Session 搜索
- [2026-04-27] 具身伴侣表现层（RFC-005）降级为 V3.5+ / 独立产品线
- [2026-04-27] Z-Core Vision Bridge 从表现层解耦，作为感知插件提拔至 V3.1
- [2026-04-28] Hermes 数据源采用 JSON 而非 SQLite
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
- **HEAD**: `367fee9`
- **测试基线**: 101 pass / 0 fail / 1 skip
- **Python**: ≥3.11, 零外部依赖
- **V3 新增文件**: 15 files, ~2000 lines
