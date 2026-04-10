from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class McpServer:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"command": self.command}
        if self.args:
            payload["args"] = list(self.args)
        if self.env:
            payload["env"] = dict(self.env)
        return payload

    def to_registry_dict(self) -> dict[str, Any]:
        payload = {"name": self.name, "command": self.command, "args": list(self.args), "env": dict(self.env)}
        return payload


@dataclass
class McpSyncResult:
    agent: str
    config_path: str
    servers_added: list[str]
    servers_removed: list[str]
    servers_updated: list[str]
    unchanged: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
