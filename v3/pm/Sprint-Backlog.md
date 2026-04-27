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
| **M1** | Harvester 收割机原型（Claude + Hermes adapter） | Claude adapter 解析成功率 ≥ 90%；Hermes adapter 通过 SQLite 读取测试；≥ 5 个测试用例通过 | 5-7 天 | 需分析 Claude/Hermes 日志格式 | ⚪ 待启动 |
| **M2** | GhostAgent 角色切换 | `generate(role="compact")` 正确路由到 Flash；fallback 降级正常；≥ 3 个测试用例通过 | 1-2 天 | config.toml 已预留 | ⚪ 待启动 |
| **M3** | 隐私脱敏管线增强 | API key/password/IP/email/token 模式 100% 脱敏；ingest-ignore 规则生效；≥ 3 个测试用例通过 | 2-3 天 | 复用现有 privacy.py | ⚪ 待启动 |
| **M4** | Session 全文搜索 | 1000 条会话搜索 < 2s；多关键词 AND 搜索正确；≥ 4 个测试用例通过 | 2-3 天 | 依赖 M1 产出 | ⚪ 待启动 |

## M1 任务拆解：Harvester 收割机

- [ ] 分析 `~/.claude/projects/` 目录结构，确认会话日志格式
- [ ] 分析 `~/.hermes/sessions/` SQLite schema
- [ ] 定义 `SourceAdapter` ABC 接口（`discover/ingest/health_check`）
- [ ] 实现 `claude_adapter.py`
- [ ] 实现 `hermes_adapter.py`
- [ ] 实现 `engines/harvester.py` 核心引擎
- [ ] 实现 `zcore harvest discover/ingest/status` CLI
- [ ] 收割结果写入 `~/.zcore/harvested/`，MemoryEngine 可消费
- [ ] 新增 Harvester 测试（≥ 5 用例）

## M2 任务拆解：GhostAgent 角色切换

- [ ] `config.toml` 增加 `[llm_backend.roles]` 区块
- [ ] `GhostAgent.generate()` 增加 `role` 参数
- [ ] 角色模型不可用时 fallback 到 default_model
- [ ] 新增角色路由测试（≥ 3 用例）

## M3 任务拆解：隐私脱敏

- [ ] 增强 `utils/privacy.py`：新增 `sanitize_transcript()`
- [ ] 支持 API key / password / IP / email / token 模式
- [ ] 新增 `~/.zcore/ingest-ignore` 规则文件
- [ ] Session 级 `private: true` 标记支持
- [ ] 新增脱敏测试（≥ 3 用例）

## M4 任务拆解：Session 搜索

- [ ] 实现 `zcore session search --query <keyword>` CLI
- [ ] 搜索范围：Session 元数据 + 压缩摘要 + 收割结果
- [ ] 输出：匹配会话列表（ID / 时间 / 高亮片段）
- [ ] 新增搜索测试（≥ 4 用例）

## MVP 阶段明确不做

- ❌ Planner Engine → V3.1
- ❌ Evaluator Engine → V3.1
- ❌ Agent Dispatcher → V3.1
- ❌ Dashboard（TUI/Web） → V3.1 / V3.2
- ❌ 具身伴侣 → V3.5+ / 独立仓库
- ❌ 商业化功能 → V3.2+
