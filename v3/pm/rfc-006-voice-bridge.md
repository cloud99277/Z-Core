---
rfc: "006"
title: "Voice Bridge（语音交互桥）：Z-Core 双向语音交互层"
status: proposed
created: 2026-04-29
depends_on: ["v2/rfcs/003-unified-persona-engine.md", "v2/rfcs/005-embodied-companion-ui.md", "v3/pm/Addendum-Vision-Bridge.md"]
---

# RFC-006: Voice Bridge（语音交互桥）

## 背景与动机

### 现状

Z-Core V3.0 已完成 Harvester 收割机、GhostAgent 角色切换、隐私脱敏管线、Session 全文搜索。
V3.1 正在扩展三大 Agent Adapter + FTS5 索引。

当前 Z-Core 的交互模型是 **纯文本 CLI**：用户打字 → Agent 执行 → 文本输出。

### 缺口

RFC-005（具身伴侣表现层）设计了 **单向** 语音输出：
```
Agent 事件 → Persona Engine → TTS → 用户听到
```

Vision Bridge Addendum 设计了 **单向** 视觉输入：
```
用户截图 → LLM 解释 → 文字/TTS 反馈
```

但两者都不具备 **语音输入 → 理解 → Tool 执行 → 语音反馈** 的双向闭环能力。

### 参考实现

OpenAI 开源了 [realtime-voice-component](https://github.com/openai/realtime-voice-component)（2026-04-15），其核心模式值得借鉴：

```
defineVoiceTool(Zod schema) → VoiceControlController → Tool 执行 → 反馈
```

该组件当前绑定浏览器（WebRTC），但其 **VoiceTool 模式** 和 **Controller 生命周期** 是可移植的。

---

## 问题定义

需要一个语音交互层，使得：

1. **语音输入** — 用户可以通过麦克风对 Z-Core 说话（ASR）
2. **意图理解** — 语音转文字后，理解用户想执行什么操作
3. **Skill 调用** — 将意图映射到 Z-Core 已有的 skill 体系并执行
4. **语音反馈** — 执行结果通过 TTS 读出，配合情绪标签（对接 Persona Engine）
5. **双向对话** — 支持多轮语音交互，不只是单次指令
6. **多后端** — 不绑定 OpenAI Realtime，支持本地 ASR（Whisper/FunASR）+ 本地 TTS（Edge-TTS/ChatTTS）

---

## 选择

**选项 A：直接用 OpenAI Realtime API（WebRTC 或 WebSocket）。**
- 优点：端到端延迟最低（~300ms），天然支持 function calling
- 缺点：绑定 OpenAI，需要 API key，无法离线，中文支持有限
- 投入：低
- 上限：中

**选项 B：ASR + LLM + TTS 三段式架构（推荐）。**
- ASR 层：可插拔（Whisper / FunASR / Paraformer / OpenAI Realtime）
- LLM 层：复用 GhostAgent（Gemini Flash / Claude Haiku / 本地模型）
- TTS 层：可插拔（Edge-TTS / ChatTTS / CosyVoice / ElevenLabs）
- 优点：完全解耦，可离线，中文 ASR/TTS 选择丰富，与 Z-Core skill 体系天然对齐
- 缺点：端到端延迟较高（~1-3s），需要自己做意图路由
- 投入：中等
- 上限：高

**选项 C：混合同级 — 默认三段式，可选 Realtime 直连。**
- 选项 B 作为默认架构
- 通过 `RealtimeTransport` 接口抽象，允许切换到 OpenAI Realtime WebSocket 模式
- 投入：中等偏高
- 上限：最高

---

## 决定

**选择 C：混合同级架构。**

理由：
1. 与 Z-Core "零外部依赖"的核心原则兼容（默认用本地 ASR/TTS）
2. 不排除 OpenAI Realtime 的低延迟优势（作为可选后端）
3. VoiceTool 模式与 Z-Core skill 体系天然对齐
4. Persona Engine 的情绪标签可以直接注入 TTS 控制

---

## 具体设计

### 1. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    Voice Bridge                          │
│                                                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐           │
│  │ ASR Layer│───→│  Intent  │───→│  Skill   │           │
│  │ (可插拔)  │    │  Router  │    │ Executor │           │
│  └──────────┘    └──────────┘    └──────────┘           │
│       ↑               │               │                  │
│       │          ┌────┴────┐          ↓                  │
│  ┌────┴────┐     │ Persona │    ┌──────────┐            │
│  │ Audio   │     │ Engine  │    │ Z-Core   │            │
│  │ Capture │     │ (情绪)   │    │ Skills   │            │
│  └─────────┘     └────┬────┘    └──────────┘            │
│                       │                                  │
│                       ↓                                  │
│                  ┌──────────┐                            │
│                  │ TTS Layer│                            │
│                  │ (可插拔)  │                            │
│                  └──────────┘                            │
└─────────────────────────────────────────────────────────┘
```

### 2. 核心抽象

#### 2.1 VoiceSkill（语音可调用技能）

借鉴 realtime-voice-component 的 `defineVoiceTool()` 模式，
将 Z-Core 已有 skill 通过声明式方式暴露给语音层：

```python
from dataclasses import dataclass
from typing import Any, Callable

@dataclass
class VoiceSkill:
    """语音可调用的 Z-Core Skill"""
    name: str                           # "search_memory"
    description: str                    # "搜索历史记忆"
    parameters: dict                    # JSON Schema 格式参数定义
    handler: Callable[..., Any]         # 实际执行函数
    confirm_before: bool = False        # 是否需要语音确认（危险操作）
    voice_aliases: list[str] = None     # 语音别名 ["搜记忆", "查历史"]

# 示例：将已有 skill 暴露为 VoiceSkill
search_memory_skill = VoiceSkill(
    name="search_memory",
    description="搜索 Z-Core 跨 Agent 历史记忆",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"}
        },
        "required": ["query"]
    },
    handler=lambda query: zcore_memory_search(query),
    voice_aliases=["搜记忆", "查历史", "找一下"]
)
```

#### 2.2 ASR Provider（语音识别后端）

```python
from abc import ABC, abstractmethod

@dataclass
class TranscriptionResult:
    text: str
    language: str | None = None
    confidence: float | None = None
    is_final: bool = True

class ASRProvider(ABC):
    """语音识别后端接口"""

    @abstractmethod
    def start_stream(self) -> None:
        """开始音频流"""
        ...

    @abstractmethod
    def feed_audio(self, audio_chunk: bytes) -> TranscriptionResult | None:
        """喂入音频数据，返回中间或最终识别结果"""
        ...

    @abstractmethod
    def end_stream(self) -> TranscriptionResult:
        """结束音频流，返回最终识别结果"""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...
```

实现：
- `WhisperASRProvider` — 本地 OpenAI Whisper（`whisper` Python 包）
- `FunASRProvider` — 阿里 FunASR（本地或 API）
- `OpenAIRealtimeASR` — OpenAI Realtime API（WebSocket 模式）

#### 2.3 TTS Provider（语音合成后端）

```python
class TTSProvider(ABC):
    """语音合成后端接口"""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        emotion: str | None = None,    # 来自 Persona Engine 的情绪标签
        voice: str | None = None,      # 声线选择
        speed: float = 1.0,
    ) -> bytes:
        """合成语音，返回音频数据（WAV/MP3）"""
        ...

    @abstractmethod
    def list_voices(self) -> list[dict]:
        """列出可用声线"""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...
```

实现：
- `EdgeTTSProvider` — 微软 Edge-TTS（免费、快速、中文效果好）
- `ChatTTSProvider` — 开源 ChatTTS（本地、可控情绪）
- `CosyVoiceProvider` — 阿里 CosyVoice（本地、中文自然度高）
- `ElevenLabsProvider` — ElevenLabs（付费、最高质量）

#### 2.4 IntentRouter（意图路由器）

```python
class IntentRouter:
    """将用户语音文本映射到 VoiceSkill 调用"""

    def __init__(self, skills: list[VoiceSkill], llm_backend=None):
        self.skills = {s.name: s for s in skills}
        self.aliases = self._build_alias_map(skills)
        self.llm_backend = llm_backend

    def route(self, text: str) -> SkillCall | ConversationReply:
        """
        路由策略（三级）：
        1. 精确匹配：语音别名直接命中 → 立即执行
        2. 关键词匹配：提取关键词匹配 skill description
        3. LLM 理解：用 GhostAgent 做意图分类（fallback）
        """
        # Level 1: 别名匹配
        match = self._match_alias(text)
        if match:
            return SkillCall(skill=match, args=self._extract_args(text, match))

        # Level 2: 关键词匹配
        match = self._match_keywords(text)
        if match:
            return SkillCall(skill=match, args=self._extract_args(text, match))

        # Level 3: LLM 意图理解（GhostAgent compact role）
        if self.llm_backend:
            return self._llm_route(text)

        return ConversationReply(text=f"我不太确定你想做什么：{text}")
```

### 3. VoiceBridge 主控

```python
class VoiceBridge:
    """Z-Core 语音交互桥主控"""

    def __init__(self, config: VoiceConfig):
        self.asr = config.asr_provider
        self.tts = config.tts_provider
        self.router = IntentRouter(config.skills, config.llm_backend)
        self.persona_engine = config.persona_engine  # 对接 RFC-003
        self.session = VoiceSession()

    async def run(self):
        """主循环"""
        self.asr.start_stream()
        while self.session.active:
            audio = await self.capture_audio()
            result = self.asr.feed_audio(audio)

            if result and result.is_final:
                response = await self.handle_utterance(result.text)
                audio_data = self.tts.synthesize(
                    text=response.text,
                    emotion=response.emotion,  # 来自 Persona Engine
                )
                await self.play_audio(audio_data)

    async def handle_utterance(self, text: str) -> VoiceResponse:
        """处理一次语音输入"""
        # 上下文注入（复用 Z-Core L1/L2/L3）
        context = self.session.get_context()

        # 意图路由
        intent = self.router.route(text)

        if isinstance(intent, SkillCall):
            # 危险操作需要确认
            if intent.skill.confirm_before:
                confirm = await self.ask_confirmation(intent)
                if not confirm:
                    return VoiceResponse(text="好的，已取消。", emotion="neutral")

            # 执行 skill
            result = await intent.skill.handler(**intent.args)
            self.session.add_turn(text, result)

            # Persona Engine 决定情绪
            emotion = self.persona_engine.infer_emotion(text, result)

            return VoiceResponse(
                text=self.format_result(result),
                emotion=emotion,
            )
        else:
            # 非 skill 意图，走对话模式
            return VoiceResponse(text=intent.text, emotion="gentle")
```

### 4. 配置

`~/.zcore/config.toml` 新增 `[voice]` 区块：

```toml
[voice]
enabled = false                     # 默认关闭，需手动启用
activation_mode = "push-to-talk"    # push-to-talk | vad | wake-word
wake_word = "z7"                    # 唤醒词（wake-word 模式）

[voice.asr]
provider = "whisper"                # whisper | funasr | openai-realtime
model = "base"                      # whisper 模型大小
language = "zh"                     # 识别语言

[voice.tts]
provider = "edge-tts"               # edge-tts | chattts | cosyvoice | elevenlabs
voice = "zh-CN-XiaoyiNeural"        # 声线
speed = 1.0
emotion_from_persona = true         # 是否根据 Persona Engine 调整语气

[voice.skills]
auto_discover = true                # 自动从 ~/.ai-skills/ 发现可用 skill
confirm_dangerous = true            # 危险操作（git push、删除文件）需要语音确认
max_history = 50                    # 语音会话历史保留条数
```

### 5. CLI 命令

```bash
# 启动语音交互
zcore voice start

# 测试 ASR 后端
zcore voice test-asr --provider whisper --duration 5

# 测试 TTS 后端
zcore voice test-tts --provider edge-tts --text "你好，我是Z7"

# 查看已注册的语音技能
zcore voice skills list

# 手动注册/取消语音技能
zcore voice skills enable search_memory
zcore voice skills disable git_push

# 查看语音交互历史
zcore voice history [--last 20]
```

### 6. 与现有 Z-Core 组件的集成点

| Z-Core 组件 | Voice Bridge 集成方式 |
|---|---|
| **Skill 系统** (`~/.ai-skills/`) | 自动扫描 SKILL.md，生成 VoiceSkill 注册 |
| **Persona Engine** (RFC-003) | 情绪标签注入 TTS 合成参数 |
| **GhostAgent** | 用 compact role 做意图理解 fallback |
| **L2/L3 记忆** | 语音查询记忆、语音结果写入记忆 |
| **Harvester** | 语音交互记录可被收割为会话数据 |
| **Governance Hooks** | 语音操作走同一套权限规则 |
| **Event Broadcaster** (RFC-005) | 语音事件广播给具身伴侣 UI |

### 7. 与 RFC-005（具身伴侣）的关系

Voice Bridge 是 RFC-005 的 **前置能力层**，两者独立演进但可组合：

```
RFC-005 事件广播（ws://localhost:9270）
    ↓
┌───────────────────────────────┐
│         具身伴侣 UI           │
│  ┌─────────┐  ┌───────────┐  │
│  │ 3D/2D   │  │  Voice    │  │
│  │ Avatar  │  │  Bridge   │  │  ← RFC-006
│  └─────────┘  └───────────┘  │
└───────────────────────────────┘
```

- **无具身伴侣时**：Voice Bridge 独立运行（终端模式，纯语音 + 文本反馈）
- **有具身伴侣时**：Voice Bridge 接管语音输入/输出，Avatar 负责视觉表现

---

## 实施路线

### Phase 0：V3.1 准备期（当前 Sprint）

- 确立 RFC-006 方案
- 在 `config.toml` 预留 `[voice]` 区块（空配置，不实现）
- 事件广播器（Event Broadcaster）增加 `voice.*` 事件类型定义

### Phase 1：V3.2 MVP — The Ear & Mouth

**目标**：最小可用的语音交互闭环

- 实现 `VoiceBridge` 核心循环
- ASR：`WhisperASRProvider`（本地，中文 base 模型）
- TTS：`EdgeTTSProvider`（免费，中文效果好）
- IntentRouter：Level 1（别名匹配）+ Level 2（关键词匹配）
- 自动从 `~/.ai-skills/` 发现并注册 VoiceSkill
- CLI：`zcore voice start / test-asr / test-tts`
- 测试：≥ 10 个用例

**端到端延迟目标**：< 3s（ASR ~1s + Intent ~0.1s + Skill ~0.5s + TTS ~1s）

### Phase 2：V3.3 增强 — The Brain

- IntentRouter Level 3：GhostAgent LLM 意图理解
- 多轮对话上下文（VoiceSession 持久化）
- 语音确认流程（危险操作）
- ASR 扩展：FunASR Provider（更高中文精度）
- TTS 扩展：ChatTTS / CosyVoice Provider（本地、可控情绪）

### Phase 3：V3.5 高级 — The Skin

- 唤醒词支持（对接 Picovoice Porcupine）
- OpenAI Realtime WebSocket Transport（低延迟模式）
- 对接具身伴侣 UI（RFC-005 Avatar 口型同步）
- 语音操作的 Ghost Cursor 视觉反馈
- 方言/多语言支持

---

## 影响

### 需要新建

- `zcore/voice/` — Voice Bridge 核心模块
  - `bridge.py` — VoiceBridge 主控
  - `asr/` — ASR Provider 接口 + 实现
  - `tts/` — TTS Provider 接口 + 实现
  - `intent.py` — IntentRouter 意图路由
  - `session.py` — VoiceSession 语音会话管理
  - `types.py` — VoiceSkill、TranscriptionResult 等类型
- `zcore/cli/voice.py` — `zcore voice` CLI 子命令
- `config.toml` 的 `[voice]` 区块
- 测试文件

### 需要修改

- `v2/design/architecture.md` — Engine Layer 增加 Voice Bridge
- Event Broadcaster（RFC-005）增加 `voice.*` 事件类型
- `zcore/hooks/` — 语音操作走 Governance Hooks

### 依赖

| 依赖 | 必需/可选 | 说明 |
|------|----------|------|
| `openai-whisper` 或 `faster-whisper` | 可选 | 本地 ASR |
| `edge-tts` | 可选 | 本地 TTS（免费） |
| `sounddevice` 或 `pyaudio` | 必需 | 麦克风音频采集 |
| `numpy` | 可选 | 音频处理（whisper 需要） |

**注意**：Voice Bridge 作为可选模块，不影响 Z-Core 零依赖核心。
通过 `pip install -e ".[voice]"` 安装语音依赖。

### 风险

| 风险 | 缓解 |
|------|------|
| ASR 中文识别精度不足 | 多后端可切换，FunASR 中文效果优于 Whisper |
| 端到端延迟过高（>5s） | Phase 1 用轻量模型（whisper base），Phase 3 引入 Realtime |
| 音频采集依赖系统库 | `sounddevice` 比 `pyaudio` 更易安装，fallback 到文件输入 |
| 语音误识别导致误操作 | confirm_dangerous=true + 操作前语音确认 |
| Z-Core 零依赖原则被破坏 | voice 作为可选 extra，不装 voice 依赖时核心功能不受影响 |

---

## 开放问题

1. **唤醒词方案**：Picovoice Porcupine（商业授权）vs 本地 Vosk/Snowboy vs 纯 ASR 关键词检测？Phase 1 先用 push-to-talk，唤醒词留到 Phase 3。
2. **音频格式**：统一用 16kHz PCM16 还是各 Provider 自行处理？建议统一输入格式。
3. **语音会话持久化**：VoiceSession 是否需要像 TextSession 一样被 Harvester 收割？建议是，格式兼容 `IngestedSession`。
4. **移动端支持**：Z-Core 目前是 WSL/Linux CLI，语音采集在 WSL 下是否有额外坑？需要实测 `sounddevice` 在 WSL2 + PulseAudio 下的表现。
5. **与 OpenClaw/Hermes 的语音能力重叠**：Hermes 已有 TTS（text_to_speech 工具），OpenClaw 有 Voice 系统。Voice Bridge 是统一层还是各自独立？建议 Voice Bridge 作为 Z-Core 层统一提供，Agent 各自的语音能力作为 fallback。

---

## 附录 A：替代方案 — 基于 Pipecat 引擎的实现路径

> **状态**：备选方案，待对比评估
> **提出日期**：2026-04-29
> **参考**：[pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat)、[livekit/agents](https://github.com/livekit/agents)

### A.1 背景

方案 A（原方案）选择从零搭建三段式架构（ASR + IntentRouter + TTS），需要自研：
- ASR Provider 接口 + Whisper/FunASR 实现
- IntentRouter 三级路由（别名 → 关键词 → LLM）
- TTS Provider 接口 + Edge-TTS/ChatTTS 实现
- 音频采集、播放、格式转换

然而，开源社区已有成熟框架 **Pipecat** 完整解决了这条链路，
且额外提供了原生 Speech-to-Speech（S2S）+ Function Calling 能力——这是方案 A 没有覆盖的。

### A.2 Pipecat 概况

Pipecat 是 Daily 团队开源的 Python 实时语音+多模态 AI Agent 框架（Apache-2.0）。

**已集成的 S2S 端到端服务（语音直入直出，无需 ASR/TTS 拆分）：**
- OpenAI Realtime API（WebSocket 模式，非浏览器绑定）
- Google Gemini Live API
- AWS Nova Sonic
- Grok Voice Agent
- Ultravox

**已集成的传统三段式服务：**
- STT（18+）：Whisper、Deepgram、AssemblyAI、Google、Azure、FunASR...
- LLM（20+）：OpenAI、Anthropic、Gemini、DeepSeek、Ollama、Qwen...
- TTS（25+）：Edge-TTS、Cartesia、ElevenLabs、Fish、Kokoro、ChatTTS、CosyVoice...

**传输层：**
- WebRTC（Daily、LiveKit）
- WebSocket（FastAPI）
- 本地（Local Transport，不需要网络）

**关键能力：**
- S2S 模式下原生 function calling（语音 → LLM 直接调用工具，不需要额外的意图路由层）
- 语义 VAD（Silero 模型判断用户是否说完）
- Pipeline 模式（模块化组合 ASR/LLM/TTS/S2S）
- 多 Agent 子系统（pipecat-subagents）

### A.3 方案 B 架构：Z-Core Skill 适配层 + Pipecat 引擎

```
┌─────────────────────────────────────────────────────────────┐
│  Z-Core Voice Bridge（薄适配层，~200 行）                    │
│                                                              │
│  ┌──────────────────┐  ┌────────────────┐                   │
│  │ Skill→FunctionSchema│  │ Persona→TTS  │                   │
│  │ 转换器             │  │ emotion 注入  │                   │
│  └──────────────────┘  └────────────────┘                   │
│  ┌──────────────────┐  ┌────────────────┐                   │
│  │ L2/L3 → system    │  │ Harvester     │                   │
│  │ instruction 注入  │  │ 对话收割钩子   │                   │
│  └──────────────────┘  └────────────────┘                   │
└────────────────────────┬────────────────────────────────────┘
                         │ 调用
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  Pipecat（引擎层，不修改）                                   │
│                                                              │
│  S2S 模式（低延迟 ~300ms）：                                 │
│    OpenAI Realtime / Gemini Live / AWS Nova Sonic            │
│    → 语音直入 → LLM 理解 + function calling → 语音直出        │
│                                                              │
│  三段式模式（离线/免费）：                                    │
│    Whisper/FunASR → Ollama/Qwen → Edge-TTS/ChatTTS           │
│                                                              │
│  Transport: WebSocket / WebRTC / Local                       │
└─────────────────────────────────────────────────────────────┘
```

### A.4 核心代码示例

**将 Z-Core Skill 转为 Pipecat FunctionSchema：**

```python
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.llm_service import FunctionCallParams

def zcore_skill_to_function_schema(skill_path: str) -> FunctionSchema:
    """扫描 Z-Core SKILL.md，提取 name/description/parameters，转为 FunctionSchema"""
    skill_meta = parse_skill_md(skill_path)  # 复用 Z-Core 已有的 SKILL.md 解析
    return FunctionSchema(
        name=skill_meta["name"],
        description=skill_meta["description"],
        properties=skill_meta["parameters"]["properties"],
        required=skill_meta["parameters"].get("required", []),
    )

async def zcore_skill_handler(params: FunctionCallParams):
    """通用 Z-Core skill 执行器"""
    skill_name = params.function_name
    result = await run_zcore_skill(skill_name, params.arguments)
    await params.result_callback(result)
```

**启动语音交互（Pipecat + OpenAI Realtime）：**

```python
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService

async def run_voice_bridge():
    # 1. 扫描 Z-Core skills，转为 FunctionSchema
    skills = discover_zcore_skills("~/.ai-skills/")
    function_schemas = [zcore_skill_to_function_schema(s) for s in skills]

    # 2. 创建 S2S 服务
    llm = OpenAIRealtimeLLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAIRealtimeLLMService.Settings(
            system_instruction=build_system_instruction(),  # 注入 L1/L2/L3 + Persona
        ),
    )

    # 3. 注册所有 Z-Core skill 为 function handler
    for skill in skills:
        llm.register_function(skill.name, zcore_skill_handler)

    # 4. 构建 pipeline 并运行
    pipeline = Pipeline([transport.input(), user_agg, llm, transport.output(), assistant_agg])
    await PipelineRunner().run(PipelineTask(pipeline))
```

**启动语音交互（Pipecat + Gemini Live，免费方案）：**

```python
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService

llm = GeminiLiveLLMService(api_key=os.environ["GOOGLE_API_KEY"])
# 其余相同
```

### A.5 对比评估

| 维度 | 方案 A（自研三段式） | 方案 B（Pipecat 引擎） |
|------|-------------------|---------------------|
| **开发量** | ~2000 行核心代码 | ~200 行适配代码 |
| **S2S 低延迟** | ❌ 不支持（Phase 3 才加） | ✅ 原生支持（OpenAI Realtime / Gemini Live） |
| **Function Calling** | 自研 IntentRouter（三级路由） | S2S 模式下 LLM 直接调用，不需要路由 |
| **ASR/TTS 后端数** | 自己实现 2-3 个 | 自动获得 18+ STT + 25+ TTS |
| **离线能力** | ✅ 本地 Whisper + Edge-TTS | ✅ 同样支持（Local Transport + 本地模型） |
| **中文支持** | 需自测各 Provider | Pipecat 已有中文用户社区 |
| **外部依赖** | 零依赖核心 + 可选 extra | 引入 pipecat-ai 依赖 |
| **可控性** | 完全自研，随心定制 | 受 Pipecat API 约束，上游变更需跟进 |
| **维护成本** | 全部自维护 | 框架由 Daily 团队维护，社区活跃 |
| **Z-Core 零依赖原则** | ✅ 符合（voice 可选 extra） | ⚠️ 放宽为"核心零依赖，voice extra 有依赖" |
| **学习成本** | 低（自己写的代码） | 中（需理解 Pipecat Pipeline/Transport 模型） |

### A.6 LiveKit Agents（另一个候选）

与 Pipecat 同级的替代品，更偏生产部署：

```python
from livekit.agents import Agent, AgentSession, function_tool

@function_tool
async def zcore_search_memory(context, query: str):
    """搜索 Z-Core 历史记忆"""
    return await run_zcore_skill("search_memory", {"query": query})

agent = Agent(instructions="...", tools=[zcore_search_memory])
session = AgentSession()
await session.start(agent=agent)
```

**优势**：`@function_tool` 装饰器极简，内置 MCP 支持，语义 VAD，电话集成。
**劣势**：依赖 LiveKit Server（WebRTC 媒体服务器），部署更重。

### A.7 决策建议

**暂不决策，待以下验证后再选：**

1. 在 WSL2 下实际运行 Pipecat 的 Local Transport，验证音频采集兼容性
2. 用 Pipecat + OpenAI Realtime 跑一个最小 demo，测试端到端延迟
3. 评估 `pipecat-ai` 包的依赖树大小，确认对 Z-Core 的影响范围
4. 测试 Pipecat 的 Gemini Live function calling 在中文场景的表现

**如果 Pipecat 验证通过**：采用方案 B，Z-Core 只需写 Skill 适配层。
**如果 Pipecat 有不可接受的问题**：退回方案 A，自研可控。
