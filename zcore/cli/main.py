from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from zcore import __version__
from zcore.config import (
    config_permissions_warning,
    init_runtime,
    load_config,
    mask_sensitive_data,
    reset_config,
    set_config_value,
)
from zcore.engines.agent_setup import AgentSetupEngine
from zcore.engines.context import ContextEngine
from zcore.engines.ghost_agent import GhostAgent
from zcore.engines.governance import PermissionDeniedError, PermissionEngine, resolve_ask_behavior
from zcore.engines.mcp import McpEngine
from zcore.engines.memory import MemoryEngine
from zcore.engines.observability import ObservabilityEngine
from zcore.engines.router import SkillRouter
from zcore.engines.session import SessionManager
from zcore.engines.workflow import WorkflowEngine
from zcore.runtime import RuntimePaths


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zcore", description="Z-Core runtime middleware")
    parser.add_argument("--version", action="version", version=f"zcore {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize ~/.zcore runtime files")
    init_parser.add_argument("--force", action="store_true", help="Overwrite config and shared rules if present")
    init_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    status_parser = subparsers.add_parser("status", help="Show runtime bootstrap status")
    status_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    doctor_parser = subparsers.add_parser("doctor", help="Run lightweight health checks")
    doctor_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    context_parser = subparsers.add_parser("context", help="Context analysis commands")
    context_subparsers = context_parser.add_subparsers(dest="context_command", required=True)

    context_analyze = context_subparsers.add_parser("analyze", help="Analyze transcript token usage")
    context_analyze.add_argument("--input", required=True)
    context_analyze.add_argument("--model", required=True)
    context_analyze.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    compact_parser = subparsers.add_parser("compact", help="Compact a messages transcript")
    compact_parser.add_argument("--input", required=True)
    compact_parser.add_argument("--model", required=True)
    compact_parser.add_argument("--session")
    compact_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    memory_parser = subparsers.add_parser("memory", help="Memory engine commands")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command", required=True)

    memory_extract = memory_subparsers.add_parser("extract", help="Extract memories from a transcript")
    memory_extract.add_argument("--input", required=True)
    memory_extract.add_argument("--model", required=True)
    memory_extract.add_argument("--project")
    memory_extract.add_argument("--agent")
    memory_extract.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    memory_list = memory_subparsers.add_parser("list", help="List persisted memories")
    memory_list.add_argument("--topic")
    memory_list.add_argument("--type")
    memory_list.add_argument("--limit", type=int, default=20)
    memory_list.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    memory_search = memory_subparsers.add_parser("search", help="Search persisted memories")
    memory_search.add_argument("--query", required=True)
    memory_search.add_argument("--limit", type=int, default=10)
    memory_search.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    memory_write = memory_subparsers.add_parser("write", help="Write a memory entry directly")
    memory_write.add_argument("content")
    memory_write.add_argument("--topic", default="general")
    memory_write.add_argument("--tags")
    memory_write.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    memory_topics = memory_subparsers.add_parser("topics", help="List memory topics")
    memory_topics.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    memory_stats = memory_subparsers.add_parser("stats", help="Show memory statistics")
    memory_stats.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    memory_pending = memory_subparsers.add_parser("pending", help="Inspect or resolve pending memories")
    memory_pending.add_argument("--confirm")
    memory_pending.add_argument("--reject")
    memory_pending.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    memory_expire = memory_subparsers.add_parser("expire-check", help="Mark stale memories as expired")
    memory_expire.add_argument("--older-than", default="90d")
    memory_expire.add_argument("--dry-run", action="store_true")
    memory_expire.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    migrate_parser = subparsers.add_parser("migrate", help="Migrate whiteboard.json into topic files")
    migrate_parser.add_argument("--dry-run", action="store_true")
    migrate_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    session_parser = subparsers.add_parser("session", help="Session lifecycle commands")
    session_subparsers = session_parser.add_subparsers(dest="session_command", required=True)

    session_start = session_subparsers.add_parser("start", help="Start a new session")
    session_start.add_argument("--project", required=True)
    session_start.add_argument("--agent", required=True)
    session_start.add_argument("--tag", dest="tags", action="append", default=[])
    session_start.add_argument("--resume-from")
    session_start.add_argument("--resume-latest", action="store_true")
    session_start.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    session_end = session_subparsers.add_parser("end", help="End an existing session")
    session_end.add_argument("--session-id", required=True)
    session_end.add_argument("--messages", help="Path to a JSON messages file")
    session_end.add_argument("--no-compact", action="store_true")
    session_end.add_argument("--no-extract", action="store_true")
    session_end.add_argument("--model", default="sonnet")
    session_end.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    session_list = session_subparsers.add_parser("list", help="List recent sessions")
    session_list.add_argument("--project")
    session_list.add_argument("--agent")
    session_list.add_argument("--status")
    session_list.add_argument("--limit", type=int, default=20)
    session_list.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    session_show = session_subparsers.add_parser("show", help="Show a single session")
    session_show.add_argument("session_id")
    session_show.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    session_cleanup = session_subparsers.add_parser("cleanup", help="Clean up old session snapshots")
    session_cleanup.add_argument("--older-than", default="30d")
    session_cleanup.add_argument("--dry-run", action="store_true")
    session_cleanup.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    session_handoff = session_subparsers.add_parser("handoff", help="Generate a handoff note")
    session_handoff.add_argument("--session-id", required=True)
    session_handoff.add_argument("--to", required=True)
    session_handoff.add_argument("--note")
    session_handoff.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    session_pause = session_subparsers.add_parser("pause", help="Pause an active session")
    session_pause.add_argument("--session-id")
    session_pause.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    session_resume = session_subparsers.add_parser("resume", help="Resume a paused session")
    session_resume.add_argument("--session-id")
    session_resume.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    workflow_parser = subparsers.add_parser("workflow", help="Workflow engine commands")
    workflow_subparsers = workflow_parser.add_subparsers(dest="workflow_command", required=True)

    workflow_list = workflow_subparsers.add_parser("list", help="List discovered workflows")
    workflow_list.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    workflow_validate = workflow_subparsers.add_parser("validate", help="Validate a workflow file")
    workflow_validate.add_argument("name_or_file")
    workflow_validate.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    workflow_run = workflow_subparsers.add_parser("run", help="Run a workflow")
    workflow_run.add_argument("name_or_file")
    workflow_run.add_argument("--dry-run", action="store_true")
    workflow_run.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    mcp_parser = subparsers.add_parser("mcp", help="Manage MCP servers and sync across agents")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command", required=True)

    mcp_list = mcp_subparsers.add_parser("list", help="List registered MCP servers")
    mcp_list.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    mcp_add = mcp_subparsers.add_parser("add", help="Add an MCP server to the registry")
    mcp_add.add_argument("name")
    mcp_add.add_argument("--command", dest="mcp_exec", required=True)
    mcp_add.add_argument("--args", action="append", default=[])
    mcp_add.add_argument("--env", action="append", default=[])
    mcp_add.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    mcp_remove = mcp_subparsers.add_parser("remove", help="Remove an MCP server from the registry")
    mcp_remove.add_argument("name")
    mcp_remove.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    mcp_sync = mcp_subparsers.add_parser("sync", help="Sync registry MCP servers into agent configs")
    mcp_sync.add_argument("--agent", choices=["claude", "gemini", "codex", "all"], default="all")
    mcp_sync.add_argument("--dry-run", action="store_true")
    mcp_sync.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    mcp_diff = mcp_subparsers.add_parser("diff", help="Compare registry vs agent MCP configs")
    mcp_diff.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    skill_parser = subparsers.add_parser("skill", help="Skill discovery and matching commands")
    skill_subparsers = skill_parser.add_subparsers(dest="skill_command", required=True)

    skill_list = skill_subparsers.add_parser("list", help="List discovered skills")
    skill_list.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    skill_match = skill_subparsers.add_parser("match", help="Match skills for a query")
    skill_match.add_argument("query")
    skill_match.add_argument("--token-count", type=int)
    skill_match.add_argument("--file-paths", nargs="*", default=[])
    skill_match.add_argument("--project")
    skill_match.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    skill_info = skill_subparsers.add_parser("info", help="Show a single skill manifest")
    skill_info.add_argument("name")
    skill_info.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    skill_install = skill_subparsers.add_parser("install", help="Install a skill from a path or git URL")
    skill_install.add_argument("source")
    skill_install.add_argument("--name")
    skill_install.add_argument("--force", action="store_true")
    skill_install.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    skill_validate = skill_subparsers.add_parser("validate", help="Validate an installed skill")
    skill_validate.add_argument("name")
    skill_validate.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    run_parser = subparsers.add_parser("run", help="Execute a skill")
    run_parser.add_argument("skill_name")
    run_parser.add_argument("skill_args", nargs="*", help="Positional args forwarded as --key value or bare values")
    run_parser.add_argument("--action")
    run_parser.add_argument("--session-id")
    run_parser.add_argument("--project")
    run_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    governance_parser = subparsers.add_parser("governance", help="Governance engine commands")
    governance_subparsers = governance_parser.add_subparsers(dest="governance_command", required=True)

    governance_rules = governance_subparsers.add_parser("rules", help="List loaded permission rules")
    governance_rules.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    governance_check = governance_subparsers.add_parser("check", help="Check whether an action is allowed")
    governance_check.add_argument("action")
    governance_check.add_argument("target")
    governance_check.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    governance_allow = governance_subparsers.add_parser("allow", help="Persist an allow rule")
    governance_allow.add_argument("pattern")
    governance_allow.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    governance_deny = governance_subparsers.add_parser("deny", help="Persist a deny rule")
    governance_deny.add_argument("pattern")
    governance_deny.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    governance_log = governance_subparsers.add_parser("log", help="Show recent execution logs")
    governance_log.add_argument("--last", type=int, default=20)
    governance_log.add_argument("--skill")
    governance_log.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    governance_audit = governance_subparsers.add_parser("audit", help="Aggregate governance audit data")
    governance_audit.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    governance_parser = subparsers.add_parser("governance-check", help="Inspect non-TTY ask behavior")
    governance_parser.add_argument("--action", required=True)
    governance_parser.add_argument("--target", required=True)
    governance_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    observe_parser = subparsers.add_parser("observe", help="Observability commands")
    observe_subparsers = observe_parser.add_subparsers(dest="observe_command", required=True)

    observe_stats = observe_subparsers.add_parser("stats", help="Summarize execution logs")
    observe_stats.add_argument("--since", default="7d")
    observe_stats.add_argument("--skill")
    observe_stats.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    observe_costs = observe_subparsers.add_parser("costs", help="Summarize LLM costs")
    observe_costs.add_argument("--since", default="30d")
    observe_costs.add_argument("--provider")
    observe_costs.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    observe_health = observe_subparsers.add_parser("health", help="Run observability health checks")
    observe_health.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    setup_parser = subparsers.add_parser("setup", help="Detect or integrate Z-Core into agent configs")
    setup_parser.add_argument("setup_target", choices=["detect", "claude", "gemini", "codex", "all"])
    setup_parser.add_argument("--dry-run", action="store_true")
    setup_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    config_parser = subparsers.add_parser("config", help="Inspect and edit config.toml")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)

    config_show = config_subparsers.add_parser("show", help="Show config values")
    config_show.add_argument("--section")
    config_show.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    config_set = config_subparsers.add_parser("set", help="Set a config value using section.key notation")
    config_set.add_argument("key")
    config_set.add_argument("value")
    config_set.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    config_reset = config_subparsers.add_parser("reset", help="Reset config to defaults")
    config_reset.add_argument("--section")
    config_reset.add_argument("--force", action="store_true")
    config_reset.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    return parser


def _status_payload(paths: RuntimePaths) -> dict[str, object]:
    memory = MemoryEngine(paths).get_stats()
    sessions = SessionManager(paths).list(status="active")
    ghost = GhostAgent(paths).availability()
    config_exists = paths.config_path.exists()
    loaded_config = load_config(paths) if config_exists else {}

    return {
        "version": __version__,
        "runtime_dir": str(paths.base_dir),
        "config_path": str(paths.config_path),
        "config_exists": config_exists,
        "needs_init": not config_exists,
        "shared_rules_path": str(paths.shared_rules_path),
        "active_sessions": len(sessions),
        "memory": memory,
        "ghost_agent": ghost,
        "file_locking": {
            "available": True,
            "lock_dir": str(paths.lock_dir),
        },
        "compat": {
            "legacy_skills_dir": str(paths.skills_dir),
            "legacy_memory_manager_present": (paths.skills_dir / "memory-manager").exists(),
        },
        "paths": {
            "memory_dir": str(paths.memory_dir),
            "knowledge_db": str(paths.knowledge_db_path),
        },
        "config_sections": sorted(loaded_config.keys()) if isinstance(loaded_config, dict) else [],
    }


def _print_human_status(payload: dict[str, object]) -> None:
    ghost = payload["ghost_agent"]
    memory = payload["memory"]
    compat = payload["compat"]
    print("Z-Core Status")
    print(f"  Version: {payload['version']}")
    print(f"  Runtime: {payload['runtime_dir']}")
    print(f"  Config: {'present' if payload['config_exists'] else 'missing'} ({payload['config_path']})")
    print(f"  Active sessions: {payload['active_sessions']}")
    print(f"  Whiteboard entries: {memory['whiteboard_entries']}")
    print(f"  Topic files: {memory['topic_count']}")
    print(f"  Knowledge DB: {'present' if memory['rag_available'] else 'missing'}")
    print(
        "  Ghost Agent: "
        f"{ghost['mode']} ({ghost['provider']}/{ghost['model']})"
        + (f" reason={ghost['reason']}" if ghost["reason"] else "")
    )
    print(f"  File locking: {'ready' if payload['file_locking']['available'] else 'unavailable'}")
    print(f"  Legacy bridge: {'ready' if compat['legacy_memory_manager_present'] else 'missing'}")


def _doctor_payload(paths: RuntimePaths) -> dict[str, object]:
    warnings = []
    permission_warning = config_permissions_warning(paths)
    if permission_warning:
        warnings.append(permission_warning)
    if not paths.config_path.exists():
        warnings.append("config missing: run `zcore init`")
    if not paths.shared_rules_path.exists():
        warnings.append("shared rules missing: run `zcore init`")

    return {
        "healthy": not warnings,
        "warnings": warnings,
        "runtime_dir": str(paths.base_dir),
        "config_path": str(paths.config_path),
    }


def _load_messages(path: str) -> list[dict[str, object]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        messages = payload.get("messages")
        if isinstance(messages, list):
            return messages
    if isinstance(payload, list):
        return payload
    raise ValueError(f"Unsupported messages file format: {path}")


def _parse_skill_args(items: list[str]) -> dict[str, object]:
    parsed: dict[str, object] = {}
    positional: list[str] = []
    index = 0
    while index < len(items):
        item = items[index]
        if item.startswith("--"):
            key = item[2:].replace("-", "_")
            next_index = index + 1
            if next_index < len(items) and not items[next_index].startswith("--"):
                parsed[key] = items[next_index]
                index += 2
            else:
                parsed[key] = True
                index += 1
            continue
        positional.append(item)
        index += 1
    if positional:
        parsed["argv"] = positional
    return parsed


def _parse_repeated_csv(items: list[str]) -> list[str]:
    values: list[str] = []
    for item in items:
        for part in item.split(","):
            stripped = part.strip()
            if stripped:
                values.append(stripped)
    return values


def _parse_env_pairs(items: list[str]) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"invalid env pair (expected KEY=VALUE): {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"invalid env key: {item}")
        pairs[key] = value
    return pairs


def _normalize_argv(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        return None
    normalized = list(argv)
    if len(normalized) >= 2 and normalized[0] == "mcp" and normalized[1] == "add":
        index = 0
        while index < len(normalized) - 1:
            if normalized[index] == "--args" and normalized[index + 1].startswith("-"):
                normalized[index] = f"--args={normalized[index + 1]}"
                del normalized[index + 1]
                continue
            index += 1
    return normalized


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    raw_argv = argv if argv is not None else sys.argv[1:]
    args, unknown = parser.parse_known_args(_normalize_argv(raw_argv))
    if getattr(args, "command", None) == "run" and unknown:
        args.skill_args.extend(unknown)
    elif unknown:
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")
    paths = RuntimePaths.discover()

    if args.command == "init":
        result = init_runtime(paths, force=args.force)
        payload = {
            "ok": True,
            "runtime_dir": str(paths.base_dir),
            **result,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print("Initialized Z-Core runtime")
            print(f"  Runtime: {paths.base_dir}")
            print(f"  Config: {paths.config_path}")
            print(f"  Shared rules: {paths.shared_rules_path}")
        return 0

    if args.command == "status":
        payload = _status_payload(paths)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            _print_human_status(payload)
        return 0

    if args.command == "doctor":
        payload = _doctor_payload(paths)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print("Z-Core Doctor")
            print(f"  Healthy: {'yes' if payload['healthy'] else 'no'}")
            for warning in payload["warnings"]:
                print(f"  Warning: {warning}")
        return 0

    if args.command == "context":
        engine = ContextEngine(paths)
        messages = _load_messages(args.input)
        if args.context_command == "analyze":
            payload = engine.analyze(messages, args.model).to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print("Context Analysis")
                print(f"  Total tokens: {payload['total_tokens']}")
                print(f"  Context window: {payload['context_window']}")
                print(f"  Usage: {payload['usage_pct']}%")
                print(f"  Remaining: {payload['tokens_remaining']}")
                print(f"  Should compact: {'yes' if payload['should_compact'] else 'no'}")
                print(f"  Urgency: {payload['urgency']}")
            return 0

    if args.command == "compact":
        engine = ContextEngine(paths)
        messages = _load_messages(args.input)
        result = engine.apply_compact(
            messages,
            args.model,
            ghost_agent=GhostAgent(paths),
            session_id=args.session,
        )
        payload = result.to_dict()
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(result.summary)
        return 0

    if args.command == "memory":
        engine = MemoryEngine(paths)
        if args.memory_command == "extract":
            messages = _load_messages(args.input)
            payload = engine.extract_from_conversation(
                messages,
                model=args.model,
                project=args.project,
                agent=args.agent,
            ).to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(
                    f"Extracted {len(payload['entries'])} entries"
                    f" ({payload['admitted']} admitted, {payload['pending']} pending, {payload['discarded']} discarded)"
                )
            return 0

        if args.memory_command == "list":
            entries = engine.list_entries(topic=args.topic, type_name=args.type, limit=args.limit)
            payload = [entry.to_dict() for entry in entries]
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for entry in entries:
                    print(entry.to_markdown_line())
            return 0

        if args.memory_command == "search":
            entries = engine.search(args.query, limit=args.limit)
            payload = [entry.to_dict() for entry in entries]
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for entry in entries:
                    print(entry.to_markdown_line())
            return 0

        if args.memory_command == "write":
            tags = [item.strip() for item in str(args.tags or "").split(",") if item.strip()]
            entry = engine.write_memory(args.content, topic=args.topic, tags=tags)
            payload = entry.to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(entry.to_markdown_line())
            return 0

        if args.memory_command == "topics":
            payload = engine.list_topics()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for item in payload:
                    print(f"{item['topic']}\t{item['count']}")
            return 0

        if args.memory_command == "stats":
            payload = engine.get_stats()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"Total entries: {payload['total_entries']}")
            return 0

        if args.memory_command == "pending":
            if args.confirm and args.reject:
                parser.error("--confirm and --reject are mutually exclusive")
            if args.confirm:
                payload = engine.confirm_pending(args.confirm).to_dict()
            elif args.reject:
                engine.reject_pending(args.reject)
                payload = {"rejected": args.reject}
            else:
                payload = engine.list_pending()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                if isinstance(payload, list):
                    for item in payload:
                        print(f"{item['id']}: [{item['type']}] {item['content']}")
                else:
                    print(payload)
            return 0

        if args.memory_command == "expire-check":
            payload = engine.expire_check(older_than=args.older_than, dry_run=args.dry_run)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"Expired entries: {len(payload['expired'])}")
            return 0

    if args.command == "migrate":
        payload = MemoryEngine(paths).migrate_v1(dry_run=args.dry_run)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"Migrated {payload['migrated']} memories across {len(payload['topics'])} topics")
        return 0

    if args.command == "session":
        manager = SessionManager(paths)
        if args.session_command == "start":
            resume_from = args.resume_from
            resume_context = ""
            if args.resume_latest:
                latest = manager.find_latest(project=args.project, status="completed")
                if latest is not None:
                    resume_from = latest.session_id
                    resume_context = manager.load_context(latest.session_id) or latest.summary
            meta = manager.start(args.project, args.agent, tags=args.tags, resume_from=resume_from)
            payload = meta.to_dict()
            if resume_from:
                payload["resume_from"] = resume_from
            if resume_context:
                payload["resume_context"] = resume_context
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"Session started: {meta.session_id}")
                if resume_context:
                    print()
                    print(resume_context)
            return 0

        if args.session_command == "end":
            messages = None
            if args.messages:
                messages = _load_messages(args.messages)
            meta = manager.end(
                args.session_id,
                messages=messages,
                ghost_agent=GhostAgent(paths),
                auto_compact=not args.no_compact,
                auto_extract_memory=not args.no_extract,
                model=args.model,
            )
            payload = meta.to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"Session ended: {meta.session_id}")
                if meta.summary:
                    print(meta.summary)
            return 0

        if args.session_command == "list":
            sessions = manager.list(
                project=args.project,
                agent=args.agent,
                status=args.status,
                limit=args.limit,
            )
            payload = [session.to_dict() for session in sessions]
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for session in sessions:
                    print(
                        f"{session.session_id}\t{session.project}\t{session.agent}\t"
                        f"{session.status}\t{session.summary}"
                    )
            return 0

        if args.session_command == "show":
            payload = manager.show_session(args.session_id)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"{payload['session_id']}\t{payload['project']}\t{payload['status']}")
            return 0

        if args.session_command == "cleanup":
            payload = manager.cleanup_sessions(older_than=args.older_than, dry_run=args.dry_run)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"Cleanup candidates: {len(payload['removed'])}")
            return 0

        if args.session_command == "handoff":
            document = manager.handoff(args.session_id, args.to, note=args.note)
            payload = {
                "ok": True,
                "session_id": args.session_id,
                "to_agent": args.to,
                "path": str(paths.sessions_dir / args.session_id / "handoff.md"),
                "document": document,
            }
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(document)
            return 0

        if args.session_command == "pause":
            meta = manager.pause(session_id=args.session_id)
            payload = meta.to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"Session paused: {meta.session_id}")
            return 0

        if args.session_command == "resume":
            meta = manager.resume(session_id=args.session_id)
            payload = meta.to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"Session resumed: {meta.session_id}")
            return 0

    if args.command == "workflow":
        engine = WorkflowEngine(paths)
        if args.workflow_command == "list":
            payload = [workflow.to_dict() for workflow in engine.discover_workflows()]
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for workflow in payload:
                    print(f"{workflow['name']}\t{len(workflow['steps'])}\t{workflow['source_path']}")
            return 0
        if args.workflow_command == "validate":
            payload = engine.validate_workflow(args.name_or_file)
            code = 0 if payload["ok"] else 1
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for check in payload["checks"]:
                    print(f"{check['status']}\t{check['check']}\t{check['message']}")
            return code
        if args.workflow_command == "run":
            result = engine.run_workflow(args.name_or_file, dry_run=args.dry_run)
            payload = result.to_dict()
            code = 0 if payload["overall"] in {"ok", "partial"} else 1
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"{payload['workflow_name']}\t{payload['overall']}")
            return code

    if args.command == "mcp":
        engine = McpEngine(paths)
        if args.mcp_command == "list":
            servers = engine.list_servers()
            payload = [
                {
                    "name": server.name,
                    "command": server.command,
                    "args": server.args,
                    "args_count": len(server.args),
                    "env": server.env,
                    "env_count": len(server.env),
                }
                for server in servers
            ]
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for item in payload:
                    print(f"{item['name']}\t{item['command']}\targs={item['args_count']}\tenv={item['env_count']}")
            return 0

        if args.mcp_command == "add":
            try:
                server = engine.add_server(
                    args.name,
                    args.mcp_exec,
                    args=_parse_repeated_csv(args.args),
                    env=_parse_env_pairs(args.env),
                )
            except ValueError as exc:
                print(str(exc))
                return 1
            payload = {"ok": True, "server": {"name": server.name, **server.to_dict()}}
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"Added MCP server: {server.name}")
            return 0

        if args.mcp_command == "remove":
            removed = engine.remove_server(args.name)
            if not removed:
                print(json.dumps({"ok": False, "error": f"MCP server not found: {args.name}"}, ensure_ascii=False) if args.json else f"MCP server not found: {args.name}")
                return 1
            payload = {"ok": True, "removed": args.name}
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"Removed MCP server: {args.name}")
            return 0

        if args.mcp_command == "sync":
            agents = ["claude", "gemini", "codex"] if args.agent == "all" else [args.agent]
            results = [engine.sync_to_agent(agent, dry_run=args.dry_run).to_dict() for agent in agents]
            payload = {"ok": True, "dry_run": args.dry_run, "results": results}
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for result in results:
                    print(
                        f"{result['agent']}\tadded={len(result['servers_added'])}\t"
                        f"removed={len(result['servers_removed'])}\tupdated={len(result['servers_updated'])}"
                    )
            return 0

        if args.mcp_command == "diff":
            payload = engine.diff()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for agent, result in payload["agents"].items():
                    print(
                        f"{agent}\tadded={len(result['servers_added'])}\t"
                        f"removed={len(result['servers_removed'])}\tupdated={len(result['servers_updated'])}"
                    )
            return 0

    if args.command == "skill":
        router = SkillRouter(paths)
        if args.skill_command == "list":
            manifests = router.discover()
            payload = [manifest.to_dict() for manifest in manifests]
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for manifest in manifests:
                    print(f"{manifest.name}\t{manifest.source_type}\t{manifest.source_path}")
            return 0

        if args.skill_command == "match":
            matches = router.match(
                args.query,
                file_paths=args.file_paths,
                token_count=args.token_count,
                project=args.project,
            )
            payload = [match.to_dict() for match in matches]
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for match in matches:
                    print(
                        f"{match.manifest.name}\t{match.score:.2f}\t"
                        f"layer={match.match_layer}\t{match.match_reason}"
                    )
            return 0
        if args.skill_command == "info":
            payload = router.get_skill_info(args.name).to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"{payload['name']}\t{payload['description']}")
            return 0
        if args.skill_command == "install":
            payload = router.install_skill(args.source, name=args.name, force=args.force)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"Installed skill: {payload['name']}")
            return 0
        if args.skill_command == "validate":
            payload = router.validate_skill(args.name)
            code = 0 if payload["ok"] else 1
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for check in payload["checks"]:
                    print(f"{check['status']}\t{check['check']}\t{check['message']}")
            return code

    if args.command == "run":
        router = SkillRouter(paths)
        skill_args = _parse_skill_args(args.skill_args)
        if args.action:
            skill_args["action"] = args.action
        if args.project:
            skill_args["project"] = args.project
        result = router.execute(args.skill_name, skill_args, session_id=args.session_id)
        payload = result.to_dict()
        code = 0 if result.status == "ok" else 1
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(result.output)
        return code

    if args.command == "governance":
        engine = PermissionEngine(paths)
        if args.governance_command == "rules":
            payload = [rule.to_dict() for rule in engine.load_rules()]
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for rule in engine.load_rules():
                    print(f"{rule.source}\t{rule.action}({rule.pattern})\t{rule.decision}")
            return 0
        if args.governance_command == "allow":
            payload = engine.add_rule(args.pattern, "allow").to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"allow: {args.pattern}")
            return 0
        if args.governance_command == "deny":
            payload = engine.add_rule(args.pattern, "deny").to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"deny: {args.pattern}")
            return 0
        if args.governance_command == "log":
            payload = engine.read_log(last=args.last, skill_name=args.skill)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for item in payload:
                    print(f"{item.get('timestamp')}\t{item.get('skill_name')}\t{item.get('status')}")
            return 0
        if args.governance_command == "audit":
            payload = engine.audit_report()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"Rules: {payload['rule_stats']['total']}")
            return 0
        if args.governance_command == "check":
            decision = engine.check(args.action, args.target)
            payload = decision.to_dict()
            code = 0 if decision.allowed else 1
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(payload["reason"])
            return code

    if args.command == "governance-check":
        try:
            decision = resolve_ask_behavior(args.action, args.target)
            payload = {"ok": True, "decision": decision.decision, "reason": decision.reason}
            code = 0
        except PermissionDeniedError as exc:
            payload = {"ok": False, "error": str(exc)}
            code = 1

        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(payload["reason"] if payload["ok"] else payload["error"])
        return code

    if args.command == "observe":
        engine = ObservabilityEngine(paths)
        if args.observe_command == "stats":
            payload = engine.get_execution_stats(since=args.since, skill_name=args.skill).to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print("Execution Stats")
                print(f"  Period: {payload['period']}")
                print(f"  Total: {payload['total']}")
                print(f"  Success: {payload['success']}")
                print(f"  Failed: {payload['failed']}")
                print(f"  Avg duration: {payload['avg_duration_ms']} ms")
            return 0
        if args.observe_command == "costs":
            payload = engine.get_cost_report(since=args.since, provider=args.provider).to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print("Cost Report")
                print(f"  Period: {payload['period']}")
                print(f"  Total USD: {payload['total_usd']}")
                print(f"  Budget remaining: {payload['budget_remaining']}")
            return 0
        if args.observe_command == "health":
            payload = engine.health_check().to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print("Health Report")
                print(f"  Healthy: {'yes' if payload['healthy'] else 'no'}")
                for warning in payload["warnings"]:
                    print(f"  Warning: {warning}")
            return 0

    if args.command == "setup":
        engine = AgentSetupEngine(paths)
        if args.setup_target == "detect":
            payload = [item.to_dict() for item in engine.detect_agents()]
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                for item in payload:
                    print(f"{item['name']}\tdetected={item['detected']}\tpath={item['config_path']}")
            return 0
        payload = engine.setup_agent(args.setup_target, dry_run=args.dry_run).to_dict()
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"{payload['agent']}: {payload['config_path']}")
            for change in payload["changes"]:
                print(f"  - {change}")
        return 0

    if args.command == "config":
        if args.config_command == "show":
            payload = load_config(paths)
            if args.section:
                payload = payload.get(args.section, {}) if isinstance(payload, dict) else {}
            payload = mask_sensitive_data(payload)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if args.config_command == "set":
            payload = set_config_value(paths, args.key, args.value)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"Updated {payload['key']} = {payload['value']}")
            return 0

        if args.config_command == "reset":
            if not args.section and not args.force:
                parser.error("config reset without --section requires --force")
            payload = reset_config(paths, section=args.section)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(f"Reset config scope: {payload['scope']}")
            return 0

    return 1
