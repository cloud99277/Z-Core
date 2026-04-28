---
sprint: V3.0-MVP
start: 2026-04-27
end: 2026-05-11
goal: 落地 Harvester 收割机 + GhostAgent 角色切换，让 Z-Core 拥有数据自主获取能力
---

# Sprint Backlog

## 里程碑

| 里程碑 | 目标 | 准出标准 | 预计工作量 | 依赖 | 状态 |
|--------|------|---------|-----------|------|:----:|
| **M1** | Harvester 收割机原型（Claude + Hermes adapter） | Claude adapter 解析成功率 ≥ 90%；Hermes adapter 通过 JSON 读取测试（决策：弃 SQLite 改用 JSON，见 Task0 报告）；≥ 5 个测试用例通过 | 5-7 天 | 需分析 Claude/Hermes 日志格式 | 🟢 完成 |
| **M2** | GhostAgent 角色切换 | `generate(role="compact")` 正确路由到 Flash；fallback 降级正常；≥ 3 个测试用例通过 | 1-2 天 | config.toml 已预留 | 🟢 完成 |
| **M3** | 隐私脱敏管线增强 | API key/password/IP/email/token 模式 100% 脱敏；ingest-ignore 规则生效；≥ 8 个测试用例通过 | 2-3 天 | 复用现有 privacy.py | 🟡 任务已派发 |
| **M4** | Session 全文搜索 | 1000 条会话搜索 < 2s；多关键词 AND 搜索正确；≥ 5 个测试用例通过 | 2-3 天 | 依赖 M1 产出 | 🟡 任务已派发 |

## M1 任务拆解：Harvester 收割机

- [x] 分析 `~/.claude/projects/` 目录结构，确认会话日志格式 *(Task0)*
- [x] 分析 `~/.hermes/sessions/` 数据格式（决策：直接读 JSON，弃 SQLite） *(Task0)*
- [x] 定义 `SourceAdapter` ABC 接口（`discover/ingest/health_check`） *(Task1)*
- [x] 实现 `claude_adapter.py` *(Task2)*
- [x] 实现 `hermes_adapter.py` *(Task2, ISSUE-1 已修复)*
- [x] 实现 `engines/harvester.py` 核心引擎 *(Task1)*
- [x] 实现 `zcore harvest discover/ingest/status` CLI *(Task1)*
- [x] 收割结果写入 `~/.zcore/harvested/`，MemoryEngine 可消费 *(Task1, MemoryEngine 集成待 M3/M4)*
- [x] 新增 Harvester 测试（≥ 5 用例）→ 实际 15 用例 *(Task1+Task2)*

## M2 任务拆解：GhostAgent 角色切换

- [x] `config.toml` 增加 `[llm_backend.roles]` 区块 *(Task3)*
- [x] `GhostAgent.generate()` 增加 `role` 参数 *(Task3)*
- [x] 角色模型不可用时 fallback 到 default_model *(Task3)*
- [x] 新增角色路由测试（≥ 3 用例）→ 实际 5 用例 *(Task3)*

## M3 任务拆解：隐私脱敏

- [ ] 增强 `DEFAULT_PATTERNS`：IPv4 / Email / 手机号 / AWS Key / Bearer Token *(Task4)*
- [ ] 新增 `sanitize_transcript()` 批量脱敏函数 *(Task4)*
- [ ] 新增 `load_ingest_ignore()` / `should_ignore()` *(Task4)*
- [ ] HarvesterEngine.ingest() 集成 ingest-ignore 检查 *(Task4)*
- [ ] 新增脱敏测试（≥ 5 用例）+ ingest-ignore 测试（≥ 3 用例） *(Task4)*

## M4 任务拆解：Session 搜索

- [ ] 新建 `zcore/engines/search.py` SearchEngine *(Task5)*
- [ ] 新建 `zcore/models/search.py` SearchHit + SearchResult *(Task5)*
- [ ] 实现 `zcore session search --query <keyword> [--source] [--project] [--limit] [--json]` CLI *(Task5)*
- [ ] 搜索范围：native Session meta + Harvester JSON 文件 *(Task5)*
- [ ] 多关键词 AND 搜索 + snippet 生成 *(Task5)*
- [ ] 新增搜索测试（≥ 5 用例） *(Task5)*

## MVP 阶段明确不做

- ❌ Planner Engine → V3.1
- ❌ Evaluator Engine → V3.1
- ❌ Agent Dispatcher → V3.1
- ❌ Z-Core Vision Bridge (全局视觉解释能力) → V3.1
- ❌ Dashboard（TUI/Web） → V3.1 / V3.2
- ❌ 具身伴侣表现层 (3D/Live2D) → V3.5+ / 独立仓库
- ❌ 商业化功能 → V3.2+
