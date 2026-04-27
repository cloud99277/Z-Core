---
project: Z-Core-V3
stage: V3 规划阶段 — MVP 范围已定义，待启动开发
owner: yangyy
last_updated: 2026-04-27
status_source: single-source-of-truth
---

# Current State

## 当前阶段目标

完成 V3.0 MVP：落地 Harvester 收割机 + GhostAgent 角色切换 + 隐私脱敏 + Session 搜索，让 Z-Core 从"辅助工具"迈向"数据主权中间件"。

## 本阶段成功标准

- [ ] `zcore harvest discover/ingest/status` CLI 可用
- [ ] Claude adapter 能正确解析 ≥ 90% 的会话日志
- [ ] Hermes adapter 能正确解析 SQLite session 存储
- [ ] GhostAgent 支持按 role 路由到不同模型
- [ ] 收割数据经过脱敏管线（API key/密码/IP 等）
- [ ] `zcore session search --query` 全文检索可用
- [ ] 新增 ≥ 15 个测试用例

## 当前 P0

- [ ] M1: Harvester 收割机原型（Claude + Hermes adapter）
- [ ] M2: GhostAgent 角色切换（config.toml `[llm_backend.roles]`）

## 当前 P1

- [ ] M3: 隐私脱敏管线增强
- [ ] M4: Session 全文搜索

## 已完成

- [x] V3 构思全景梳理与 PM 审查（2026-04-27）
- [x] V3 MVP 范围定义（V3-MVP-Scope.md）
- [x] PM 管理体系初始化
- [x] 项目仓库创建与文档迁移

## 阻塞点

- 需要实际分析 Claude Code 的 `~/.claude/` 目录结构，确认日志格式稳定性

## 当前最大风险

- Claude/Hermes 私有日志格式随版本更新而变化，导致 Harvester adapter 失效

## 最新决策

- [2026-04-27] V3 项目从 V2 仓库独立，创建 Z-Core-V3 专用仓库
- [2026-04-27] V3.0 MVP = Harvester + GhostAgent 角色切换 + 脱敏 + Session 搜索
- [2026-04-27] 具身伴侣（RFC-005）降级为 V3.5+ / 独立产品线
- [2026-04-27] Dashboard 优先做 TUI（V3.1），Web 版本 V3.2+

## 明确延期

- Planner / Evaluator / Dispatcher → V3.1
- TUI Dashboard → V3.1
- Web Dashboard → V3.2
- 预测性记忆推送 / 分歧审计器 → V3.2
- 具身伴侣表现层 → V3.5+ / 独立仓库
- 商业化付费功能 → V3.2+
- Creator Economy → V4+

> 详细规划见 `pm/ideas/V3-MVP-Scope.md` 和 `pm/ideas/V3-Roadmap.md`
