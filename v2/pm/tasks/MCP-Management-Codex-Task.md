# MCP 配置管理 — 统一 MCP Server 注册与跨 Agent 同步

## 目标

新增 `zcore mcp` 子命令组，实现 MCP Server 配置的统一管理。用户在 Z-Core 中注册一次 MCP server，即可同步到 Claude Code、Gemini CLI、Codex CLI 等多个 Agent 的配置文件。

**核心价值：一处注册，多 Agent 同步。**

## 上下文

- Z-Core 当前 39 测试通过，CLI 35/35 = 100%
- 已有 `zcore setup` 实现了 Agent 配置注入（`AgentSetupEngine`），本任务是其自然延伸
- 已有 Agent 配置路径检测逻辑在 `zcore/engines/agent_setup.py`
- 已有 TOML 读写能力：`tomllib`（stdlib 读）+ `config.py` 的自研写入器
- 保持零外部依赖原则
- Claude Code 和 Gemini CLI 的 MCP 配置格式**完全一致**（都用 `mcpServers` JSON 对象）

### Agent MCP 配置位置与格式

**Claude Code**：`~/.claude/claude_desktop_config.json`
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"],
      "env": {}
    }
  }
}
```

**Gemini CLI**：`~/.gemini/settings.json`（合并到现有 settings 中）
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"],
      "env": {}
    }
  }
}
```

**Codex CLI**（如存在）：`~/.codex/config.json`，格式同上。

> 三个 Agent 的 `mcpServers` 格式完全一致，只是所在文件路径不同。

## 执行方法论

本任务使用 `delegated-sprint` skill 的标准流程。

### 执行 Agent 必须遵守的规则

1. **🔒 code-review 自审不可跳过**：编码完成后，先 `view_file` 读取 `~/.ai-skills/code-review/SKILL.md`，然后按其流程执行 self-review。
2. **测试先行**：每个 Milestone 完成后先验证该 Milestone 的测试通过。
3. **回归保护**：最终交付前，`python3 -m unittest discover tests -q` 必须全部通过。
4. **使用共享 helper**：从 `tests/helpers.py` 导入 `run_zcore`, `TestHome`。

## 任务详情

### M1: McpEngine + 数据模型（核心引擎）

新增 `zcore/engines/mcp.py`，实现 MCP Server 的注册表管理。

**数据存储**：`~/.zcore/mcp-servers.toml`（Z-Core 作为 single source of truth）

```toml
# Z-Core 管理的 MCP Server 注册表
# 执行 `zcore mcp sync` 将这些配置同步到各 Agent

[servers.filesystem]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/projects"]

[servers.postgres]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-postgres"]
env = { DATABASE_URL = "postgresql://localhost/mydb" }

[servers.github]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
env = { GITHUB_TOKEN = "env:GITHUB_TOKEN" }
```

**数据模型** — 新增到 `zcore/models/mcp.py`：

```python
@dataclass
class McpServer:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """输出 mcpServers 格式的 JSON 对象"""
        d: dict[str, Any] = {"command": self.command}
        if self.args:
            d["args"] = self.args
        if self.env:
            d["env"] = self.env
        return d

@dataclass
class McpSyncResult:
    agent: str
    config_path: str
    servers_added: list[str]
    servers_removed: list[str]
    servers_updated: list[str]
    unchanged: bool
```

**McpEngine 方法**：

```python
class McpEngine:
    def __init__(self, runtime_paths: RuntimePaths): ...

    def list_servers(self) -> list[McpServer]:
        """读取 mcp-servers.toml，返回注册的 server 列表"""

    def add_server(self, name: str, command: str,
                   args: list[str] | None = None,
                   env: dict[str, str] | None = None) -> McpServer:
        """注册一个 MCP server 到 mcp-servers.toml"""

    def remove_server(self, name: str) -> bool:
        """从 mcp-servers.toml 删除一个 server"""

    def sync_to_agent(self, agent_name: str, *, dry_run: bool = False) -> McpSyncResult:
        """将注册表同步到指定 Agent 的配置文件"""

    def diff(self) -> dict[str, Any]:
        """对比 Z-Core 注册表 vs 各 Agent 实际配置"""

    def _read_registry(self) -> dict[str, McpServer]:
        """读取 mcp-servers.toml"""

    def _write_registry(self, servers: dict[str, McpServer]) -> None:
        """写入 mcp-servers.toml（手写 TOML，参考 config.py 的写入模式）"""

    def _agent_mcp_config_path(self, agent_name: str) -> Path:
        """返回 Agent 的 MCP 配置文件路径"""

    def _read_agent_mcp(self, agent_name: str) -> dict[str, Any]:
        """读取 Agent 配置文件中的 mcpServers 部分"""

    def _write_agent_mcp(self, agent_name: str, servers: dict[str, Any],
                         *, dry_run: bool = False) -> McpSyncResult:
        """将 mcpServers 合并写入 Agent 配置文件（保留其他配置不动）"""
```

**Agent MCP 配置路径**（复用 `AgentSetupEngine` 的检测逻辑）：

| Agent | 配置文件 | 说明 |
|-------|---------|------|
| claude | `~/.claude/claude_desktop_config.json` | 可能不存在，需创建 |
| gemini | `~/.gemini/settings.json` | 已有其他配置，需合并 |
| codex | `~/.codex/config.json` | 可能不存在，需创建 |

**写入 Agent 配置的关键逻辑**：
1. 读取现有 JSON 文件（不存在则 `{}`）
2. 只更新 `mcpServers` key，保留其他所有配置不动
3. 写入前创建 `.bak` 备份
4. 使用 `json.dumps(indent=2)` 格式化输出

### M2: CLI 子命令

在 `zcore/cli/main.py` 中新增 `mcp` subparser：

**`zcore mcp list [--json]`**
- 列出 Z-Core 中注册的所有 MCP server
- 显示 name、command、args 数量、env 变量数
- 验收：`zcore mcp list --json` 输出 server 列表

**`zcore mcp add <name> --command <cmd> [--args <args>] [--env KEY=VAL ...] [--json]`**
- 注册一个新的 MCP server
- `--args` 接收逗号分隔的参数列表，或多次使用 `--args`
- `--env` 接收 `KEY=VAL` 格式，可多次使用
- 如果 name 已存在，报错（提示用 `remove` 再 `add`，或后续可加 `--force`）
- 验收：`zcore mcp add filesystem --command npx --args "-y,@modelcontextprotocol/server-filesystem,/tmp" --json`

**`zcore mcp remove <name> [--json]`**
- 从注册表删除一个 MCP server
- 注意：只删注册表，不自动同步到 Agent（需手动 `zcore mcp sync`）
- 验收：`zcore mcp remove filesystem --json`

**`zcore mcp sync [--agent claude|gemini|codex|all] [--dry-run] [--json]`**
- 将 Z-Core 注册表同步到指定 Agent（默认 `all`）
- 同步逻辑：Z-Core 注册表作为 source of truth，覆盖 Agent 中的 `mcpServers`
- `--dry-run` 只显示将要做的变更，不实际写入
- 每个 Agent 同步后输出 added/removed/updated 数量
- 验收：`zcore mcp sync --agent claude --dry-run --json`

**`zcore mcp diff [--json]`**
- 对比 Z-Core 注册表 vs 各 Agent 实际配置
- 输出每个 Agent 的差异：多了什么、少了什么、配置不同的
- 验收：`zcore mcp diff --json`

### M3: 测试 + 回归

新增 `tests/test_mcp.py`：

**测试用例**（≥8 个）：

1. `test_add_server` — 注册一个 server，验证 mcp-servers.toml 正确写入
2. `test_add_duplicate_server` — 重复注册同名 server 应报错
3. `test_remove_server` — 删除 server，验证 toml 更新
4. `test_remove_nonexistent` — 删除不存在的 server 应报未找到
5. `test_list_empty` — 无注册 server 时 list 返回空
6. `test_list_servers` — 注册多个 server 后 list 返回正确列表
7. `test_sync_dry_run` — sync --dry-run 不写入 Agent 配置文件
8. `test_sync_to_agent` — sync 写入 Agent 配置文件，验证 JSON 正确
9. `test_sync_preserves_other_config` — sync 不破坏 Agent 配置中的其他字段
10. `test_diff` — diff 正确报告差异

**技巧**：
- 使用 `TestHome` 创建临时 HOME，模拟 Agent 配置文件
- 在临时 HOME 下创建 `~/.claude/claude_desktop_config.json` 和 `~/.gemini/settings.json`
- 验证写入的 JSON 可被 `json.loads()` 正确解析

## 交付标准

1. `python3 -m compileall zcore tests` 通过
2. `python3 -m unittest discover tests -q` 全部通过（39 + ≥8 = 47+ tests）
3. CLI 新增 5 个命令：`mcp list/add/remove/sync/diff`
4. 冒烟验证：
   ```bash
   zcore mcp list --json
   zcore mcp add test-server --command echo --args "hello" --json
   zcore mcp list --json
   zcore mcp sync --dry-run --json
   zcore mcp diff --json
   zcore mcp remove test-server --json
   ```
5. code-review 自审通过

## 技术约束（必读）

- **零外部依赖**：不引入任何第三方库
- **Python ≥3.11**：可用 `tomllib`（stdlib 读 TOML）
- **TOML 写入**：参考 `zcore/config.py` 的手写 TOML 序列化模式
- **JSON 合并**：写 Agent 配置时只更新 `mcpServers` key，保留其他配置不动
- **备份**：写入 Agent 配置前创建 `.bak` 文件
- **使用共享 helper**：新测试 `from tests.helpers import run_zcore, TestHome`
- **不运行 MCP server**：Z-Core 只管配置，不启动/停止 server 进程

## 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `zcore/models/mcp.py` | McpServer, McpSyncResult 数据模型 |
| 新增 | `zcore/engines/mcp.py` | McpEngine 核心引擎 |
| 新增 | `tests/test_mcp.py` | ≥8 个测试用例 |
| 修改 | `zcore/cli/main.py` | 新增 `mcp` subparser（list/add/remove/sync/diff） |
