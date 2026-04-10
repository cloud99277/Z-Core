---
title: "Phase 2 完成审查报告"
reviewer: gemini (antigravity)
executor: codex
date: 2026-04-10
phase: 2
status: passed
---

# Phase 2 审查报告

> **审查时间**：2026-04-10
> **分支**：`feat/v2`（commit `96b7875`）
> **执行方**：Codex（Phase 2 实现）+ Gemini（审查与提交）

---

## 一、审查结论：✅ 通过

23/23 测试全部通过（1.97s），7 个成功标准全部达标。

| 成功标准 | 状态 |
|---------|:----:|
| `zcore memory extract` 能调用 Ghost Agent 提取或 heuristic 降级 | ✅ |
| 提取结果经过去重检查（编辑距离 + 关键词重叠） | ✅ |
| 置信度 >0.8 自动入库，0.5-0.8 pending，<0.5 丢弃 | ✅ |
| `zcore memory list` 按主题/类型展示记忆 | ✅ |
| `zcore migrate` 迁移 whiteboard.json 到 topics/*.md | ✅ |
| 17 个 Phase 0+1 测试继续通过 | ✅ |
| 新增 ≥6 个 Phase 2 测试 | ✅ (1 CLI + 5 unit = 6) |

---

## 二、新增/修改代码清单

### 新增文件（3 个）

| 文件 | 行数 | 内容 |
|------|------|------|
| `zcore/models/memory.py` | ~85 | MemoryEntry dataclass，4 类分类法，markdown 序列化/正则解析，validation |
| `zcore/prompts/memory_extract.md` | ~30 | 提取 Prompt 模板（4 类说明 + existing_memories 占位 + JSON 输出格式） |
| `tests/test_zcore_memory.py` | ~120 | 5 个测试：roundtrip、store write/read、dedup+auto_topic、heuristic+pending、confirm+migrate |

### 修改文件（6 个）

| 文件 | 变更 | 内容 |
|------|------|------|
| `zcore/engines/memory.py` | 重写 ~400 行 | TopicStore + MemoryEngine（extract/dedup/auto_topic/admit/pending/search/migrate） |
| `zcore/cli/main.py` | +67 行 | memory extract/list/search/pending + migrate 子命令 |
| `zcore/engines/session.py` | +8/-3 | session end 改用 MemoryEngine.extract_from_conversation() |
| `zcore/runtime.py` | +4 | staging_dir + extraction_log_path |
| `zcore/config.py` | +6 | [memory_extraction] 默认配置区块 |
| `tests/test_zcore_cli.py` | +40 | 新增 memory+migrate CLI 端到端测试 |

---

## 三、亮点 ⭐

### 1. TopicStore 设计
markdown 格式的持久化很巧 —— 每行一条 `- [type] content (source, confidence, date)`，用正则 `_MARKDOWN_RE` 解析。人类可直接阅读和编辑 topics/*.md 文件，比 JSON 更友好。

### 2. 提取管线的三级降级
```
Ghost Agent API 可用 → LLM 提取 (JSON 解析)
Ghost Agent 不可用 → heuristic 标记提取 ([decision] [fact] 等)
解析失败 → 空列表 + 日志记录
```
每一级都不会抛异常，保证 session end 流程不中断。

### 3. session end 自动提取集成
`session.py` 改用 `MemoryEngine.extract_from_conversation()` 替代之前 Ghost Agent 的 stub `extract_memories()`，形成完整的 session end → compact + extract → 持久化闭环。

### 4. v1 迁移安全设计
`migrate_v1()` 支持 `--dry-run`，迁移完自动备份 `whiteboard.v1.json.bak` 并删除原文件。FileLock 保护写入。

---

## 四、已知风险（Codex 已同步）

| # | 风险 | 严重度 | 说明 |
|---|------|--------|------|
| 1 | 字符串级去重的语义覆盖有限 | 🟡 低 | difflib 无法识别语义相同但用词不同的条目。留到后续用 embedding 增强 |
| 2 | topic markdown 不保留 pending 条目完整元数据 | 🟡 低 | confirm 后条目从 JSON 转为 markdown 行，丢失 source_session 等详情。可接受 |

---

## 五、测试覆盖分析

| 测试文件 | 测试数 | 覆盖范围 |
|---------|--------|---------|
| `test_zcore_cli.py` | 8 | +1: memory extract→pending→confirm→list→search→migrate CLI |
| `test_zcore_runtime.py` | 3 | 不变 |
| `test_zcore_context.py` | 4 | 不变 |
| `test_zcore_ghost_agent.py` | 3 | 不变 |
| `test_zcore_memory.py` | 5 | roundtrip、store、dedup+topic、heuristic+pending、confirm+migrate |
| **总计** | **23** | Phase 0 + 1 + 2 全覆盖 |

---

## 六、与设计文档的偏差

### 🟢 完全符合
- 4 类分类法（preference/fact/learning/decision）
- 置信度三档过滤（config 可调）
- TopicStore markdown 存储
- Ghost Agent 提取 + heuristic fallback
- 去重（difflib.SequenceMatcher）
- extraction-log.jsonl 日志
- v1 迁移 + dry-run + 备份

### 🟡 延期到后续（符合计划）
- Embedding 语义去重
- Prefetch 预取 / 主动回忆
- 睡眠整理 consolidation
- 时间线 UI
- 流式提取（每 N 轮自动触发）
