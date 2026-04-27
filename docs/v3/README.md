# Z-Core V3 — 从辅助工具到主控大脑

> **Status**: Planning / Pre-Development
> **Branch**: `v3/develop`（V3 开发在分支上进行，不是独立仓库）
> **V2 锚点**: Tag `v2.0.0` on `main`
> **Created**: 2026-04-27

---

## 定位

Z-Core V3 是 Z-Core 的架构跃迁版本。V2 是 Agent 的"后勤中间件"（记忆、上下文、路由），V3 将 Z-Core 升级为 Agent 的"主控大脑"（规划、分派、验收）。

## 版本管理策略

```
main 分支         v3/develop 分支          feature 分支
    │                  │
    ├── v2.0.0 Tag     │
    │                  ├── V3 PM/RFC/Design 文档
    │                  ├── V3 新增 Engine（Harvester 等）
    │                  ├── V3 新增 CLI 命令
    │                  │
    │ (V2 Bug fix)     ├── v3/feat/harvester ──┐
    │                  ├── v3/feat/ghost-roles ─┤ merge 回 v3/develop
    │                  │                       │
    │                  ├── V3.0 MVP 完成 ───────┘
    │◄─────────────────┤ merge 到 main, Tag v3.0.0
```

- **代码**：V3 新增模块直接写在 `zcore/` 包中（增量添加，不建平行目录）
- **文档**：V3 专属规划在 `v3/pm/`，V2 规划在 `v2/pm/`（各自独立）
- **数据**：开发时通过 `ZCORE_HOME=~/.zcore-v3-dev` 隔离

## 核心模块

| 模块 | 定位 | 版本目标 |
|------|------|---------|
| **Harvester（收割机）** | 主动接入 Agent 原始日志，告别"默写 JSON" | V3.0 MVP |
| **GhostAgent 角色切换** | 不同任务用不同模型（Planner=强推理, Compact=Flash） | V3.0 MVP |
| **隐私脱敏管线** | 收割数据在入库前自动脱敏 | V3.0 MVP |
| **Session 全文搜索** | 关键词即可搜索历史会话，不需记 ID | V3.0 MVP |
| **Planner Engine** | 模糊需求 → 结构化执行计划 + 验收契约 | V3.1 |
| **Evaluator Engine** | 独立于执行者的质量验收 | V3.1 |
| **Agent Dispatcher** | 将任务分派给最合适的 Agent | V3.1 |
| **Dashboard (TUI/Web)** | 可视化运行时数据 | V3.1 / V3.2 |
| **具身伴侣 (zcore-ui)** | 3D/2D 数字人 + TTS | V3.5+ |

## 目录结构（在同一仓库 Z-Core 中）

```
Z-Core/                              # 单一仓库，v3/develop 分支
├── zcore/                           # 代码包（V2 + V3 增量）
│   ├── engines/
│   │   ├── context.py               # V2 ✅
│   │   ├── memory.py                # V2 ✅
│   │   ├── ghost_agent.py           # V2 ✅ → V3 增强（角色切换）
│   │   ├── harvester.py             # V3 新增
│   │   └── ...
│   ├── adapters/                    # V3 新增
│   │   ├── base.py                  # SourceAdapter ABC
│   │   ├── claude_adapter.py
│   │   └── hermes_adapter.py
│   └── ...
├── v3/                              # V3 专属规划
│   ├── pm/                          # V3 PM 体系
│   ├── BREAKING-CHANGES.md
│   └── MIGRATION-GUIDE.md
├── v2/                              # V2 规划（保留不动）
├── docs/v3/                         # V3 概述文档
│   └── README.md                    # 本文件
└── tests/                           # V2 + V3 测试共存
```

## 文档溯源

V3 构思文档的原始出处：

| 当前路径 | V2 原始路径 |
|---------|------------|
| `v2/pm/ideas/V3-Roadmap.md` | 原位保留 |
| `v2/pm/ideas/V3-MVP-Scope.md` | 原位保留 |
| `v2/pm/ideas/Harness-三层架构与V2增量.md` | 原位保留 |
| `v2/pm/reviews/V3-Initial-PM-Review.md` | 原位保留 |
| `v2/rfcs/003~005` | 原位保留 |
| `v2/design/{product-strategy,hermes-as-runtime,market-validation}.md` | 原位保留 |
