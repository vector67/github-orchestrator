from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


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
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, suffix=".tmp", delete=False
    )
    tmp_path = Path(tmp.name)
    try:
        try:
            json.dump(
                {
                    "consecutive": failures.consecutive,
                    "last_error": failures.last_error,
                    "fix": failures.fix,
                },
                tmp,
            )
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        tmp_path.replace(path)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return failures


def clear_failures(path: Path) -> None:
    path.unlink(missing_ok=True)

