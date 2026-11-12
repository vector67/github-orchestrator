from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from github_orchestrator.atomic_write import write_atomically


@dataclass(frozen=True)
class WatcherFailures:
    consecutive: int
    last_error: str
    fix: str | None


NO_FAILURES = WatcherFailures(consecutive=0, last_error="", fix=None)


def read_failures(path: Path) -> WatcherFailures:
    try:
        data = json.loads(path.read_text())
        fix = data.get("fix")
        return WatcherFailures(
            consecutive=int(data["consecutive"]),
            last_error=str(data["last_error"]),
            fix=fix if isinstance(fix, str) else None,
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return NO_FAILURES


def record_failure(path: Path, error: str, fix: str | None) -> WatcherFailures:
    failures = WatcherFailures(
        consecutive=read_failures(path).consecutive + 1, last_error=error, fix=fix,
    )
    write_atomically(path, json.dumps({
        "consecutive": failures.consecutive,
        "last_error": failures.last_error,
        "fix": failures.fix,
    }).encode())
    return failures


def clear_failures(path: Path) -> None:
    path.unlink(missing_ok=True)

