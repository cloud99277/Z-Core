# V3 Breaking Changes

> 本文档跟踪 V3 相对于 V2 的所有接口变化。每次修改 V2 已有接口时必须在此记录。

---

## 当前状态：V3.0 MVP — 无破坏性变更

V3.0 MVP 是**纯增量开发**，不修改任何 V2 已有接口。V2 的 Skill 无需修改即可在 V3 上运行。

### 新增模块（不影响 V2 兼容性）

| 模块 | 文件 | 说明 |
|------|------|------|
| Harvester Engine | `zcore/engines/harvester.py` | 新增收割引擎 |
| Source Adapters | `zcore/adapters/` | 新增适配器目录 |
| CLI 命令 | `zcore harvest discover/ingest/status` | 新增 CLI 子命令 |

### 修改模块（向下兼容）

| 模块 | 变化 | 兼容性 |
|------|------|--------|
| `GhostAgent.generate()` | 新增 `role` 参数 | 默认值保持 V2 行为，不传 role 时无任何变化 |
| `config.toml` | 新增 `[llm_backend.roles]` 区块 | 可选配置，不配也正常工作 |
| `utils/privacy.py` | 新增 `sanitize_transcript()` | 新增函数，不影响现有函数 |

### 数据格式变化

| 数据 | 变化 | 迁移需求 |
|------|------|---------|
| `~/.ai-memory/` | 无变化 | 无需迁移 |
| `~/.zcore/config.toml` | 新增可选区块 | 无需迁移 |
| `~/.zcore/harvested/` | 新增目录 | 自动创建 |

---

## V3.1 预期的破坏性变更（预告）

以下变更将在 V3.1 引入，届时需要更新本文档并编写迁移指南：

- [ ] Planner Engine 可能修改 `SessionManager` 的状态机
- [ ] Evaluator Engine 可能扩展 `ObservabilityEngine` 的日志格式
- [ ] Dispatcher 可能修改 `zcore run` 的执行协议
