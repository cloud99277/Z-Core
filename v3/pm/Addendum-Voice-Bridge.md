# V3 补丁计划：Z-Core Voice Bridge（双向语音交互桥）

> **Status:** Proposed (Addendum to V3 Roadmap)
> **Date:** 2026-04-29
> **Author:** yangyy
> **RFC:** v3/pm/rfc-006-voice-bridge.md

## 1. 战略背景

在最初的 V3 规划中，RFC-005（具身伴侣表现层）定义了 **单向** 语音输出（Agent → TTS → 用户），
Vision Bridge Addendum 定义了 **单向** 视觉输入（截图 → LLM → 解释）。

但 Z-Core 的具身交互缺少一个关键维度：**用户用语音驱动 Z-Core 执行操作**。

参考 OpenAI 开源的 realtime-voice-component（2026-04-15），其 VoiceTool 模式
（Zod schema 定义工具 → Controller 执行 → 反馈）与 Z-Core 的 skill 体系高度对齐。
该组件当前绑定浏览器 WebRTC，但其核心抽象（VoiceTool、Controller 生命周期、Transport 接口）
是可移植的服务端设计。

## 2. 核心定位

Voice Bridge 不是"语音助手"，而是 **Z-Core skill 体系的语音入口**：

- 文本模式：`zcore session search --query "认证方案"` → 文字结果
- 语音模式：用户说"搜一下认证方案" → 调用同一个 session search skill → 语音读出结果

**同一个 skill，两种入口。** Voice Bridge 只是增加了一层 ASR/TTS + 意图路由。

## 3. 与 Vision Bridge 的对称关系

| | Vision Bridge (已有) | Voice Bridge (新增) |
|---|---|---|
| **输入** | 屏幕截图 | 用户语音 |
| **处理** | Z-Core + LLM 解释 | Z-Core + 意图路由 + Skill 执行 |
| **输出** | Toast 文字 / TTS | 语音 / 文本 |
| **交互** | 单向（用户看屏幕 → AI 解释） | 双向（用户说话 ↔ AI 执行+反馈） |
| **Phase** | V3.2 | V3.2（并行） |

两者可组合：用户截了一个报错截图，语音问"这个错误怎么修"。

## 4. 轻量化实现路径 (MVP = Phase 1)

### Phase 1: The Ear & Mouth（V3.2）

**ASR**：Whisper base 模型（本地、中文可用、~1s 延迟）
**TTS**：Edge-TTS（免费、微软中文声线质量好、~1s 延迟）
**意图路由**：别名匹配 + 关键词匹配（不依赖 LLM，<100ms）
**Skill 发现**：自动扫描 `~/.ai-skills/` 目录

端到端延迟目标：< 3s

```bash
pip install -e ".[voice]"
zcore voice start
# → "Z7 在听，说吧..."
# 用户："搜一下昨天的架构决策"
# → 调用 session search skill → 语音读出结果
```

### Phase 2: The Brain（V3.3）

- GhostAgent LLM 意图理解（fallback）
- 多轮对话上下文
- FunASR / ChatTTS 更高质量后端

### Phase 3: The Skin（V3.5）

- 唤醒词（"z7"）
- OpenAI Realtime 低延迟模式
- 对接具身伴侣 Avatar 口型同步

## 5. PM 计划调整

- **V3.1**：不变。RFC-006 方案确立，config.toml 预留 `[voice]` 空区块
- **V3.2**：Voice Bridge Phase 1（The Ear & Mouth）与 Vision Bridge 并行开发
- **V3.3**：Voice Bridge Phase 2（The Brain）
- **V3.5**：Voice Bridge Phase 3（The Skin）+ 对接 RFC-005 具身伴侣

## 6. 依赖与风险

**新增依赖（可选 extra，不破坏零依赖核心）：**
- `sounddevice` — 麦克风采集
- `openai-whisper` 或 `faster-whisper` — 本地 ASR
- `edge-tts` — 免费 TTS

**最大风险：** WSL2 下音频采集的兼容性（PulseAudio / PipeWire）。
**缓解：** Phase 1 同时支持文件输入模式（`zcore voice start --from-file audio.wav`），
确保在音频采集不可用时仍可测试 ASR/TTS 链路。
