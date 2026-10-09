import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from github_orchestrator.domain import Pr
from github_orchestrator.pr_manager._files import write_whole

log = logging.getLogger(__name__)


class Command(StrEnum):
    HOLD = "hold"
    RESUME = "resume"
    CARRY_ON = "carry-on"
    START_REVIEW = "start-review"
    DISMISS_UNTIL_NEXT_EVENT = "dismiss-until-next-event"
    DISMISS_FOREVER = "dismiss-forever"
    CLOSE = "close"


@dataclass(frozen=True)
class Pending:
    path: Path
    command: Command


class _Ids:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last = 0

    def next(self) -> str:
        with self._lock:
            self._last = max(time.time_ns(), self._last + 1)
            return f"{self._last:020d}-{os.getpid()}"


_IDS = _Ids()


class CommandFiles:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "commands"

    def write(self, pr: Pr, command: Command) -> None:
        path = self._of(pr) / f"{_IDS.next()}.json"
        write_whole(path, json.dumps({"command": command.value}).encode())

    def pending(self, pr: Pr) -> list[Pending]:
        try:
            paths = sorted(self._of(pr).glob("*.json"))
        except OSError as error:
            log.warning("could not list the commands for %s: %s", pr, error)
            return []
        pending = []
        for path in paths:
            command = _read(path)
            if command is None:
                self._discard(path)
            else:
                pending.append(Pending(path, command))
        return pending

    def delete(self, pending: Pending) -> None:
        self._discard(pending.path)

    def _discard(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            log.warning("could not delete the command file %s: %s", path, error)

    def _of(self, pr: Pr) -> Path:
        return self._dir / pr.repo.owner / pr.repo.name / str(pr.number)


def _read(path: Path) -> Command | None:
    try:
        return Command(json.loads(path.read_bytes())["command"])
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as error:
        log.warning("dropping the unreadable command file %s: %s", path, error)
        return None
