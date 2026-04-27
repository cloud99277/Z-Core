# Z-Core Session 体系优化建议 - 2026-04-25

## 当前痛点 (Current Pain Points)
1. **指令非标准化**: 集成到 Agent (CLAUDE.md/GEMINI.md) 中的指令过于口语化（如 "保存对话为 JSON"），缺乏原子操作的严谨感，容易导致 Agent 执行偏差。
2. **查询维度匮乏**: 缺乏对会话内容的检索能力（session search），只能通过 ID 或时间戳硬找。
3. **摘要质量不足**: 现有的 `summary` 字段仅为简单截断，未充分利用 `compact.md` 生成的结构化报告，导致任务上下文丢失。
4. **人类可读性差**: Session ID (Hex) 难以记忆，缺乏 Alias 或 Semantic Label 支持。
5. **对话导出可靠性缺失 (Transcript Integrity)**: 目前依赖 Agent "默写" 历史记录为 JSON。由于 Agent 无法直接导出系统级 transcript，且受限于输出长度，经常导致仅保存了 "一问一答" 而非完整对话，导致 Session 历史断裂。

## 核心设计哲学: 从“独立存储”到“集成收割机” (Integration over Redundancy)
为了避免与现有工具（如 Claude Code, Hermes）功能重复，Z-Core 的定位应明确为 **AI Agent 的中间件加工层**：
- **收割 (Ingest)**: 不再强制要求 Agent 导出 JSON，而是由 Z-Core 自动读取宿主 Agent 的原始日志（如 `~/.claude/sessions/` 或 `.hermes/sessions/`）。
- **加工 (Process)**: 将原始流水账压缩为高价值的结构化资产（Technical Decisions, L2 Facts）。
- **分发 (Sync)**: 将加工后的记忆同步给其他 Agent，打破孤岛历史，实现跨 Agent 的上下文接力。

## 改进建议 (Proposed Enhancements)
1. **标准化报告输出与管理**:
   - 增强 `zcore session show`，默认渲染结构化 Markdown 摘要。
   - 增加 `zcore session report` 和 `zcore session rename` (Alias) 功能。
2. **自动化收割器 (The Harvester)**:
   - 开发 `zcore session ingest --source <claude|hermes|cursor>`，实现从本地 Agent 环境一键提取 transcript，解决 "一问一答" 记录残缺问题。
3. **全文搜索能力**:
   - 实现 `zcore session search`，通过对 `context.md` (压缩后的摘要) 进行检索，实现跨会话知识定位。
4. **指令集重定义 (Protocol over Prompt)**:
   - 在 `agent_setup.py` 中将指令改为“协议描述”，明确 Z-Core 作为记忆中继的地位。

## 决策记录
- [2026-04-25] 用户 yangyy 确认上述痛点并要求启动优化规划。
- [2026-04-25] 发现 Codex/Agent 记录残缺问题。确定原因为 "Agent 侧缺乏 transcript 自动导出工具"。
- [2026-04-25] **架构调整**: 确立“集成收割机”思路，避免与 Claude Code 等工具重复存储，转向“接入-加工-分发”模型。
