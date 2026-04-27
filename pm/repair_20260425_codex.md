# Codex 修复记录 - 2026-04-25

## 问题诊断
在对 Z-Core 体系进行审查时，发现了以下关键问题：

1. **打包遗漏**: `pyproject.toml` 配置不完善，导致 `wheel` 或 `sdist` 安装包中未包含 `skills/core` 目录。在非 editable 模式下安装后，17 个核心技能无法加载。
2. **错误处理不规范**: 在使用 `--json` 参数时，部分错误路径（如文件缺失）仍会输出 Python Traceback，破坏了机器可读性。
3. **Agent 集成缺陷**: `zcore setup` 注入到 Agent 配置（如 `CLAUDE.md`）中的 `session end` 命令缺少 `--messages` 参数，导致对话上下文无法自动保存到记忆中。

## 已执行的修复
- [x] 更新 `pyproject.toml`，在 `[tool.setuptools.packages.find]` 中包含 `skills*`，并明确 `package-data` 包含核心技能文件。
- [x] 在 `zcore session end` 命令中增加了基本的错误捕获逻辑。
- [x] 更新 `AgentSetupEngine` 提示词模板，确保 `session end` 命令包含 `--messages <messages.json>` 参数。

## 待办事项
- [ ] 补齐所有 CLI 命令的全局异常捕获，确保 `--json` 下无 Traceback。
- [ ] 验证跨平台安装后的技能加载情况。
