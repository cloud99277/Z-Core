# Decision Log — Z-Core V3

> **格式要求**：每条决策必须包含「决策 / 原因 / 影响 / 兼容性评估」四段。

## [2026-04-27] 仓库收拢：从独立仓库回归 Git 分支

**决策：** 废弃独立仓库 `Z-Core-V3/`，V3 开发在 `Z-Core` 主仓库的 `v3/develop` 分支上进行。

**原因：**
- 独立仓库是 "Copy-Paste Versioning" 反模式，会导致历史断裂和代码同步困难
- V2 的 Bug 修复无法自动合并到 V3
- Git 分支是管理版本演进的标准做法
- V3.0 MVP 是纯增量开发（新增 Harvester/Adapters），不改 V2 接口，无需物理隔离

**影响：**
- `main` 分支打 `v2.0.0` Tag 作为永久锚点
- `v3/develop` 分支承载所有 V3 开发
- V3 PM 文件位于 `v3/pm/`，V2 PM 文件保留在 `v2/pm/`
- `Z-Core-V3/` 文件夹删除

**兼容性评估：**
- 对现有接口的影响：无（纯仓库管理变更，不涉及代码）
- 需要迁移的内容：无

---

## [2026-04-27] V3.0 MVP 范围确认

**决策：** V3.0 MVP = Harvester + GhostAgent 角色切换 + 隐私脱敏 + Session 搜索

**原因：**
- Harvester 是所有 V3 特性的数据前提（Planner/Evaluator 需要高质量输入）
- GhostAgent 角色切换投入小（1-2 天）、价值大（成本优化）
- 脱敏是 Harvester 的安全门槛，不可省略
- Session 搜索解决高频痛点

**影响：**
- Planner/Evaluator/Dispatcher 明确归入 V3.1
- 具身伴侣归入 V3.5+ 或独立产品线
- Dashboard 先做 TUI（V3.1），Web 版 V3.2

**兼容性评估：**
- 对现有接口的影响：无（V3.0 MVP 全部是新增模块）
- 需要迁移的内容：无（V2 Skill 无需修改即可在 V3 上运行）

---

## [2026-04-27] Gemini 建议的务实取舍

**决策：** 采纳 Git 分支/SemVer/环境隔离/Skill 版本声明 4 条建议；推迟 Side-by-Side/Feature Flag/Shadow Testing 等 8 条到 V3.1。

**原因：**
- V3.0 MVP 是纯增量开发，不改 V2 接口，不需要兼容层
- Solo 开发者项目不需要企业级配置管理
- 当 V3.1 开始修改 V2 接口时再引入 Feature Flag 和迁移适配器

**影响：**
- 保持开发敏捷性，避免过度工程化
- V3.1 启动前需要重新评估是否引入 Feature Flag

**兼容性评估：**
- 对现有接口的影响：无
- 需要迁移的内容：无

---

## [2026-04-27] PM 管理体系初始化

**决策：** 采用 5 文件 PM 管理体系（Current-State, Sprint-Backlog, Decision-Log, sprint-status, Changelog）。

**原因：** 沿用 V2 经过 6 个 Phase 实战验证的精简体系。

**影响：** V3 PM 文件在 `v3/pm/`，与 V2 的 `v2/pm/` 互不干扰。

**兼容性评估：**
- 对现有接口的影响：无
- 需要迁移的内容：无

---

## [2026-04-27] PM Skill 增强（Gate Criteria + Impact Assessment）

**决策：** 对 `project-manager` SKILL.md 和 `init-pm.py` 进行 3 项增强：Decision-Log 强制 Impact 字段、Sprint-Backlog 里程碑增加准出标准列、行动收敛增加可选回归验证。

**原因：** 基于 Gemini 的 8 条改进建议进行务实取舍，采纳 3 条高价值低成本建议，推迟 2 条到 V3.1，不采纳 3 条（过度工程化/技术不可行）。

**影响：** 所有未来的 PM 初始化和决策记录都将包含兼容性评估，里程碑推进受准出门禁约束。

**兼容性评估：**
- 对现有接口的影响：无（仅修改 PM Skill 模板和流程规则）
- 需要迁移的内容：无（已有项目的 PM 文件不受影响）

---
