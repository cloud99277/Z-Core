---
title: "Phase 3 完成审查报告"
reviewer: gemini (antigravity)
executor: codex
date: 2026-04-10
phase: 3
status: passed
---

# Phase 3 审查报告

> **审查时间**：2026-04-10
> **分支**：`feat/v2`（commit `4d9ceba`）
> **审查范围**：Skill Router + Governance Engine + Hook Framework
> **执行方**：Codex（Phase 3 实现 + 自审修复）+ Gemini（独立审查）
> **审查模式**：Standard（~1200 行新增/修改代码，分批审查）

---

## 一、审查结论：✅ 通过

5/5 Phase 3 测试全部通过（0.049s），8 个成功标准中 7 个已达标（全仓历史测试依赖阻塞除外）。

| 成功标准 | 状态 |
|---------|:----:|
| `zcore skill list` 发现 skill 并解析 SKILL.md frontmatter | ✅ |
| `zcore skill match "压缩对话"` 按三层路由返回排序候选 | ✅ |
| `zcore run <skill>` 执行 skill + pre/post hook 链 | ✅ |
| `zcore governance check shell "rm -rf /"` 返回 DENIED | ✅ |
| `zcore governance rules` 列出权限规则 | ✅ |
| hook 链中 pre-hook 失败时中止执行 | ✅ |
| 全仓历史测试全量通过 | ⚠️ 环境阻塞 |
| 新增 ≥5 个 Phase 3 测试 | ✅ (5 个) |

---

## 二、新增/修改代码清单

### 新增文件（5 个）

| 文件 | 行数 | 内容 |
|------|------|------|
| `zcore/models/skill.py` | 250 | SkillManifest + ActivationConfig + DependencyConfig + LifecycleConfig + PermissionConfig + IOConfig dataclasses，`from_skill_md()` 解析 |
| `zcore/utils/frontmatter.py` | 237 | 纯 stdlib YAML frontmatter 解析器，支持嵌套 dict/list、block scalar (`|` `>`)、inline list、引号字符串、注释 |
| `zcore/engines/router.py` | 290 | SkillRouter：discover + match（三层）+ activate_conditional + execute（含生命周期）|
| `zcore/hooks/lifecycle.py` | 77 | HookRunner：加载 builtin hooks → 按序执行 → pre 阶段 fail 即中断 |
| `zcore/hooks/builtin.py` | 90 | 3 个内置 hook：validate-input、check-permissions、log-execution |
| `zcore/hooks/__init__.py` | 2 | 包标识 |
| `tests/test_skill_router.py` | 269 | 5 个测试：frontmatter 解析、真实 skill 解析、路由全流程、权限优先级、CLI 端到端 |

### 修改文件（2 个）

| 文件 | 变更 | 内容 |
|------|------|------|
| `zcore/engines/governance.py` | 重构 ~130 行 | 新增 PermissionEngine + PermissionRule + PermissionDecision + classify_shell_command + DANGEROUS/RISKY_PATTERNS |
| `zcore/cli/main.py` | +80 行 | 新增 skill list/match、run、governance rules/check 子命令 + `_parse_skill_args()` |

---

## 三、分层审查

### Layer 1: 设计与架构 ⭐

#### 👍 亮点

1. **YAML 解析器零依赖实现**（`frontmatter.py`）
   手写递归下降 parser，支持 `|` / `>` block scalar、inline `[list]`、嵌套 dict/list、注释 strip。比引入 PyYAML 依赖轻量得多，且足以覆盖 SKILL.md frontmatter 的语法子集。代码结构清晰：`_parse_block` → `_parse_dict` / `_parse_list` → `_parse_inline_value`。

2. **SkillManifest 的防御式构建**
   每个子 dataclass 都有 `from_dict()` classmethod，所有字段通过 `_coerce_*` 函数容错（None → 默认值、字符串 → int 转换等）。`from_skill_md()` 还添加 `warnings` 列表记录缺失但非致命的字段（如 description 缺失）。

3. **Hook 框架的 pre/post 语义分离**
   pre-hook fail → `return (False, results)` 中止执行；post-hook fail → 不阻塞。这与设计文档完全一致。

4. **权限规则优先级双维度排序**（Codex 自审修复）
   `max(matches, key=lambda: (_DECISION_PRIORITY[decision], _SOURCE_PRIORITY[source]))` — 先按 deny > ask > allow，再按 session > project > global。这是正确的组合优先级。

5. **`parse_known_args` 透传 skill 参数**（Codex 自审修复）
   `zcore run context-engine --message hello` 中 `--message hello` 不会被顶层 argparse 误吞。

#### 🟡 架构观察

- Router、Governance、Hooks 三个模块之间的依赖关系清晰：`router.py` → `lifecycle.py` → `builtin.py` → `governance.py`。没有循环依赖。
- `builtin.py` 同时注册 kebab-case 和 snake_case 形式的 hook 名（`"validate-input"` + `"validate_input"`），提升了容错性。

### Layer 2: 逻辑正确性

#### 🔴 Blocking（0 个）

无阻塞性问题。

#### 🟡 Non-blocking（3 个）

##### 1. `check_permissions` hook 中重复 shell 分类
**位置**：`builtin.py:59-62`
**当前**：`check_permissions` 先调 `engine.check()` → 如果 `check()` 已 allow，再额外调用 `classify_shell_command()` 做二次检测，在 `dangerous` 时再次 fail。
**问题**：`PermissionEngine.check()` 在 `auto` 模式下已经包含 `classify_shell_command()` 调用（`governance.py:142-148`），所以 hook 中的二次分类在 auto 模式下是冗余的。但在 `yolo` 模式下，`check()` 会直接 allow，此时 hook 的二次检测提供了额外防护层。
**建议**：保留当前行为作为 defense-in-depth，但添加注释说明意图：
```python
# Defense-in-depth: even if PermissionEngine allowed (e.g. yolo mode),
# still block dangerous shell commands at the hook layer.
```
**影响**：仅可读性。当前逻辑正确且安全。

##### 2. `_tokenize` 中的 inline `__import__`
**位置**：`router.py:236`
**当前**：`__import__("re").findall(...)` — 在函数体内动态导入 `re`。
**问题**：`re` 已在文件顶部导入（`router.py` 没有，但 `frontmatter.py` 有）。实际上 `router.py` 引入了 `fnmatch` 和 `subprocess` 但没有 `import re`，所以这里用 `__import__` 是刻意规避。
**建议**：在文件顶部添加 `import re`，替换 `__import__("re")`：
```python
import re
# ...
tokens = set(part for part in re.findall(r"[\w\u4e00-\u9fff]+", normalized) if len(part) >= 2)
```
**原因**：`__import__` 在应用代码中是反模式，降低可读性。

##### 3. `log_execution` hook 无原子写入保护
**位置**：`builtin.py:78`
**当前**：直接 `open(log_path, "a")` 追加写入。
**问题**：项目已有 `zcore/utils/fs.py` 提供 `atomic_write_text/json`。不过 JSONL 追加写入的原子性需求与全文件替换不同，append 模式下崩溃最多丢失最后一行，风险较低。
**建议**：记录为已知技术债，后续可考虑 `fcntl.flock` 保护或 `fsync`。当前不阻塞。

### Layer 3: 可读性与风格

#### 💬 Nit（3 个）

- [Nit] `governance.py:84` — `_RULE_RE` 的正则可以加内联注释说明 `action(pattern)` 格式
- [Nit] `router.py:202` — `for trigger in triggers: if trigger and any(trigger in token or token in trigger ...)` 嵌套条件可以提取为 `_trigger_matches(trigger, tokens)` 独立函数
- [Nit] `skill.py:186` — `manifest.lifecycle.post_execute.append("log-execution")` 直接修改了 frozen-ish 对象的内部列表。虽然 dataclass 不是 frozen，但在 `from_skill_md` 这种 classmethod 中修改刚构建的对象是 OK 的，只是可以移到 `from_dict` 内部

### Layer 4: 性能

无性能问题。所有操作都是磁盘 I/O bound（扫描 skill 目录）+ O(n) 遍历，n = skill 数量（通常 < 100）。

### Layer 5: 安全（快速扫描）

| 检查项 | 结果 |
|--------|------|
| 用户输入校验 | ✅ `_parse_skill_args` 正确解析，无注入风险 |
| Shell 命令执行 | ✅ `subprocess.run` 带 `capture_output=True` + `timeout`，不使用 `shell=True` |
| 敏感数据泄露 | ✅ 日志写入 `execution_output` 但不含 API key（上游已 redact） |
| 权限检查 | ✅ pre-hook `check_permissions` + `PermissionEngine.check()` 双层防护 |
| DANGEROUS_PATTERNS 覆盖 | ✅ 14 个危险 + 7 个风险模式，覆盖 rm -rf、sudo、curl\|sh、eval 等 |

---

## 四、与设计文档的偏差分析

### 🟢 完全符合

| 设计要求 | 实现 |
|---------|----|
| SkillManifest dataclass（name, version, description, activation, dependencies, lifecycle, permissions, io）| ✅ 完整实现 |
| 三层路由（关键词 → 路径 → 上下文）| ✅ Layer 1/2/3 评分 + 排序 |
| `SkillRouter.discover()` 搜索 `~/.ai-skills/` + `./.skills/` | ✅ |
| `SkillRouter.match()` 返回排序 `SkillMatch` | ✅ |
| `SkillRouter.activate_conditional()` 路径激活 | ✅ fnmatch 实现 |
| `PermissionRule` dataclass | ✅ |
| `PermissionEngine.check()` 优先级：deny > ask > allow，session > project > global | ✅（Codex 自审修复） |
| `classify_shell_command()` 三级分类 | ✅ dangerous/risky/safe |
| 非 TTY `ask` 快速失败 | ✅ 继承 Phase 0 |
| Hook 链 pre/post 语义 | ✅ |
| 内置 hooks：validate-input, check-permissions, log-execution | ✅ |
| CLI：skill list/match, run, governance rules/check | ✅ |
| `zcore run` 参数透传 | ✅（Codex 自审修复） |

### 🟡 设计文档有但明确延期

| 功能 | 设计文档位置 | 延期到 |
|------|------------|--------|
| YAML Workflow 编排执行器（`Orchestrator` class） | skill-router.md §5 | Phase 4+ |
| `resolve_dependencies()` 方法 | skill-router.md §4 | Phase 4（当前只声明，不实际解析） |
| 零信任签名验签 / 2FA 物理签名 | governance.md §5 | Phase 4+ |
| Ghost Agent 意图审计 hook | governance.md §5.3 | Phase 4+ |
| 自定义 hook 脚本（`~/.zcore/hooks/pre-execute.d/`） | governance.md §3.3 | Phase 4（当前只做 builtin） |
| `check-dependencies` / `dangerous-pattern` / `stale-guardrail` pre-hooks | governance.md §3.2 | Phase 4 |
| `auto-l2-capture` / `cost-track` / `notify-session` post-hooks | governance.md §3.2 | Phase 4 |
| `governance allow/deny` 动态规则管理 CLI | governance.md §7 | Phase 4 |
| `governance log` / `governance audit` CLI | governance.md §7 | Phase 4 |

### 🔵 实现优于设计

| 实现 | 设计未要求但实现了 |
|------|-----------------|
| `frontmatter.py` 支持 block scalar `|` / `>` | 设计标注 "不支持 `|` `>`"，实际实现了 |
| `_coerce_int` 处理 bool/空字符串边界 | 设计未提及，防御式编程 |
| hook 名同时注册 kebab-case + snake_case | 设计未提及，提升兼容性 |
| `SkillManifest.warnings` 字段 | 设计未提及，有助于诊断 |

---

## 五、Codex 自审修复确认

Codex 自审中修复了两个问题，我独立验证了修复的正确性：

| # | 自审修复 | 验证结果 |
|---|---------|---------|
| 1 | `zcore run` 参数透传：`parse_known_args` + unknown args 追加到 `skill_args` | ✅ `main.py:258-260` 实现正确 |
| 2 | 权限规则优先级：先 deny > ask > allow，再 session > project > global | ✅ `governance.py:127` 的 `max(key=...)` 使用双维度排序，`_DECISION_PRIORITY` 和 `_SOURCE_PRIORITY` 值正确 |

---

## 六、测试覆盖分析

| 测试文件 | 测试数 | 覆盖范围 |
|---------|--------|---------|
| `test_zcore_cli.py` | 8 | Phase 0+1+2 CLI |
| `test_zcore_runtime.py` | 3 | Phase 0 runtime |
| `test_zcore_context.py` | 4 | Phase 1 context |
| `test_zcore_ghost_agent.py` | 3 | Phase 1 ghost agent |
| `test_zcore_memory.py` | 5 | Phase 2 memory |
| `test_skill_router.py` | 5 | Phase 3：frontmatter 解析、manifest 构建、三层路由 + execute + hooks、权限优先级、CLI 端到端 |
| **总计** | **28** | Phase 0+1+2+3 全覆盖 |

### 测试质量评价

- `test_skill_manifest_from_real_skill`: 直接读取 `~/.ai-skills/project-manager/SKILL.md`，验证真实 skill 的解析。这是**集成测试**，依赖文件系统状态。
- `test_router_match_activate_and_execute`: 端到端测试了 discover → match → activate_conditional → execute 全流程，包含真实文件 I/O、subprocess 执行和 hook 链验证。覆盖面很宽。
- `test_permission_engine_rule_priority`: 验证了全局 + 项目 + 会话三层规则叠加和优先级 — 覆盖了 Codex 自审修复的核心场景。

---

## 七、已知风险

| # | 风险 | 严重度 | 说明 |
|---|------|--------|------|
| 1 | `test_skill_manifest_from_real_skill` 依赖真实 `~/.ai-skills/` | 🟡 低 | 在无该目录的 CI 环境会失败。建议后续加 `@unittest.skipUnless(Path(...).exists(), ...)` |
| 2 | `check_permissions` hook 在 yolo 模式下是唯一的 shell 危险检测防线 | 🟡 低 | 当前设计合理（defense-in-depth），但应文档化 |
| 3 | `_args_to_cli` 跳过 `timeout` 和 `project` 键 | 🟡 低 | 硬编码的黑名单。如果后续增加更多保留键需要同步更新 |
| 4 | 全仓 `unittest discover` 被历史测试阻塞 | 🟡 中 | 与 Phase 3 本身无关，但会影响 CI 集成。已记录到 PM |

---

## 八、总评

Phase 3 是一次高质量的交付：

- **代码量适中**：~1200 行新增，分布在 7 个新文件 + 2 个修改文件中，模块边界清晰
- **零新依赖**：frontmatter parser（替代 PyYAML）、fnmatch（替代 pathspec）、argparse parse_known_args（替代额外 CLI 框架）—— 保持了零基础设施的架构承诺
- **自审有效**：Codex 的自审发现并修复了 2 个真实问题（参数透传 + 权限优先级），修复质量经独立验证确认正确
- **设计对齐度高**：P0+P1 功能全量实现，延期内容均在 Sprint-Backlog 中明确标记

**结论：✅ 通过，建议进入 Phase 4。**
