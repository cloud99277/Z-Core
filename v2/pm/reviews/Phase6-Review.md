# Phase 6 Independent Review Report

**审查者**：Gemini（独立审查）  
**审查日期**：2026-04-11  
**Commit**：`89b8b42`  
**审查方法**：code-review skill Standard 模式 5 层审查  

## 审查结论：✅ 通过（Pass）

发现 0 个 Blocking，0 个需修复，1 个 Nit。

## 变更概要

| 类型 | 文件数 | 新增/修改行数 |
|------|--------|-------------|
| 新增 Engine | 1 (`workflow.py`) | 191 行 |
| 新增 Model | 1 (`workflow.py`) | 60 行 |
| 扩展 Engine | 2 (`session.py`, `memory.py`) | 93 行 |
| 扩展 Model | 2 (`session.py`, `memory.py`) | 8 行 |
| CLI 扩展 | 1 (`main.py`) | 84 行 |
| 打包 | 2 (`pyproject.toml`, `__version__.py`) | 6 行 |
| Runtime | 1 (`runtime.py`) | 5 行 |
| 新增 Tests | 3 | 214 行 |
| PM 文件 | 5 | — |
| **合计** | **18** | **~661** |

## Layer 1: 架构审查

### 符合设计

- ✅ **Workflow Engine** 是独立新 Engine（`zcore/engines/workflow.py`），不嵌入其他 Engine
- ✅ Workflow 定义使用 **TOML**（`tomllib` stdlib），保持零外部依赖
- ✅ Workflow 发现支持全局（`~/.zcore/workflows/`）+ 项目级（`.zcore/workflows/`）双路径
- ✅ `session pause/resume` 正确扩展 `SessionManager`，不触发 hook
- ✅ `memory expire-check` 标记 `type = "expired"` 而不是删除，可恢复
- ✅ `MemoryType` Literal 和 `_MARKDOWN_RE` 正则同步添加 `"expired"` 类型
- ✅ `pyproject.toml` 声明 `[project.scripts] zcore = "zcore.cli.main:main"`
- ✅ `__version__` 从 `zcore/__version__.py` 导入，版本号 `0.2.0`

### 与设计文档/任务文件对照

| 任务要求 | 实际实现 | 评估 |
|---------|---------|------|
| `workflow list/validate/run` | ✅ 三个子命令完整实现 | 一致 |
| `session pause/resume` | ✅ 状态机 active↔paused | 一致 |
| `memory expire-check --older-than --dry-run` | ✅ 标记过期 + dry-run | 一致 |
| `pip install -e .` + `zcore --version` | ✅ pyproject.toml + entry point | 一致 |
| Workflow TOML 格式 | ✅ `[workflow]` + `[[steps]]` 结构 | 一致 |
| `on_failure = "continue" | "abort"` | ✅ 支持，abort 时跳过剩余步骤 | 一致 |
| `SessionMeta.paused_at/resumed_at` | ✅ 新增字段 | 一致 |
| `RuntimePaths.workflows_dir` | ✅ `base_dir / "workflows"` + `ensure_runtime_dirs` | 一致 |

### 无偏差项

Phase 6 任务文档定义的全部命令和接口规格完全一致实现，无偏差。

## Layer 2: 逻辑审查

### ✅ 无 Blocking 问题

### Nit

**T1: `run_workflow()` 重新构建 `WorkflowDefinition` 而不是复用 `validate` 的结果**

```python
# workflow.py:85-89
workflow = WorkflowDefinition(
    name=str(validation["workflow"]["name"]),
    ...
    steps=[WorkflowStep(**step) for step in validation["workflow"]["steps"]],
)
```

`validate_workflow()` 内部已经 `load_workflow()` 拿到了 `WorkflowDefinition`，但返回的是 `workflow.to_dict()` 字典。`run_workflow()` 又从字典重建对象。虽然功能正确，但多了一次 dict→dataclass 转换。

**建议**：后续可让 `validate_workflow()` 同时返回原始 `WorkflowDefinition` 对象，避免反序列化。风险极低，不影响功能。

## Layer 3: 可读性审查

- ✅ `WorkflowEngine` 结构清晰：`discover → load → validate → run`
- ✅ `_parse_workflow_file()` 的 TOML 解析有完善的错误消息（标明文件路径和位置）
- ✅ `_resolve_target_session()` 提取为公共方法，避免 pause/resume 重复代码
- ✅ `_persist_meta()` 统一了 meta 写入 + index 更新
- ✅ `rewrite_topic()` 的 FileLock 保护
- ✅ 所有新方法有完整 type hints

## Layer 4: 性能审查

- ✅ `discover_workflows()` 使用 `seen: set[Path]` 去重，避免全局和项目级重复
- ✅ `expire_check()` 按 topic 遍历，局部更新（`rewrite_topic` 只写变更的 topic），不全量重写
- ✅ `run_workflow()` 的 subprocess 有 `capture_output=True`，stdout 截取前 500 字符

## Layer 5: 安全审查

- ✅ `install_skill()` + `workflow run` 的 subprocess 调用无 `shell=True`
- ✅ `expire_check()` 非 dry-run 时使用 `FileLock` + `atomic_write_text`
- ✅ `pause/resume` 有状态校验 — 只有 `active` 能 pause，只有 `paused` 能 resume

## 测试覆盖

| 测试文件 | 测试数 | 覆盖范围 |
|---------|--------|---------|
| `test_workflow.py` | 5 | list/validate pass/validate error/run dry-run/run continue-on-failure |
| `test_session_pause.py` | 3 | pause/resume/pause→resume→end 全程 |
| `test_memory_expire.py` | 2 | dry-run/actual expire |
| **Phase 6 新增** | **10** | Phase 6 全覆盖 |

回归测试：

| 测试集 | 结果 |
|--------|------|
| `unittest discover`（39 tests） | ✅ 全部通过 |
| `compileall` | ✅ 通过 |

## CLI 命令覆盖率分析（Phase 6 后 — Final）

| 设计命令 | Phase | 状态 |
|---------|-------|------|
| `init`, `status`, `doctor` | 0 | ✅ |
| `context analyze`, `compact` | 1 | ✅ |
| `memory extract/list/search/pending` | 2 | ✅ |
| `memory write/topics/stats` | 5 | ✅ |
| `memory expire-check` | **6** | ✅ |
| `session start/end/list/handoff` | 0+1 | ✅ |
| `session show/cleanup` | 5 | ✅ |
| `session pause/resume` | **6** | ✅ |
| `skill list/match` | 3 | ✅ |
| `skill info/install/validate` | 5 | ✅ |
| `run <skill>` | 3 | ✅ |
| `governance rules/check/allow/deny/log` | 3+4 | ✅ |
| `governance audit` | 5 | ✅ |
| `observe stats/costs/health` | 4 | ✅ |
| `setup claude/gemini/codex/detect` | 4 | ✅ |
| `config show/set/reset` | 4 | ✅ |
| `workflow list/validate/run` | **6** | ✅ |
| `migrate` | 2 | ✅ |
| `--version` | **6** | ✅ |
| **覆盖率** | | **35/35 = 100%** |

## V2 最终统计

| 指标 | 数据 |
|------|------|
| **总 Phase 数** | 7（Phase 0-6） |
| **CLI 命令覆盖率** | 35/35 = 100% |
| **总测试数** | 39 |
| **Engine 数量** | 9（Context/Memory/Session/Router/Governance/Observability/AgentSetup/GhostAgent/Workflow） |
| **模型数量** | 5（session/memory/context/governance/workflow） |
| **公共模块** | 7（tokens/frontmatter/fs/filelock/privacy/prompts/time） |
| **总代码行数** | ~5,000+（zcore/） |
| **外部依赖** | 0 |
| **Python 版本** | ≥3.11 |
| **包版本** | 0.2.0 |

## 总评

Phase 6 交付质量优秀。Workflow Engine 设计干净（TOML 定义 → discover → validate → run 闭环），session pause/resume 状态机简洁可靠，memory expire-check 的"标记而非删除"策略正确。`pyproject.toml` 打包使得 `pip install -e .` → `zcore --version` 可用。测试全面（10 个新测试，39/39 全量通过）。

**V2 正式收官：CLI 100% 覆盖，0 外部依赖，39 测试全绿，可 pip 安装。**
