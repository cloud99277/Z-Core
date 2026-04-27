# Gemini 修复记录 - 2026-04-25

## 修复目标
完成 Codex 遗留的配置刷新任务，并彻底解决 CLI 在 JSON 模式下的 Traceback 问题。

## 已执行的修复
1. **配置全量刷新**:
   - 执行 `zcore setup all`。
   - 成功更新本地 `~/.gemini/GEMINI.md`、`~/.claude/CLAUDE.md` 及 `AGENTS.md`。
   - 确认集成指令已包含 `--messages` 参数。

2. **全局异常捕获补齐**:
   - 对 `zcore/cli/main.py` 进行了结构化重构。
   - 引入了全局 `try...except` 包装器。
   - 确保当 `--json` 启用时，任何未捕获的异常（如 `FileNotFoundError`, `ValueError`, `ImportError`）均通过 `_emit_error` 输出干净的 JSON 负载，不再泄露 Python Traceback。

3. **验证测试**:
   - 测试命令: `zcore context analyze --model gpt-4 --input non_existent.json --json`
   - 结果: 输出 `{"ok": false, "error": "[Errno 2] No such file or directory: 'non_existent.json'"}`，退出码 1。

## 修复总结
至此，Z-Core 的基础集成稳定性已显著提升。Agent 现在可以正确引导用户保存上下文，且 CLI 在作为中间件调用时具有更强的健壮性。
