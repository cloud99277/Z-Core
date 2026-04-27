# Task 3: GhostAgent 角色切换

## 目标

增强 GhostAgent 支持按角色（role）路由到不同 LLM 模型。此任务与 Harvester 完全独立，可并行执行。

## 上下文

- 分支 `v3/develop`
- 已有 `zcore/engines/ghost_agent.py`：`GhostAgent` 类
- `generate()` 签名：`generate(self, prompt, fallback_text=None, *, session_id=None, skill_name=None)`
- `config.toml` 通过 `load_config()` / `get_nested()` 读取
- 62 测试通过

## Allowed write set

- `zcore/engines/ghost_agent.py` — 修改：generate() 增加 role 参数 + 角色路由逻辑
- `zcore/cli/main.py` — 修改：新增 `ghost roles` 子命令
- `tests/test_ghost_roles.py` — 新建

## Protected surface（不得修改）

- `zcore/engines/session.py`、`memory.py`、`context.py`
- `zcore/config.py`、`zcore/runtime.py`
- `zcore/utils/privacy.py`

## 任务详情

### 1. config.toml 角色配置

在 `config.toml` 中支持可选的 `[llm_backend.roles]` 区块：

```toml
[llm_backend]
enabled = true
provider = "google"
model = "gemini-2.5-flash"          # 默认模型

[llm_backend.roles]
compact = "gemini-2.5-flash"
planner = "claude-sonnet-4-20250514"
evaluator = "gemini-2.5-flash"
```

### 2. 修改 generate() 方法

新增 `role` 关键字参数：

```python
def generate(
    self,
    prompt: str,
    fallback_text: str | None = None,
    *,
    role: str | None = None,        # 新增
    session_id: str | None = None,
    skill_name: str | None = None,
) -> dict[str, object]:
```

路由逻辑：
1. `role` 为 None → 行为与 V2 完全一致（使用 `llm_backend.model`）
2. `role` 不为 None → 从 `get_nested(config, "llm_backend", "roles", role)` 获取模型名
3. 找到角色模型 → 用该模型发送请求（临时覆盖 `self.prompt_model()` 返回值）
4. 角色模型不存在 / 请求失败 → fallback 到默认模型
5. 返回 dict 中新增 `"role": role` 字段

**关键约束**：`generate()` 不传 `role` 时，行为必须与修改前 100% 一致。

### 3. CLI 命令

新增 `ghost roles` 子命令：

**`zcore ghost roles [--json]`**

```json
{
  "default_model": "gemini-2.5-flash",
  "roles": {
    "compact": "gemini-2.5-flash",
    "planner": "claude-sonnet-4-20250514"
  }
}
```

如果 `[llm_backend.roles]` 未配置，`roles` 为空 dict。

### 4. 测试 `tests/test_ghost_roles.py`（≥ 4 用例）

- generate() 不传 role → 使用默认模型（回归保护）
- generate(role="compact") → 使用角色模型
- generate(role="nonexistent") → fallback 到默认模型
- `zcore ghost roles --json` 输出有效 JSON

## 交付标准

1. `python3 -m compileall zcore tests` 通过
2. `python3 -m unittest discover tests -q` 全部通过（62 + ≥ 4 新增）
3. `zcore ghost roles --json` 输出有效 JSON
4. 所有现有 GhostAgent 测试不变
5. code-review 自审通过

## 技术约束

- 零外部依赖
- 向下兼容：不传 role 时行为不变
- `[llm_backend.roles]` 是可选配置，不配也正常工作
- 角色路由失败时静默 fallback，不报错
