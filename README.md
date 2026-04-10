[English](README.md) | [简体中文](README_CN.md)

# 🐾 Z-Core

**Agent Runtime Middleware — shared memory, context management, and skill orchestration for AI agents.**

[![Python](https://img.shields.io/badge/Python-≥3.11-blue?style=flat-square)](https://python.org)
[![Dependencies](https://img.shields.io/badge/Dependencies-0-green?style=flat-square)](#)
[![Tests](https://img.shields.io/badge/Tests-39%2F39-brightgreen?style=flat-square)](#testing)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

Z-Core is an agent-agnostic runtime middleware that gives your CLI agents (Claude Code, Gemini CLI, Codex CLI, etc.) a shared infrastructure for:

- 🧠 **Memory** — persistent cross-session memory with topic-based storage, auto-extraction, and deduplication
- 📋 **Context** — token analysis, automatic compaction via Ghost Agent LLM backend
- 🔄 **Sessions** — session lifecycle, pause/resume, cross-agent handoff
- 🔧 **Skills** — three-layer intelligent routing, lifecycle hooks, and governance
- 🛡️ **Governance** — permission rules, dangerous shell detection, execution audit
- 📊 **Observability** — execution stats, cost tracking, health reports
- 🤖 **Agent Setup** — auto-inject instructions into Claude/Gemini/Codex configs
- 🔁 **Workflows** — TOML-based multi-step skill orchestration

## Quick Start

```bash
# Install (Python ≥3.11, zero external dependencies)
pip install -e .

# Initialize runtime
zcore init

# Check system health
zcore doctor --json
```

## Architecture

Z-Core consists of **9 independent engines**, all injectable via `RuntimePaths`:

```
ContextEngine    → analyze / compact / pre-trim
MemoryEngine     → extract / write / search / dedup / expire
SessionManager   → start / end / pause / resume / handoff / cleanup
SkillRouter      → discover / match / execute / install / validate
PermissionEngine → check / add_rule / audit_report
ObservabilityEngine → log_execution / log_cost / stats / health
AgentSetupEngine → detect / setup / inject
GhostAgent       → generate / availability / fallback
WorkflowEngine   → discover / validate / run
```

**Key design principles:**
- **Zero external dependencies** — Python 3.11+ stdlib only
- **No daemon** — pure CLI, stateless between invocations
- **Agent-agnostic** — works with any terminal-native AI agent
- **Ghost Agent** — optional cheap LLM backend for autonomous compaction/extraction

## CLI Commands (35/35)

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
# Run all 39 tests
python -m unittest discover tests -v

# Quick check
python -m unittest discover tests -q
```

## Project Structure

```
Z-Core/
├── zcore/                  # Python package (5,457 lines)
│   ├── cli/main.py         # argparse CLI (35 commands)
│   ├── engines/            # 9 engines
│   ├── models/             # Data models
│   ├── hooks/              # Lifecycle hook framework
│   ├── utils/              # Shared utilities
│   ├── prompts/            # LLM prompt templates
│   ├── config.py           # TOML config management
│   └── runtime.py          # RuntimePaths discovery
├── tests/                  # 39 unit tests (2,573 lines)
├── v2/                     # Design documentation
│   ├── design/             # Architecture & engine specs
│   ├── pm/                 # Project management
│   ├── rfcs/               # Request for comments
│   └── references/         # External references
├── pyproject.toml          # Package configuration
└── LICENSE
```

## Documentation

- [Architecture](v2/design/architecture.md) — 9-engine design, dependency graph, config schema
- [CLI Design](v2/design/cli.md) — Command interface specification
- [Context Engine](v2/design/context-engine.md) — Token analysis and compaction
- [Memory Engine](v2/design/memory-engine.md) — Extraction, dedup, topic storage
- [Session Manager](v2/design/session-manager.md) — Lifecycle, handoff, pause/resume
- [Skill Router](v2/design/skill-router.md) — Three-layer routing and orchestration
- [Governance](v2/design/governance.md) — Permission rules and hooks
- [Product Strategy](v2/design/product-strategy.md) — Vision and positioning

## Origin

Z-Core was developed as KitClaw V2 — the runtime middleware evolution of the [KitClaw](https://github.com/cloud99277/KitClaw) platform. It has been extracted into a standalone project for independent development and distribution.

## License

[MIT](LICENSE)
