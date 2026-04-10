[简体中文](README.md) | [English](README_EN.md)

<div align="center">

# 🐾 Z-Core

**Runtime middleware for AI agents with shared memory, context management, MCP sync, and skill orchestration**

[![Author](https://img.shields.io/badge/Author-Cloud927-blue?style=flat-square)](https://github.com/cloud99277)
[![Python](https://img.shields.io/badge/Python-≥3.11-blue?style=flat-square)](https://python.org)
[![Dependencies](https://img.shields.io/badge/Dependencies-0-green?style=flat-square)](#)
[![Tests](https://img.shields.io/badge/Tests-50%20passing-brightgreen?style=flat-square)](#testing)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

Z-Core is an agent-agnostic runtime middleware that gives your CLI agents (Claude Code, Gemini CLI, Codex CLI, etc.) a shared infrastructure for:

- 🧠 **Memory** — persistent cross-session memory with topic-based storage, auto-extraction, and deduplication
- 📋 **Context** — token analysis, automatic compaction via Ghost Agent LLM backend
- 🔄 **Sessions** — session lifecycle, pause/resume, cross-agent handoff
- 🔧 **Skills** — three-layer intelligent routing, lifecycle hooks, and governance
- 🛡️ **Governance** — permission rules, dangerous shell detection, execution audit
- 📊 **Observability** — execution stats, cost tracking, health reports
- 🤖 **Agent Setup** — auto-inject instructions into Claude/Gemini/Codex configs
- 🔌 **MCP Management** — register MCP servers once and sync them into multiple agent configs
- 🔁 **Workflows** — TOML-based multi-step skill orchestration

## Quick Start

```bash
# Install (Python ≥3.11, zero external dependencies)
pip install -e .

# Initialize runtime
zcore init

# Auto-configure your agents (Claude, Gemini, Codex)
zcore setup all

# Register and preview-sync an MCP server
zcore mcp add filesystem --command npx --args "-y,@modelcontextprotocol/server-filesystem,/tmp"
zcore mcp sync --dry-run --json

# Check system health
zcore doctor --json
```

That's it — your agents now know how to use Z-Core automatically.

## Agent Auto-Setup

`zcore setup` auto-injects Z-Core instructions into your agent config files so they learn to use sessions, memory, and context management without manual configuration.

```bash
# Detect which agents are installed
zcore setup detect --json
# → claude: detected=true, gemini: detected=true, codex: detected=false

# Configure a specific agent
zcore setup claude

# Or configure all detected agents at once
zcore setup all

# Preview changes without modifying files
zcore setup claude --dry-run
```

This inserts a managed block into the agent's config file (e.g. `~/.claude/CLAUDE.md`):

```markdown
<!-- ZCORE:START (managed by zcore setup, do not edit manually) -->
## Z-Core Runtime Integration

- Start tasks: `zcore session start --project <project> --agent <agent> --json`
- End tasks: `zcore session end --session-id <id> --json`
- Search memory: `zcore memory search --query "<query>" --json`
- Analyze context: `zcore context analyze --model <model> --input <file> --json`
- Run skills: `zcore run <skill-name> [--args] --json`
- Always use `--json` for structured output
<!-- ZCORE:END -->
```

**Safety guarantees:**
- **Idempotent** — running setup twice won't duplicate the block
- **Auto-backup** — creates `.bak` before modifying
- **`--dry-run`** — preview changes without writing
- **Non-destructive** — only touches the managed block, your own content stays

## Getting Started (5-Minute Walkthrough)

### 1. Start a Session

```bash
zcore session start --project my-app --agent claude
# → Session started: 802718d8b3f4
```

### 2. Extract Memory from Conversations

Save your conversation as `messages.json`, then extract decisions and facts:

```bash
zcore memory extract --input messages.json --model sonnet --project my-app
# → Extracted 4 entries (0 admitted, 3 pending, 1 discarded)
```

Z-Core uses a confidence-based triage:
- **>0.8** — auto-admitted to permanent storage
- **0.5–0.8** — pending human confirmation
- **<0.5** — discarded

### 3. Confirm Pending Memories

```bash
# View pending entries
zcore memory pending
# → 520f4bf2: [decision] Use FastAPI for auto OpenAPI docs
# → bfb2d778: [decision] Use PostgreSQL + SQLAlchemy ORM

# Confirm one
zcore memory pending --confirm 520f4bf2
```

### 4. Search Memory Across Sessions

```bash
zcore memory search --query "database" --json
```

### 5. End Session (Auto-Saves Everything)

```bash
zcore session end --session-id 802718d8b3f4 --messages messages.json
# → Session ended: 802718d8b3f4
# → Auto-saves: context snapshot + extracted memories + summary
```

### 6. Pause / Resume / Handoff

```bash
# Pause without ending
zcore session pause
# → Session paused: 802718d8b3f4

# Resume later
zcore session resume
# → Session resumed: 802718d8b3f4

# Hand off to another agent
zcore session handoff --session-id <id> --to gemini --note "Continue auth module"
```

### Optional: Enable Ghost Agent

Ghost Agent provides LLM-powered compaction and extraction. Without it, Z-Core falls back to heuristic mode (still fully functional).

```bash
zcore config set llm_backend.enabled true
export ZCORE_LLM_API_KEY="your-api-key"
```

> 📖 Full walkthrough: [docs/getting-started.md](docs/getting-started.md)

## Architecture

Z-Core consists of **10 independent engines**, all injectable via `RuntimePaths`:

```
ContextEngine    → analyze / compact / pre-trim
MemoryEngine     → extract / write / search / dedup / expire
SessionManager   → start / end / pause / resume / handoff / cleanup
SkillRouter      → discover / match / execute / install / validate
PermissionEngine → check / add_rule / audit_report
ObservabilityEngine → log_execution / log_cost / stats / health
AgentSetupEngine → detect / setup / inject
McpEngine        → register / diff / sync MCP servers across agents
GhostAgent       → generate / availability / fallback
WorkflowEngine   → discover / validate / run
```

**Key design principles:**
- **Zero external dependencies** — Python 3.11+ stdlib only
- **No daemon** — pure CLI, stateless between invocations
- **Agent-agnostic** — works with any terminal-native AI agent
- **Ghost Agent** — optional cheap LLM backend for autonomous compaction/extraction

## CLI Commands (40/40)

```bash
# Runtime
zcore init [--force] [--json]
zcore status [--json]
zcore doctor [--json]

# Session lifecycle
zcore session start --project <name> --agent <agent> [--resume-latest] [--json]
zcore session end --session-id <id> [--messages <file>] [--json]
zcore session list [--project <name>] [--json]
zcore session show <id> [--json]
zcore session handoff --session-id <id> --to <agent> [--json]
zcore session pause [--session-id <id>] [--json]
zcore session resume [--session-id <id>] [--json]
zcore session cleanup [--older-than 30d] [--dry-run] [--json]

# Memory
zcore memory extract --input <file> --model <model> [--project <name>] [--json]
zcore memory list [--topic <topic>] [--type <type>] [--json]
zcore memory search --query <query> [--json]
zcore memory pending [--confirm <id>] [--json]
zcore memory write --content <text> [--topic <topic>] [--tags <tags>] [--json]
zcore memory topics [--json]
zcore memory stats [--json]
zcore memory expire-check [--older-than 90d] [--dry-run] [--json]

# Context
zcore context analyze --input <file> --model <model> [--json]
zcore compact --input <file> --model <model> [--json]

# Skills
zcore skill list [--json]
zcore skill match --query <query> [--json]
zcore skill info <name> [--json]
zcore skill install <source> [--force] [--json]
zcore skill validate <name> [--json]
zcore run <skill> [skill-args...] [--json]

# Governance
zcore governance rules [--json]
zcore governance check --action <action> --target <target> [--json]
zcore governance allow <pattern> [--json]
zcore governance deny <pattern> [--json]
zcore governance log [--last <n>] [--json]
zcore governance audit [--json]

# Observability
zcore observe stats [--since <period>] [--json]
zcore observe costs [--since <period>] [--json]
zcore observe health [--json]

# Agent setup
zcore setup detect [--json]
zcore setup claude|gemini|codex|all [--dry-run] [--json]

# MCP management
zcore mcp list [--json]
zcore mcp add <name> --command <cmd> [--args <args>] [--env KEY=VAL] [--json]
zcore mcp remove <name> [--json]
zcore mcp sync [--agent claude|gemini|codex|all] [--dry-run] [--json]
zcore mcp diff [--json]

# Config
zcore config show [--json]
zcore config set <section.key> <value> [--json]
zcore config reset [--section <name>] [--json]

# Workflow
zcore workflow list [--json]
zcore workflow validate <name|file> [--json]
zcore workflow run <name|file> [--dry-run] [--json]

# Migration
zcore migrate [--dry-run] [--json]
```

## Testing

```bash
# Run the full test suite
python -m unittest discover tests -v

# Quick check
python -m unittest discover tests -q
```

## Project Structure

```
Z-Core/
├── zcore/                  # Python package
│   ├── cli/main.py         # argparse CLI (40 commands)
│   ├── engines/            # 10 engines
│   ├── models/             # Data models
│   ├── hooks/              # Lifecycle hook framework
│   ├── utils/              # Shared utilities
│   ├── prompts/            # LLM prompt templates
│   ├── config.py           # TOML config management
│   └── runtime.py          # RuntimePaths discovery
├── tests/                  # Standalone regression suite (50 tests)
├── v2/                     # Design documentation
│   ├── design/             # Architecture & engine specs
│   ├── pm/                 # Project management
│   ├── rfcs/               # Request for comments
│   └── references/         # External references
├── pyproject.toml          # Package configuration
└── LICENSE
```

## Documentation

- **[Getting Started Guide](docs/getting-started.md)** — 10-minute walkthrough with real examples
- [Architecture](v2/design/architecture.md) — 9-engine design, dependency graph, config schema
- [CLI Design](v2/design/cli.md) — Command interface specification
- [Context Engine](v2/design/context-engine.md) — Token analysis and compaction
- [Memory Engine](v2/design/memory-engine.md) — Extraction, dedup, topic storage
- [Session Manager](v2/design/session-manager.md) — Lifecycle, handoff, pause/resume
- [Skill Router](v2/design/skill-router.md) — Three-layer routing and orchestration
- [Governance](v2/design/governance.md) — Permission rules and hooks
- [MCP Management Task](v2/pm/tasks/MCP-Management-Codex-Task.md) — MCP registry and cross-agent sync
- [Product Strategy](v2/design/product-strategy.md) — Vision and positioning
- [Release Notes 0.2.0](docs/release-0.2.0.md) — standalone extraction and publish-ready baseline

## Origin

Z-Core began as the V2 runtime extraction from the [KitClaw](https://github.com/cloud99277/KitClaw) project and now lives as a standalone repository for independent development and distribution.

## License

[MIT](LICENSE)
