---
title: "Z-Core V3.0 MVP 范围定义"
status: draft
created: 2026-04-27
scope: v3-planning
depends_on: ["V3-Roadmap.md", "Harness-三层架构与V2增量.md"]
---

# Z-Core V3.0 MVP 范围定义

> **核心原则**：V3.0 的目标是让 Z-Core 从"辅助工具"迈向"数据主权中间件"。
> 第一步不是造大脑（Planner），而是先造眼睛和耳朵（Harvester）。

---

## 一、V3.0 包含什么（In Scope）

### M1：The Harvester 收割机原型

**目标**：解决 Agent "默写 JSON" 导致的记录残缺问题，实现一键接入。

**交付物**：
- `zcore/engines/harvester.py` — 收割引擎核心
- `zcore/adapters/` — Source Adapter 目录
  - `claude_adapter.py` — 解析 `~/.claude/projects/` 会话日志
  - `hermes_adapter.py` — 解析 `~/.hermes/sessions/` SQLite
- `SourceAdapter` ABC 接口定义：

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class IngestedSession:
    source: str                    # "claude" | "hermes" | "cursor"
    session_id: str
    timestamp: str                 # ISO 8601
    turns: list[dict]              # [{"role": "user"|"assistant", "content": "..."}]
    metadata: dict                 # agent-specific metadata
    topic_hint: str | None         # 主题推断（可选）

class SourceAdapter(ABC):
    @abstractmethod
    def discover(self) -> list[str]:
        """发现可收割的会话 ID 列表"""
        ...

    @abstractmethod
    def ingest(self, session_id: str) -> IngestedSession:
        """收割单个会话"""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """检查数据源是否可用"""
        ...
```

- CLI 命令：
  - `zcore harvest discover --source claude` — 发现可收割会话
  - `zcore harvest ingest --source claude [--session-id <id>]` — 执行收割
  - `zcore harvest status` — 各 Source 的健康状态

**验收标准**：
- [ ] Claude adapter 能正确解析至少 3 种常见的会话日志格式
- [ ] Hermes adapter 能正确解析 SQLite session 存储
- [ ] 收割结果写入 `~/.zcore/harvested/` 并可被 MemoryEngine 消费
- [ ] 收割过程中敏感信息经过脱敏管线

---

### M2：GhostAgent 角色切换

**目标**：不同任务用不同模型，优化成本和质量。

**交付物**：
- `config.toml` 增加 `[llm_backend.roles]` 区块：

```toml
[llm_backend.roles.compact]
provider = "google"
model = "gemini-2.5-flash"         # 压缩不需要强推理

[llm_backend.roles.extract]
provider = "google"
model = "gemini-2.5-flash"         # 记忆提取用便宜模型

[llm_backend.roles.planner]
provider = "anthropic"
model = "claude-sonnet-4"          # 需求展开需要强推理（V3.1 启用）

[llm_backend.roles.evaluator]
provider = "google"
model = "gemini-2.5-flash"         # 验收判断够用（V3.1 启用）
```

- `GhostAgent.generate()` 增加 `role` 参数，按角色路由到不同模型
- 降级策略：角色模型不可用时自动 fallback 到 `default_model`

**验收标准**：
- [ ] `GhostAgent.generate(prompt, role="compact")` 使用 Flash 模型
- [ ] `GhostAgent.generate(prompt, role="extract")` 使用 Flash 模型
- [ ] 角色模型不可用时自动降级到 default，并记录 warning

---

### M3：隐私脱敏管线增强

**目标**：Harvester 收割的原始日志可能包含 API key、密码、个人信息，必须在入库前脱敏。

**交付物**：
- 增强 `zcore/utils/privacy.py`：
  - 新增 `sanitize_transcript(text)` — 对会话文本脱敏
  - 支持的模式：API key（`sk-*`, `AIza*`）、密码、IP 地址、邮箱
- 新增 `~/.zcore/ingest-ignore` 规则文件（类似 `.gitignore`）
- Session 级别 `private: true` 标记支持

**验收标准**：
- [ ] API key 类模式 100% 被替换为 `[REDACTED]`
- [ ] `ingest-ignore` 规则能阻止特定目录/会话被收割
- [ ] `private` 标记的会话不被 Harvester 触及

---

### M4：Session 全文搜索

**目标**：解决"只能通过 ID 或时间戳硬找会话"的痛点。

**交付物**：
- `zcore session search --query <keyword>` — 基于 context.md 的全文检索
- 搜索范围：Session 元数据 + 压缩摘要 + Harvester 收割结果
- 输出格式：匹配的会话列表（ID / 时间 / 匹配片段高亮）

**验收标准**：
- [ ] 关键词搜索在 1000 条会话中响应 < 2s
- [ ] 支持多关键词 AND 搜索
- [ ] 搜索结果按时间倒序排列

---

## 二、V3.0 不包含什么（Out of Scope）

| 特性 | 归入版本 | 原因 |
|------|---------|------|
| Planner Engine | V3.1 | 需要 Harvester 的高质量数据作为前提 |
| Evaluator Engine | V3.1 | 与 Planner 强耦合，需同步交付 |
| Agent Dispatcher | V3.1 | 需要 Planner 产出 Task Graph |
| TUI Dashboard | V3.1 | 需要数据积累后才有可视化价值 |
| Web Dashboard | V3.2 | 需要前端技术选型决策 |
| 具身伴侣 (RFC-005) | V3.5+ / 独立仓库 | 与核心编码价值关联弱，独立产品线 |
| 预测性记忆推送 | V3.2 | 依赖 Harvester + Prefetch 成熟度 |
| 分歧审计器 | V3.2 | 需要多 Agent 协作场景积累 |
| 会话钱包 | V3.2 | 非核心需求 |
| 商业化付费功能 | V3.2+ | V3.0 专注用户价值 |
| Creator Economy | V4+ | 需要用户基数 |

---

## 三、用户旅程（Day-in-the-Life）

### 场景 1：独立开发者日常编码

```
09:00 开机，打开 Claude Code
      → Claude Code 自动加载 Z-Core 注入的上下文（L1/L2 记忆）

09:30 和 Claude 讨论了一个架构决策，修改了 3 个文件
      → 对话正常进行，Z-Core 不介入

10:00 对话结束，用户关闭 Claude
      → 用户（或定时任务）执行：zcore harvest ingest --source claude
      → Harvester 读取 Claude 最近的会话日志
      → 经过脱敏管线，提取出 2 条 decision + 1 条 fact
      → 自动写入 L2 whiteboard

10:05 用户切换到 Gemini CLI 做代码审查
      → Gemini 启动时，Z-Core 自动注入刚才 Claude 对话中的架构决策
      → 用户无需重新解释上下文
      → "上下文接力"完成 ✅
```

### 场景 2：跨 Agent 项目协作（V3.1 场景预览）

```
14:00 用户说："帮我重构认证模块"
      → Z-Core Planner 展开为 3 个 Milestone（V3.1）
      → Dispatcher 派给 Claude Code 执行（V3.1）

15:00 Claude 完成，Z-Core Evaluator 检查（V3.1）
      → 发现测试覆盖不足，打回补测试

15:30 测试补完，Evaluator 通过
      → Harvester 自动收割本次完整对话
      → 写入 L2 + Observability
```

### 场景 3：Z7 伴侣闲聊（V3.5 场景预览）

```
22:30 用户在 Telegram 和 Z7 闲聊
      → Persona Engine 自动切换到 midnight Style
      → 对话中提到"最近在学 Rust"
      → Harvester 收割后提取为 preference 类记忆

次日 09:00 用户打开 Claude Code
      → Z-Core 自动注入："用户最近在学 Rust，相关讨论可参考..."
```

---

## 四、成功指标

### V3.0 技术指标

| 指标 | 目标值 |
|------|--------|
| Harvester 源适配器数量 | ≥ 2（Claude + Hermes） |
| Claude 会话解析成功率 | ≥ 90% |
| 脱敏管线覆盖模式数 | ≥ 5（API key / password / IP / email / token） |
| Session 搜索响应时间 | < 2s（1000 条会话） |
| GhostAgent 角色路由正确率 | 100% |
| 新增测试用例数 | ≥ 15 |
| 零依赖核心保持 | ✅ |

### V3.0 用户体验指标

| 指标 | 目标值 |
|------|--------|
| 收割一次 Claude 历史的命令数 | 1（`zcore harvest ingest --source claude`） |
| 跨 Agent 上下文接力的人工干预次数 | 0 |
| 搜索历史会话的认知负担 | 关键词即可，无需记 ID |

---

## 五、工作量估算

| Milestone | 预估工作量 | 依赖 |
|-----------|-----------|------|
| M1: Harvester | 5-7 天 | 需要分析 Claude/Hermes 日志格式 |
| M2: GhostAgent 角色切换 | 1-2 天 | config.toml 已预留 |
| M3: 隐私脱敏 | 2-3 天 | 复用现有 privacy.py |
| M4: Session 搜索 | 2-3 天 | 依赖 M1 产出的数据 |
| **总计** | **10-15 天** | |

---

## 六、开放问题

1. **Claude 日志格式稳定性**：需要实际分析 `~/.claude/` 目录结构，确认是否有稳定的数据契约
2. **Harvester 触发模式**：手动 CLI vs cron 定时 vs Agent hook 自动触发？建议 MVP 阶段先做手动 CLI
3. **收割结果存储格式**：JSON vs Markdown？建议 JSON（机器友好）+ Markdown 摘要（人类友好）
4. **V3.0 是否需要新的版本号体系**：`0.3.0` 还是 `1.0.0`？建议 `0.3.0`（V3 = 版本 0.3）

---

*本文档为 V3 MVP 范围定义，基于 2026-04-27 PM 审查报告生成。*
