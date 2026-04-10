from __future__ import annotations

import json
import shutil
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from zcore.models.mcp import McpServer, McpSyncResult
from zcore.runtime import RuntimePaths
from zcore.utils.filelock import FileLock


class McpEngine:
    def __init__(self, runtime_paths: RuntimePaths):
        self.runtime_paths = runtime_paths

    def list_servers(self) -> list[McpServer]:
        return sorted(self._read_registry().values(), key=lambda item: item.name)

    def add_server(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> McpServer:
        name = name.strip()
        if not name:
            raise ValueError("server name must not be empty")
        command = command.strip()
        if not command:
            raise ValueError("command must not be empty")

        servers = self._read_registry()
        if name in servers:
            raise ValueError(f"MCP server already exists: {name}")

        server = McpServer(
            name=name,
            command=command,
            args=[item for item in (args or []) if item],
            env={key: value for key, value in (env or {}).items() if key},
        )
        servers[name] = server
        self._write_registry(servers)
        return server

    def remove_server(self, name: str) -> bool:
        servers = self._read_registry()
        if name not in servers:
            return False
        del servers[name]
        self._write_registry(servers)
        return True

    def sync_to_agent(self, agent_name: str, *, dry_run: bool = False) -> McpSyncResult:
        registry = self._read_registry()
        desired = {name: server.to_dict() for name, server in registry.items()}
        return self._write_agent_mcp(agent_name, desired, dry_run=dry_run)

    def diff(self) -> dict[str, Any]:
        registry = self._read_registry()
        desired = {name: server.to_dict() for name, server in registry.items()}
        payload: dict[str, Any] = {"registry": sorted(desired.keys()), "agents": {}}
        for agent_name in ("claude", "gemini", "codex"):
            current = self._read_agent_mcp(agent_name)
            added = sorted(name for name in desired if name not in current)
            removed = sorted(name for name in current if name not in desired)
            updated = sorted(name for name in desired if name in current and current[name] != desired[name])
            payload["agents"][agent_name] = {
                "config_path": str(self._agent_mcp_config_path(agent_name)),
                "servers_added": added,
                "servers_removed": removed,
                "servers_updated": updated,
                "unchanged": not added and not removed and not updated,
            }
        return payload

    def _read_registry(self) -> dict[str, McpServer]:
        path = self.runtime_paths.mcp_registry_path
        if not path.exists():
            return {}
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
        raw_servers = payload.get("servers")
        if not isinstance(raw_servers, dict):
            return {}

        servers: dict[str, McpServer] = {}
        for name, raw in raw_servers.items():
            if not isinstance(raw, dict):
                continue
            command = str(raw.get("command", "")).strip()
            if not command:
                continue
            args = raw.get("args", [])
            env = raw.get("env", {})
            servers[str(name)] = McpServer(
                name=str(name),
                command=command,
                args=[str(item) for item in args] if isinstance(args, list) else [],
                env={str(key): str(value) for key, value in env.items()} if isinstance(env, dict) else {},
            )
        return servers

    def _write_registry(self, servers: dict[str, McpServer]) -> None:
        self.runtime_paths.ensure_runtime_dirs()
        lines = [
            "# Z-Core managed MCP server registry",
            "# Run `zcore mcp sync` to propagate these servers to agent configs.",
        ]
        if servers:
            lines.append("")
        for name in sorted(servers):
            server = servers[name]
            lines.append(f"[servers.{server.name}]")
            lines.append(f'command = "{_escape_toml_string(server.command)}"')
            if server.args:
                args = ", ".join(f'"{_escape_toml_string(item)}"' for item in server.args)
                lines.append(f"args = [{args}]")
            if server.env:
                env_pairs = ", ".join(
                    f'{key} = "{_escape_toml_string(value)}"' for key, value in sorted(server.env.items())
                )
                lines.append(f"env = {{ {env_pairs} }}")
            lines.append("")
        text = "\n".join(lines).rstrip() + "\n"
        _atomic_write(self.runtime_paths.mcp_registry_path, text)

    def _agent_mcp_config_path(self, agent_name: str) -> Path:
        home = Path.home()
        if agent_name == "claude":
            return home / ".claude" / "claude_desktop_config.json"
        if agent_name == "gemini":
            return home / ".gemini" / "settings.json"
        if agent_name == "codex":
            return home / ".codex" / "config.json"
        raise ValueError(f"Unsupported agent: {agent_name}")

    def _read_agent_mcp(self, agent_name: str) -> dict[str, Any]:
        path = self._agent_mcp_config_path(agent_name)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload.get("mcpServers", {})
        return raw if isinstance(raw, dict) else {}

    def _write_agent_mcp(self, agent_name: str, servers: dict[str, Any], *, dry_run: bool = False) -> McpSyncResult:
        path = self._agent_mcp_config_path(agent_name)
        existing_payload: dict[str, Any] = {}
        if path.exists():
            existing_payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing_payload, dict):
                existing_payload = {}
        existing_servers = existing_payload.get("mcpServers", {})
        if not isinstance(existing_servers, dict):
            existing_servers = {}

        added = sorted(name for name in servers if name not in existing_servers)
        removed = sorted(name for name in existing_servers if name not in servers)
        updated = sorted(name for name in servers if name in existing_servers and existing_servers[name] != servers[name])
        unchanged = not added and not removed and not updated

        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                backup = path.with_suffix(path.suffix + ".bak")
                shutil.copy2(path, backup)
            existing_payload["mcpServers"] = servers
            rendered = json.dumps(existing_payload, ensure_ascii=False, indent=2) + "\n"
            _atomic_write(path, rendered)

        return McpSyncResult(
            agent=agent_name,
            config_path=str(path),
            servers_added=added,
            servers_removed=removed,
            servers_updated=updated,
            unchanged=unchanged,
        )


def _escape_toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / f"{path.name}.lock"
    with FileLock(lock_path):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            handle.write(text)
            temp_path = Path(handle.name)
        temp_path.replace(path)
