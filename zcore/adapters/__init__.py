"""Source adapters for external conversation harvesters."""

from zcore.adapters.base import SourceAdapter
from zcore.adapters.claude_adapter import ClaudeAdapter
from zcore.adapters.codex_adapter import CodexAdapter
from zcore.adapters.hermes_adapter import HermesAdapter
from zcore.adapters.openclaw_adapter import OpenClawAdapter

__all__ = ["ClaudeAdapter", "CodexAdapter", "HermesAdapter", "OpenClawAdapter", "SourceAdapter"]
