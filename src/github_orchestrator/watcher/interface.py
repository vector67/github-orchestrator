import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from github_orchestrator.domain import HubState

OVERDUE_GRACE = timedelta(minutes=2)


class Watcher(Protocol):
    def run_cycle(self) -> None: ...

    def run_forever(self) -> None: ...

    def wait_in(self, state: HubState, current: Callable[[], HubState]) -> None: ...

    def take_lock(self) -> bool: ...


@dataclass(frozen=True)
class Health:
    alive: bool
    since_last_poll: timedelta | None
    last_error: str | None
    fix: str | None
    polls_every: timedelta

    @property
    def overdue(self) -> bool:
        return (self.since_last_poll is not None
                and self.since_last_poll > 2 * self.polls_every + OVERDUE_GRACE)

    @property
    def next_poll_in(self) -> timedelta | None:
        return None if self.since_last_poll is None else self.polls_every - self.since_last_poll


class WatcherHealth(Protocol):
    def health(self) -> Health: ...


SEMVER = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:-?\.?(a|alpha|b|beta|rc)\.?(\d+))?")
STAGES = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "rc": 2}
FINAL = 3


def _order(version: str) -> tuple[int, ...] | None:
    found = SEMVER.fullmatch(version)
    if found is None:
        return None
    major, minor, patch, stage, number = found.groups()
    rank = FINAL if stage is None else STAGES[stage]
    return int(major), int(minor), int(patch), rank, int(number or 0)


@dataclass(frozen=True)
class Release:
    version: str
    wheel: str | None
    checked_at: datetime | None

    def newer_than(self, running: str | None) -> bool:
        mine = _order(self.version)
        theirs = None if running is None else _order(running)
        return mine is not None and theirs is not None and mine > theirs


class Releases(Protocol):
    def recorded(self) -> Release | None: ...

    def check_if_due(self) -> None: ...

    def look_up(self, version: str | None) -> Release | str: ...

    def download(self, release: Release, into: Path) -> Path | str: ...
