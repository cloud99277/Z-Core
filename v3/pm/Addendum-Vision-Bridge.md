# V3 补丁计划：Z-Core Vision Bridge (全局伴侣翻译/解释)

> **Status:** Accepted (Addendum to V3.1 Plan)
> **Date:** 2026-04-27
> **Author:** yangyy

## 1. 战略修正背景

在最初的 V3 规划中，“具身伴侣（RFC-005）”被定义为偏向“情感陪伴与闲聊”的表现层功能（3D数字人、TTS等），并因此被降级推迟至 V3.5+ 甚至独立产品线。

然而，在实际工作流中，存在高频的**“全局名词解释、文档翻译、代码上下文理解”**需求。市面上的工具（如 Pot, uTools, ChatGPT Desktop）虽然优秀，但它们**不具备项目上下文感知能力（Context Awareness）**。

因此，我们需要将“视觉能力（Vision）”从厚重的“具身表现层”中解耦出来，作为一个轻量级、高 ROI 的“能力层（Sensor）”插件，提前在 V3.1 落地。这就是 **Z-Core Vision Bridge**。

## 2. 核心价值与定位

- **不是“翻译工具”**，而是**“项目感知的 AI 解释器（Tutor Mode）”**。
- 当开发者选中/截图屏幕上的 `Reconciliation` 时，Vision Bridge 不仅翻译为“和解”，还会结合 Z-Core 的 `Current-State.md` 告诉开发者：“在你当前的 React 重构中，这指的是虚拟 DOM 对比算法。”
- **无缝闭环记忆**：所有查询过的生词、复杂概念，都会被 Z-Core 记录到 `~/.zcore/memory/`，下次编码时自动辅导。

## 3. 轻量化实现路径 (MVP)

采取“非侵入式、极简桥接”的架构，放弃重型 GUI。

### Phase 1: The Eye (视觉抓取)
- **Windows 侧代理**：一个极简的 Python 脚本，注册全局快捷键（如 `Alt + Space`）。
- **流程**：快捷键触发 → 调用 Windows 原生截图命令行 / `pyautogui` → 截取指定区域。

### Phase 2: The Brain (上下文注入与识别)
- **WSL2 侧接口**：Windows 侧将截图图片直接通过 HTTP/Socket 发给 WSL2 内的 Z-Core 进程（或保存到共享目录 `\\wsl.localhost\...`触发监控）。
- **LLM 路由**：Z-Core 截获图片，附加上下文（`Current-State.md`, 工作空间路径），发送给 `Gemini 1.5 Flash`（保证 2s 内低延迟返回）。

### Phase 3: The Voice (可选反馈)
- **极简 UI**：采用 Windows Toast 通知，或极简的 Tkinter/PyQt 悬浮窗显示结果。
- **TTS 语音**：调用 Edge-TTS（免费极速），用伴侣的声音直接读出解释。

## 4. PM 计划调整

- **V3.0 MVP**：维持不变（Harvester + GhostAgent），保证当前 Sprint 聚焦。
- **V3.1**：将 **Z-Core Vision Bridge (The Eye & Brain)** 正式纳入 V3.1 的 Sprint 目标，与 Planner Engine 并行开发。
- **V3.5+**：重型表现层（The Avatar，Live2D/3D 皮套）继续留在 V3.5+ 或独立项目。

## 5. 下一步行动

1. 确认 V3.0 MVP 完成后，优先启动 `skill-vision-interpret` 的开发。
2. 搭建 Windows <-> WSL2 的轻量级图片/文本通信原型。
