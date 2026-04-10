# Phase 5: Skill Management + Session Lifecycle + Memory Operations + CLI Completeness

## 目标

让 Z-Core 的 CLI 命令树对齐设计文档（`v2/design/cli.md`），补全所有剩余的 Skill 管理、Session 生命周期、Memory 操作命令，达到 **CLI 功能完备** 状态。Phase 0-4 建成了全部引擎层，Phase 5 补全 CLI 表面积，使 Agent 和用户可以通过 `zcore` 完成所有预设操作。

## 上下文

- 当前 19 测试通过（Phase 3：5 + Phase 4：14），commit `14e4f22`，分支 `feat/v2`
- 已有共享测试 helper：`tests/helpers.py`（`run_zcore`, `TestHome`, `pushd`）
- 保持零外部依赖原则
- 已有引擎：Context, Memory, Session, Router, Governance, Observability, GhostAgent, AgentSetup

## 执行方法论

本任务使用 `delegated-sprint` skill 的标准流程，当前处于 **Step 2: Dispatch（执行 Agent 编码）**。

> 完整流程定义见 `~/.ai-skills/delegated-sprint/SKILL.md`
> Step 1 (Plan) 已由 Gemini 完成；Step 3 (Review) 和 Step 4 (Commit) 将在本任务完成后由 Gemini 执行。

### 执行 Agent 必须遵守的规则

1. **🔒 code-review 自审不可跳过**：编码完成后，必须先 `view_file` 读取 `~/.ai-skills/code-review/SKILL.md`，然后按其定义的流程执行 self-review。
2. **测试先行**：每个 Milestone 完成后先验证该 Milestone 的测试通过，再进入下一个 Milestone。
3. **回归保护**：最终交付前，历史 19 个测试必须全部通过。
4. **PM 文件同步**：编码完成后更新 PM 文件。
5. **使用共享 helper**：测试文件使用 `tests/helpers.py` 中的 `run_zcore`, `TestHome`, `pushd`，不要重新定义。

## 任务详情

### M1: Skill 管理命令（1.5 天）

补全 `zcore skill info/install/validate` 命令。

**`zcore skill info <name> [--json]`**
- 读取 skill 的 `SKILL.md` frontmatter，展示名称、描述、IO 契约、权限要求、激活条件
- 使用已有的 `SkillManifest` + `parse_frontmatter()`
- 验收：`zcore skill info memory-manager --json` 输出 manifest JSON

**`zcore skill install <source> [--name <name>] [--json]`**
- `source` 支持本地路径（`/path/to/skill/`）和 Git URL（`https://github.com/user/skill.git`）
- 本地路径：copy 到 `$AI_SKILLS_DIR/<name>/`
- Git URL：`git clone --depth 1` 到 `$AI_SKILLS_DIR/<name>/`（如有 git 命令）
- 安装后自动运行 `validate`
- 安装前检查目标路径是否已存在（已存在则报错，除非 `--force`）
- 清理辅助文件（`.git/`, `README.md` 中的安装说明部分）
- 验收：`zcore skill install /tmp/test-skill --json` 安装成功

**`zcore skill validate <name> [--json]`**
- 检查 skill 目录结构：SKILL.md 存在、frontmatter 可解析、name 字段非空
- 检查 scripts/ 目录下的脚本文件有执行权限（如有）
- 输出检查结果列表（PASS/WARN/ERROR）
- 验收：`zcore skill validate memory-manager --json` 输出检查结果

**实现位置**：
- Skill management 逻辑放在 `zcore/engines/router.py` 中扩展 `SkillRouter` 类（已有 `list_skills` 和 `match_skills`），添加 `get_skill_info()`, `install_skill()`, `validate_skill()` 方法
- CLI 放在 `zcore/cli/main.py` 的 `skill` subparser 下

### M2: Session 生命周期完善（1 天）

补全 `zcore session show/cleanup` 命令（`pause`/`resume` 暂不实现，标记延期）。

**`zcore session show <session-id> [--json]`**
- 读取 `~/.zcore/sessions/<session-id>/meta.json` 展示会话详情
- 包含：agent, project, start_time, end_time, duration, status, tags
- 如果有 `context.json.gz` 则展示大小
- 验收：`zcore session show <id> --json` 输出会话元数据

**`zcore session cleanup [--older-than 30d] [--dry-run] [--json]`**
- 清理过期的会话快照目录
- `--older-than` 默认 30d，支持 d/w/m 后缀
- `--dry-run` 只列出将被清理的会话，不实际删除
- 验收：`zcore session cleanup --dry-run --json` 列出过期会话

**实现位置**：
- 扩展 `zcore/engines/session.py` 中的 `SessionManager`，添加 `show_session()` 和 `cleanup_sessions()` 方法
- CLI 放在 `zcore/cli/main.py` 的 `session` subparser 下

### M3: Memory 操作完善（1 天）

补全 `zcore memory write/topics/stats` 命令（`expire-check` 暂不实现，标记延期）。

**`zcore memory write <content> [--topic <topic>] [--tags <tags>] [--json]`**
- 直接写入一条记忆到指定 topic 文件（默认 `general`）
- 自动生成 timestamp、ID
- 支持 `--tags` 以逗号分隔
- 验收：`zcore memory write "决定使用零依赖架构" --topic architecture --json` 写入成功

**`zcore memory topics [--json]`**
- 列出所有 topic 文件和每个 topic 的记忆条目数
- 使用已有的 `TopicStore`
- 验收：`zcore memory topics --json` 输出 topic 列表

**`zcore memory stats [--json]`**
- 展示记忆统计：总条目数、topic 数、磁盘占用、最近写入时间
- 验收：`zcore memory stats --json` 输出统计数据

**实现位置**：
- 扩展 `zcore/engines/memory.py` 中的 `MemoryEngine` 和 `TopicStore`，添加 `write_memory()`, `list_topics()`, `get_stats()` 方法
- CLI 放在 `zcore/cli/main.py` 的 `memory` subparser 下

### M4: Governance Audit + 测试 + 历史测试整治（1.5 天）

**`zcore governance audit [--json]`**
- 综合安全审计报告：规则统计、最近拒绝事件、高频 skill、危险命令历史
- 从 `executions.jsonl` 和 config rules 聚合数据
- 验收：`zcore governance audit --json` 输出审计报告

**历史测试整治**
- 在 `tests/__init__.py` 中添加依赖检测，跳过需要 `pytest`/`pandas` 等外部依赖的测试
- 确保 `python3 -m unittest discover tests -q` 能无错跑完（跳过不兼容的测试，不报 ImportError）
- 现有历史测试文件需要在顶部添加 `skipIf` 检测：`test_conversation_distiller.py`, `test_knowledge_index.py`, `test_knowledge_search.py`, `test_knowledge_search_wrapper.py`, `test_mcp_export.py`, `test_md_chunker.py`, `test_skill_security_audit.py`, `test_validate_frontmatter.py`
- 验收：`python3 -m unittest discover tests -q` 运行完成，跳过依赖缺失的测试，Phase 0-5 测试全部通过

**Phase 5 新增测试**：
- `tests/test_skill_management.py`：skill info/install/validate
- `tests/test_session_lifecycle.py`：session show/cleanup
- `tests/test_memory_ops.py`：memory write/topics/stats
- `tests/test_governance_audit.py`：governance audit
- 验收：新增 ≥8 个测试，总计 27+ 测试全部通过

## 交付标准

1. 全部新文件通过 `python3 -m compileall zcore tests`
2. `python3 -m unittest -q tests.test_skill_management tests.test_session_lifecycle tests.test_memory_ops tests.test_governance_audit` 全部通过
3. 历史测试回归：`python3 -m unittest -q tests.test_observability tests.test_agent_setup tests.test_config_cli tests.test_governance_ext tests.test_skill_router` 全部通过
4. `python3 -m unittest discover tests -q` 能无错完成（跳过依赖缺失的测试）
5. 冒烟验证：
   - `python3 -m zcore skill info memory-manager --json`（如果 `$AI_SKILLS_DIR` 下有 memory-manager skill）
   - `python3 -m zcore skill validate memory-manager --json`
   - `python3 -m zcore session cleanup --dry-run --json`
   - `python3 -m zcore memory topics --json`
   - `python3 -m zcore memory stats --json`
   - `python3 -m zcore governance audit --json`
6. 执行 code-review self-review，修复所有 Blocking 问题

## 完成后更新 PM 文件

- `v2/pm/Current-State.md`: 更新成功标准完成状态
- `v2/pm/Sprint-Backlog.md`: 标记 M1-M4 ✅
- `v2/pm/sprint-status.md`: 更新验证结果
- `v2/pm/Decision-Log.md`: 记录实现期间的任何决策变更

## 技术约束（必读）

- **零外部依赖**：不引入 click、tomlkit、PyYAML 等。用 stdlib re/tomllib/argparse/subprocess/shutil
- **Python ≥3.11**：可用 tomllib（stdlib）
- **保持 argparse**：CLI 继续用 argparse
- **skill install 的 Git 克隆**：使用 `subprocess.run(["git", "clone", ...])` + `shutil.which("git")` 检测。Git 不可用时只支持本地路径安装
- **session cleanup 的时间解析**：复用 `ObservabilityEngine._parse_since()` 的逻辑或提取为公共函数（建议提取到 `zcore/utils/time.py`）
- **历史测试整治**：只加 `skipIf`，不修改测试逻辑本身。目标是让 `discover` 不报错，不是让所有历史测试通过
- **使用共享 helper**：新测试文件必须 `from tests.helpers import run_zcore, TestHome`
