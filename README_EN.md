[简体中文](README.md) | [English](README_EN.md)

# 🐾 Z-Core

**Give your AI agents persistent memory, session management, and skill orchestration — zero dependencies, pure CLI.**

[![Python](https://img.shields.io/badge/Python-≥3.11-blue?style=flat-square)](https://python.org)
[![Dependencies](https://img.shields.io/badge/Dependencies-0-green?style=flat-square)](#)
[![Tests](https://img.shields.io/badge/Tests-50%20passing-brightgreen?style=flat-square)](#testing)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

Claude Code, Gemini CLI, Codex CLI — each one is powerful, but none of them remember anything after the session ends. They can't share context. They can't hand off work to each other.

**Z-Core is the missing layer between your agents.** A single CLI that gives any agent:

- 👻 **Ghost Agent** — autonomous LLM backend that thinks between sessions (the soul of Z-Core)
- 🧠 **Memory** — cross-session persistence with topic storage, auto-extraction, deduplication
- 🔄 **Sessions** — lifecycle management, pause/resume, cross-agent handoff
- 📋 **Context** — token analysis, automatic compaction
- 🔧 **Skills** — three-layer intelligent routing, governance hooks, install/validate
- 🛡️ **Governance** — permission rules, dangerous shell detection, execution audit
- 🔌 **MCP Management** — register MCP servers once, sync to all agents
- 📊 **Observability** — execution stats, cost tracking, health reports
- 🤖 **Agent Auto-Setup** — injects instructions into Claude/Gemini/Codex configs automatically

## Install

```bash
git clone <repo-url> Z-Core && cd Z-Core
pip install -e .

# Verify
zcore --version
# → zcore 0.2.0
```

Python ≥3.11. Zero external dependencies — stdlib only.

## 60-Second Quick Start

```bash
# 1. Initialize runtime
zcore init

# 2. Auto-configure your agents (detects Claude/Gemini/Codex)
zcore setup all

# 3. Start a session
zcore session start --project my-app --agent claude
# → Session started: 802718d8b3f4

# 4. Work normally... then end session (auto-saves context + memories)
zcore session end --session-id 802718d8b3f4 --messages messages.json

# 5. Search across all past sessions
zcore memory search --query "database decisions" --json
```

That's it. Your agents now have persistent memory.

## How It Works

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Claude Code │  │ Gemini CLI  │  │  Codex CLI  │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       └────────────────┼────────────────┘
                        │
               ┌────────▼────────┐
               │    Z-Core CLI   │
               │  (zero deps)   │
               └────────┬────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
  ┌─────▼─────┐  ┌──────▼──────┐  ┌────▼─────┐
  │  Memory   │  │  Sessions   │  │  Skills  │
  │ ~/.ai-    │  │  ~/.zcore/  │  │ ~/.ai-   │
  │ memory/   │  │  sessions/  │  │ skills/  │
  └───────────┘  └─────────────┘  └──────────┘
```

Z-Core is a **stateless CLI** — no daemon, no background process. Each invocation reads/writes files directly. Agents call it via `zcore <command> --json` and get structured JSON back.

## Ghost Agent — The Soul of Z-Core

Z-Core's engines handle memory, sessions, and skills. But **Ghost Agent** is what makes it *autonomous*.

Ghost Agent is a cheap LLM backend that runs **between** your sessions — it compacts long conversations, extracts decisions and facts, and triages memories by confidence. It's the reason Z-Core can maintain persistent context without you manually curating anything.

```
  You close Claude Code
         │
         ▼
  ┌──────────────────┐
  │  Ghost Agent     │
  │                  │
  │  1. Read transcript
  │  2. Extract decisions
  │  3. Compact context
  │  4. Deduplicate
  │  5. Triage by confidence
  │                  │
  │  ~$0.01/session  │
  └────────┬─────────┘
           │
           ▼
  You open Gemini CLI → memories already there
```

**Why it matters:**
- Your agent sessions are **expensive** (Claude Opus, Gemini Pro). Don't waste their context window on housekeeping.
- Ghost Agent uses a **cheap model** (Gemini Flash at $0.30/1M input tokens) to do the boring work.
- It runs **offline** — between sessions, not during. Zero latency impact on your actual work.

### Three-Level Fallback (never loses data, never blocks)

```
Level 0: API available     → Full LLM extraction + compaction
                              Summarizes conversations, extracts [decision]/[fact] tags,
                              deduplicates against existing memories, scores confidence.

Level 1: API unavailable   → Heuristic extraction
                              Regex-based scan for [decision], [action], [learning] markers.
                              No semantic understanding, but preserves structure.

Level 2: Heuristic fails   → Gzip raw transcript
                              Stores the full conversation compressed.
                              Picks up processing next time Ghost Agent is available.
```

The principle: **never lose data, never block the user.** A degraded Ghost Agent is still better than no memory at all.

### Setup

```bash
# Enable Ghost Agent
zcore config set llm_backend.enabled true

# Set API key (environment variable recommended)
export ZCORE_LLM_API_KEY="***"

# Check status
zcore status
# → Ghost Agent: remote (google/gemini-2.5-flash)

# That's it. Session end now auto-extracts + compacts.
```

**Cost:** ~$0.01 per session with Gemini Flash. Budget cap available:

```toml
[llm_backend]
monthly_budget = 5.00    # Degrades to heuristic mode when exceeded
```

**Privacy:** all prompts are sanitized before sending — API keys, file paths, and secrets are auto-redacted.

**Supported providers:** Google Gemini, Anthropic Claude, OpenAI GPT, DeepSeek, Ollama (local).

→ **[Ghost Agent Deep Review](v2/design/ghost-agent-deep-review.md)** — 10-dimension architecture audit

## Key Commands

```bash
# Runtime
zcore init              # First-time setup
zcore status            # Overview
zcore doctor            # Health check

# Sessions
zcore session start --project <name> --agent <agent>
zcore session end --session-id <id> --messages <file>
zcore session pause / resume / handoff

# Memory
zcore memory search --query "keyword"
zcore memory write "important fact" --topic <topic>
zcore memory extract --input messages.json --model <model>

# Agent setup
zcore setup detect      # Which agents are installed?
zcore setup all         # Configure all at once

# MCP
zcore mcp add filesystem --command npx --args "-y,@mcp/server-filesystem,/tmp"
zcore mcp sync --dry-run
```

All commands support `--json` for structured output. Agents should always use it.

→ **[Full command reference (40 commands)](docs/getting-started.md)**

## Agent Auto-Setup

`zcore setup` injects a managed instruction block into agent configs (`~/.claude/CLAUDE.md`, etc.) so they automatically learn to use Z-Core:

```bash
zcore setup detect --json     # → claude: true, gemini: true, codex: false
zcore setup claude            # Configure one agent
zcore setup all               # Configure all detected
zcore setup claude --dry-run  # Preview without writing
```

**Safe by design:** idempotent, auto-backup (`.bak`), non-destructive (only touches managed block).

## Runtime Layout

```
~/.zcore/                         # Runtime directory (created by `zcore init`)
├── config.toml                   #   Configuration (permissions 0600)
├── shared-rules.yaml             #   Shared behavioral rules
├── mcp-servers.toml              #   MCP server registry
├── sessions/                     #   Session data
│   ├── index.json                #     Session index
│   └── <id>/                     #     Per-session
│       ├── context.json.gz       #       Context snapshot
│       ├── context.md            #       Human-readable summary
│       └── memories.json         #       Extracted memories
├── logs/                         #   Execution & cost logs
├── hooks/                        #   Pre/post-execute hooks
└── workflows/                    #   Workflow definitions

~/.ai-memory/                     # Memory storage
├── topics/                       #   Topic-based entries
├── staging/                      #   Pending extractions
└── whiteboard.json               #   Cross-session decisions/actions

~/.ai-skills/                     # Skill installation directory
└── <skill-name>/
    ├── SKILL.md                  #   Skill manifest
    └── scripts/                  #   Executable scripts
```

## Configuration

`~/.zcore/config.toml`:

```toml
[llm_backend]
enabled = false                   # Enable Ghost Agent
provider = "google"               # google | anthropic | openai | deepseek | ollama
model = "gemini-2.5-flash"        # Recommended: cheap + fast
monthly_budget = 5.00             # USD monthly cap
fallback_on_failure = true        # Degrade to heuristic on API failure

[privacy]
redact_before_send = true         # Auto-redact secrets before LLM calls

[memory]
auto_extract = false              # Auto-extract on session end
dedup_threshold = 0.85

[context]
auto_compact = false              # Auto-compact when context overflows
compact_threshold_pct = 80

[governance]
permission_mode = "ask"           # ask | allow | deny
```

API keys via environment variables:

```bash
export ZCORE_LLM_API_KEY="***"
```

## Architecture

Z-Core is **10 independent engines**, all injected via `RuntimePaths`:

```
Engine               Responsibility
─────────────────    ──────────────────────────────
GhostAgent           👻 generate / availability / 3-level fallback (THE BRAIN)
ContextEngine        analyze / compact / pre-trim
MemoryEngine         extract / write / search / dedup / expire
SessionManager       start / end / pause / resume / handoff / cleanup
SkillRouter          discover / match / execute / install / validate
PermissionEngine     check / add_rule / audit_report
ObservabilityEngine  log_execution / log_cost / stats / health
AgentSetupEngine     detect / setup / inject
McpEngine            register / diff / sync across agents
WorkflowEngine       discover / validate / run
```

**Key design principles:**
- **Zero external dependencies** — Python 3.11+ stdlib only
- **No daemon** — pure CLI, stateless between invocations
- **Agent-agnostic** — works with any terminal-native AI agent
- **Ghost Agent** — autonomous cheap-LLM backend for compaction/extraction (see above)

## Project Structure

```
Z-Core/
├── zcore/                  # Python package
│   ├── cli/main.py         #   argparse CLI (40 commands)
│   ├── engines/            #   10 engines
│   ├── models/             #   Data models (Skill, Session, Memory, Workflow, MCP)
│   ├── hooks/              #   Lifecycle hook framework
│   ├── utils/              #   Token estimation, FileLock, privacy redaction
│   ├── prompts/            #   LLM prompt templates
│   ├── config.py           #   TOML config management
│   └── runtime.py          #   RuntimePaths discovery
├── tests/                  # 50 unit tests
├── docs/                   # Guides and release notes
├── v2/                     # Design docs, RFCs, PM artifacts
├── pyproject.toml          # Package config (pip installable)
└── LICENSE                 # MIT
```

## Testing

```bash
python -m unittest discover tests -v    # Full suite
python -m unittest discover tests -q    # Quick check
```

## Documentation

| Document | Content |
|----------|---------|
| **[Getting Started](docs/getting-started.md)** | 10-minute walkthrough with real output |
| [Architecture](v2/design/architecture.md) | Engine design, dependency graph, config schema |
| [Memory Engine](v2/design/memory-engine.md) | Extraction, dedup, topic storage |
| [Session Manager](v2/design/session-manager.md) | Lifecycle, handoff, pause/resume |
| [Skill Router](v2/design/skill-router.md) | Three-layer routing and orchestration |
| [Governance](v2/design/governance.md) | Permission rules and hooks |
| [Product Strategy](v2/design/product-strategy.md) | Vision and positioning |
| [Release Notes 0.2.0](docs/release-0.2.0.md) | Standalone extraction baseline |

## Origin

Z-Core was extracted from the [KitClaw](https://github.com/cloud99277/KitClaw) multi-agent infrastructure project as a standalone runtime. It can be used independently or alongside KitClaw.

## Contributing

Issues and PRs welcome. Key principles:

- Zero external dependencies (stdlib only)
- All engines must be injectable via `RuntimePaths`
- CLI output must support `--json` for every command
- Test coverage for new engines/features

```bash
# Dev setup
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Before submitting
python -m compileall zcore tests
python -m unittest discover tests -v
```

## License

[MIT](LICENSE)
