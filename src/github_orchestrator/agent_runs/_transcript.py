from __future__ import annotations

import json
import os
import shlex
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from github_orchestrator.agent_runs._duration import format_duration
from github_orchestrator.agent_runs._tail import iter_lines_reverse

_TOOL_ARG_KEYS = ("file_path", "command", "pattern", "skill", "path", "url", "prompt")

_RESULT_FAILURES = {
    "error_max_turns": "hit the turn limit",
    "error_during_execution": "the run errored",
}


def _tool_argument(tool_input: dict[str, Any]) -> str:
    for key in _TOOL_ARG_KEYS:
        value = tool_input.get(key)
        if not isinstance(value, str) or not value:
            continue
        if key in ("file_path", "path"):
            return os.path.basename(value)
        return value.splitlines()[0] if "\n" in value else value
    return ""


def _summarize_block(block: dict[str, Any]) -> list[str]:
    block_type = block.get("type")
    if block_type == "text":
        return [line for line in str(block.get("text", "")).splitlines() if line.strip()]
    if block_type == "tool_use":
        name = block.get("name", "tool")
        tool_input = block.get("input")
        argument = _tool_argument(tool_input) if isinstance(tool_input, dict) else ""
        return [f"● {name} {argument}".rstrip()]
    if block_type == "thinking":
        return ["✻ thinking"]
    if block_type == "tool_result":
        if not block.get("is_error"):
            return []
        content = block.get("content")
        text = content if isinstance(content, str) else json.dumps(content)
        first = text.splitlines()[0] if text.splitlines() else ""
        return [f"↳ error: {first}"]
    return []


def _first_line(text: str) -> str:
    return next((line for line in text.splitlines() if line.strip()), "")


def _shell_script(command: str) -> str:
    try:
        words = shlex.split(command)
    except ValueError:
        return _first_line(command)
    if len(words) == 3 and words[1] in ("-c", "-lc"):
        return _first_line(words[2])
    return _first_line(command)


def _codex_item_started(item: dict[str, Any]) -> list[str]:
    kind = item.get("type")
    if kind == "command_execution":
        return [f"● {_shell_script(str(item.get('command', '')))}".rstrip()]
    if kind == "mcp_tool_call":
        return [f"● {item.get('server', '')}.{item.get('tool', '')}"]
    if kind == "web_search":
        return [f"● web search {item.get('query', '')}".rstrip()]
    return []


def _codex_item_completed(item: dict[str, Any]) -> list[str]:
    kind = item.get("type")
    if kind == "agent_message":
        return [line for line in str(item.get("text", "")).splitlines() if line.strip()]
    if kind == "reasoning":
        return ["✻ thinking"]
    if kind == "command_execution":
        code = item.get("exit_code")
        return [f"↳ error: exit {code}"] if isinstance(code, int) and code != 0 else []
    if kind == "file_change":
        changes = item.get("changes")
        names = [os.path.basename(str(change.get("path", ""))) for change in changes
                 if isinstance(change, dict)] if isinstance(changes, list) else []
        return [f"● edit {', '.join(names)}".rstrip()]
    if kind == "error":
        return [f"↳ error: {_first_line(str(item.get('message', '')))}"]
    return []


def _failure(event: dict[str, Any]) -> str:
    error = event.get("error")
    said = error.get("message") if isinstance(error, dict) else event.get("message")
    first = _first_line(str(said or ""))
    return f"✗ failed: {first}" if first else "✗ failed"


def _summarize_codex_event(event_type: str, event: dict[str, Any]) -> list[str]:
    item = event.get("item")
    if event_type == "item.started" and isinstance(item, dict):
        return _codex_item_started(item)
    if event_type == "item.completed" and isinstance(item, dict):
        return _codex_item_completed(item)
    if event_type == "turn.completed":
        return ["✓ done"]
    if event_type in ("turn.failed", "error"):
        return [_failure(event)]
    return []


def is_codex_event(event_type: object) -> bool:
    return isinstance(event_type, str) and (
        event_type.startswith(("item.", "turn.", "thread.")) or event_type == "error")


def starts_a_run(event: dict[str, Any]) -> bool:
    return (event.get("type") == "system" and event.get("subtype") == "init"
            or event.get("type") == "thread.started")


def summarize_event(event: dict[str, Any]) -> list[str]:
    event_type = event.get("type")
    if isinstance(event_type, str) and is_codex_event(event_type):
        return _summarize_codex_event(event_type, event)
    if event_type in ("assistant", "user"):
        content = event.get("message", {}).get("content")
        if not isinstance(content, list):
            return []
        lines: list[str] = []
        for block in content:
            if isinstance(block, dict):
                lines.extend(_summarize_block(block))
        return lines
    if event_type == "result":
        duration = format_duration(event.get("duration_ms", 0) / 1000)
        if not event.get("is_error"):
            return [f"✓ done ({duration})"]
        text = str(event.get("result") or "")
        subtype = str(event.get("subtype") or "")
        first = (next((ln for ln in text.splitlines() if ln.strip()), "")
                 or _RESULT_FAILURES.get(subtype, subtype))
        return [f"✗ failed ({duration}): {first}" if first
                else f"✗ failed ({duration})"]
    return []


SCAN_MAX_BYTES = 4 * 1024 * 1024


def tail_display_lines(path: Path, limit: int) -> list[tuple[str, bool]]:
    return display_rows(iter_lines_reverse(path, max_bytes=SCAN_MAX_BYTES), limit)


def display_rows(newest_first: Iterable[str], limit: int) -> list[tuple[str, bool]]:
    if limit <= 0:
        return []
    rows: list[tuple[str, bool]] = []
    for raw in newest_first:
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if starts_a_run(event):
            rows.append(("", True))
        else:
            rows.extend((line, False) for line in reversed(summarize_event(event)))
        if len(rows) >= limit:
            break
    rows.reverse()
    rows = rows[-limit:]
    return rows[1:] if rows and rows[0][1] else rows


def last_thread_in(path: Path) -> str | None:
    for raw in iter_lines_reverse(path, max_bytes=SCAN_MAX_BYTES):
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "thread.started":
            thread = event.get("thread_id")
            return thread if isinstance(thread, str) and thread else None
    return None
