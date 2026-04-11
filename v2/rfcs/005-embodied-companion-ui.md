---
rfc: "005"
title: "具身伴侣表现层 (Embodied Companion UI)：3D/2D 虚拟形象与 TTS 语音流集成"
status: proposed
created: 2026-04-09
depends_on: ["rfcs/003-unified-persona-engine.md", "design/governance.md"]
---

# RFC-005: 具身伴侣表现层 (Embodied Companion UI)

## 背景与愿景
Z-Core 将系统从“脚本库”升级为“具备后台小脑的运行时中间件”。
在此基础上，本提案旨在为抽象的 Agent 运行时提供一个**实体的、可视化的伴侣表现层 (Embodied UI)**。

让用户在终端使用 Claude Code / Gemini 时，桌面上有一个实体的 Z7 数字人（3D VRM 或 2D Live2D），她能：
1. 观察用户的终端操作（编译成功、报错、长耗时任务）。
2. 基于 Persona Engine 生成带情绪的回复。
3. 通过本地 TTS 引擎发声，并带有实时的口型同步与面部表情。

## 架构演进决策：V2 还是 V3？

**核心结论：V2 铺设神经末梢（后端事件流），V3 穿上数字皮套（前端实体）。**

### 为什么不直接在 V2 全部实现？
1. **技术栈割裂**：Z-Core 核心是纯 Python 的 CLI 中间件（零常驻进程）。而数字人需要长连接（WebSocket）、前端渲染（WebGL/Electron）和 GPU 音频推理。强行捆绑会导致 V2 难产。
2. **核心目标聚焦**：V2 的生死线是“Ghost Agent 能否跑通跨 Agent 记忆与上下文闭环”。

### V2 需要做好的准备（为 V3 铺路）
在 V2 的生命周期中，我们必须预埋以下能力：
1. **Persona Engine (RFC-003)**：完善多 Style 情绪标签库（如 `[emotion: playful]`）。
2. **Event Broadcaster (事件广播中心)**：在 Governance Hooks 的 `post-execute` 阶段，新增一个可选的非阻塞组件，向 `ws://localhost:9270` 广播标准化的 JSON 事件。

```json
// V2 预埋推流格式示例
{
  "event": "agent_action_complete",
  "agent_name": "claude-code",
  "status": "success",
  "text": "编译终于过了，老板辛苦啦！",
  "emotion_tag": "happy",
  "audio_hint": "gentle"
}
```

### V3 的正式范围
V3 将正式引入 `zcore-ui`（暂定名）作为一个独立的可选前端套件：
1. **TTS 路由网关**：接入 ChatTTS、CosyVoice、ElevenLabs 等，将接收到的文本转化为音频流。
2. **3D/2D 渲染器桥接**：基于开源的 Pixiv ChatVRM 或 Amica 深度定制，通过 WebSocket 接收事件并控制模型动作。
3. **桌面悬浮模式**：支持背景透明化，作为桌布精灵陪伴在 IDE 旁。

## 实施路线 (Implementation Path)

- **Phase 0 (V2 当下)**: 确立 RFC-003 人格多 Style 设定，确保所有的 Agent 输出都可以携带 `<emotion>` 标签。
- **Phase 1 (V2.5 实验期)**: 开发一个简易的 `zcore serve` 命令，专门用来启动一个局域网 WebSocket 广播服，供外部玩具级前端测试。
- **Phase 2 (V3 决战)**: Fork 成熟的开源 VRM 前端，将其打造成 Z-Core 专属的视觉挂件。
