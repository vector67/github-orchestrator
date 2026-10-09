import logging
import subprocess
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

TIMEOUT = 10

Run = Callable[..., subprocess.CompletedProcess[Any]]


def run_desktop_command(run: Run, argv: list[str], *, missing: str | None) -> str | None:
    name = argv[0]
    try:
        result = run(argv, capture_output=True, text=True, timeout=TIMEOUT)
    except FileNotFoundError:
        if missing is None:
            return None
        reason = missing
    except subprocess.TimeoutExpired:
        reason = f"{name} timed out after {TIMEOUT}s"
    except (OSError, subprocess.SubprocessError) as exc:
        reason = f"{name} failed: {exc}"
    else:
        if result.returncode == 0:
            return None
        detail = " ".join((result.stderr or "").split())
        reason = f"{name} exited {result.returncode}"
        if detail:
            reason = f"{reason}: {detail}"
    log.warning("%s", reason)
    return reason


def command_output(run: Run, argv: list[str]) -> str | None:
    try:
        result = run(argv, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return str(result.stdout)
