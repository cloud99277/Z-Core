# Phase 4 Independent Review Report

**审查者**：Gemini（独立审查）  
**审查日期**：2026-04-10  
**Commit**：`6ae0992`  
**审查方法**：code-review skill Standard 模式 5 层审查  

## 审查结论：✅ 有条件通过（Conditional Pass）

发现 1 个需修复问题（已修复），0 个 Blocking，2 个 Non-blocking，2 个 Nit。

## 变更概要

| 类型 | 文件数 | 新增行数 |
|------|--------|---------|
| 新增 Engine | 2 | 449 行 |
| 新增 Tests | 4 | 487 行 |
| 修改 Core | 6 | 516 行 |
| 修改 PM | 4 | — |
| **合计** | **16** | **~1450** |

## Layer 1: 架构审查

### 符合设计

- ✅ `ObservabilityEngine` 和 `AgentSetupEngine` 正确放置在 `zcore/engines/` 下
- ✅ 两个 Engine 都依赖 `RuntimePaths` 注入，与现有引擎模式一致
- ✅ `builtin.py` 的 `log_execution` hook 正确委托给 `ObservabilityEngine`，消除了直接 JSONL 写入
- ✅ `GhostAgent.generate()` 正确集成了 `ObservabilityEngine.log_cost()` 调用
- ✅ 自定义 hook 脚本通过 `HookRunner._load_custom_hooks()` 加载，builtin 优先级在前
- ✅ 零外部依赖保持：仅用 `tomllib`, `re`, `subprocess`, `argparse`, `json`

### 与设计文档偏差

| 设计要求 | 实际实现 | 评估 |
|---------|---------|------|
| `zcore observe stats/costs/health` | ✅ 完全实现 | 一致 |
| `zcore setup <agent>/detect` | ✅ 完全实现 | 一致 |
| `zcore config show/set/reset` | ✅ 完全实现 | 一致 |
| `zcore governance allow/deny/log` | ✅ 完全实现 | 一致 |
| 自定义 hook 从 `.d/` 加载 | ✅ 实现 | 一致 |
| 成本估算硬编码定价 | ✅ `PRICING_PER_1M_TOKENS` | 一致 |
| 标记块幂等注入 | ✅ `ZCORE:START/END` | 一致 |
| Config set 原子写入 | ✅ `_atomic_write` + `FileLock` | 一致 |

## Layer 2: 逻辑审查

### 🔧 已修复（审查期间）

**F1: `mask_sensitive_data` 误报 — `buffer_tokens` 被掩码**
- 原因：正则 `(token)` 作为子串匹配，导致 `buffer_tokens`、`input_tokens` 等非敏感字段被误掩码
- 修复：改为 `(^|[_-])(api[_-]?key|secret|password|auth[_-]?token)$`，只匹配结尾为敏感词的 key
- 验证：`buffer_tokens=13000` 不再被掩码，`api_key`/`auth_token`/`secret`/`password` 仍被掩码

### Non-blocking

**N1: `_parse_since()` 仅支持 `d` 和 `h` 后缀**
- `get_execution_stats(since="30d")` 和 `since="7d"` 覆盖主要场景
- 但不支持 `w`（周）、`m`（月），后续可扩展
- 风险：低（CLI 默认值覆盖了常用场景）

**N2: `_detect_version()` 对 Claude Code 返回的是 `--version` stdout**
- smoke 测试显示 Claude 检测到版本 `"2.1.37 (Claude Code)"`，这是有效的
- 但 Gemini/Codex 在当前环境不可用（返回 None），这是预期行为
- 如果未来 `claude --version` 输出格式变化，可能需要适配

### Nit

**T1: 测试文件中 `run_zcore()` helper 重复定义**
- 4 个测试文件各有一份几乎相同的 `run_zcore()` helper
- 建议后续提取到 `tests/conftest.py` 或 `tests/helpers.py`
- 不阻塞：当前不影响功能

**T2: `tempfile_home` / `temp_home` / `HomeWorkspace` 命名不一致**
- 3 种不同的临时目录上下文管理器实现
- 建议后续统一为一个 `TestHome` 类
- 不阻塞：当前不影响功能

## Layer 3: 可读性审查

- ✅ 所有新文件都有 type hints
- ✅ `to_dict()` 方法命名一致（所有 dataclass 都提供）
- ✅ CLI 子命令结构清晰（`observe`, `setup`, `config`, `governance` 各用 subparser）
- ✅ 注入模板内容清晰（`render_injection_block()` 返回可读的 markdown 指令）

## Layer 4: 性能审查

- ✅ JSONL 读取使用逐行 `json.loads()`，对大文件友好
- ✅ `_path_size` 使用 `rglob("*")` 遍历，对正常规模目录无性能问题
- ⚠️ `_iter_jsonl()` 每次调用读取整个文件到内存 → 如果 `executions.jsonl` 增长到 MB 级别，可能需要优化为流式读取。当前阶段无风险。

## Layer 5: 安全审查

- ✅ `_atomic_write()` 使用 `tempfile` + `os.replace()` 保证写入原子性
- ✅ 新写入的 config 文件权限设为 `0o600`
- ✅ 自定义 hook 脚本使用 `subprocess.run()` + `check=False`，不会因脚本崩溃导致主进程异常
- ✅ Agent Setup 的 `_inject_block()` 使用 `str.index()` 精确查找标记块，不存在注入漏洞
- ✅ `setup_agent()` 在写入前备份原文件（`.bak`）

## 测试覆盖

| 测试文件 | 测试数 | 覆盖范围 |
|---------|--------|---------|
| `test_observability.py` | 4 | ExecutionStats 聚合+过滤、CostReport 预算+provider 过滤、HealthReport 路径检测、CLI smoke |
| `test_agent_setup.py` | 3 | Agent 检测、Setup 注入+幂等、CLI detect+dry-run |
| `test_config_cli.py` | 3 | 敏感字段掩码、set dot-notation、reset section+force |
| `test_governance_ext.py` | 3 | allow/deny 持久化、governance log 读取+过滤、自定义 hook 执行+环境变量注入 |
| **合计** | **13** | Phase 4 全覆盖 |

回归测试：`test_skill_router` 5/5 通过。全量 18/18 通过。

## 总评

Codex Phase 4 交付质量优秀。代码结构清晰，与现有引擎模式完全一致，测试覆盖全面。唯一发现的实质问题（`mask_sensitive_data` 误报）已在审查期间修复。2 个 Non-blocking 和 2 个 Nit 是技术债层面的改进建议，不影响功能正确性。
