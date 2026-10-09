from collections.abc import Mapping
from typing import Any

RENAMED_KEYS = {
    "claude_timeout": "agent_timeout",
    "claude_enabled": "agents_enabled",
    "claude_command": "agent_command",
    "claude_model": "agent_model",
}


def doubled(data: Mapping[str, Any]) -> str | None:
    return next((old for old, new in RENAMED_KEYS.items() if old in data and new in data), None)


def renamed(data: Mapping[str, Any]) -> dict[str, Any]:
    return {RENAMED_KEYS.get(key, key): value for key, value in data.items()}
