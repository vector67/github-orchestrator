from collections.abc import Set
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol

from github_orchestrator.change_detection import (
    BecameUnmergeable,
    CiFailed,
    PrClosed,
    PrEvent,
    ReviewRequested,
)
from github_orchestrator.conversation import ThreadActivity
from github_orchestrator.domain import Pr, Repo

Queued = PrEvent | ThreadActivity


class State(Enum):
    PENDING = "pending"
    IN_FLIGHT = "in-flight"
    FAILED = "failed"


@dataclass(frozen=True)
class Entry:
    pr: Pr
    event: Queued | None
    queued_at: datetime
    state: State
    problem: str | None = None

    @property
    def pending(self) -> bool:
        return self.state is State.PENDING

    @property
    def in_flight(self) -> bool:
        return self.state is State.IN_FLIGHT

    @property
    def failed(self) -> bool:
        return self.state is State.FAILED


@dataclass(frozen=True)
class Queue:
    pr: Pr
    entries: tuple[Entry, ...]

    @property
    def in_flight(self) -> list[Entry]:
        return [entry for entry in self.entries if entry.in_flight]

    @property
    def pending(self) -> list[Entry]:
        return [entry for entry in self.entries if entry.pending]


@dataclass(frozen=True)
class Waiting:
    count: int
    closing: bool
    failed_checks: frozenset[str]


Launching = CiFailed | BecameUnmergeable | ReviewRequested


@dataclass(frozen=True)
class Response:
    event: Queued
    launch: Launching | None
    skipped: bool
    more_failures_wait: bool

    @property
    def closes(self) -> bool:
        return isinstance(self.event, PrClosed)


class Taken(Protocol):
    @property
    def response(self) -> Response: ...

    def done(self) -> None: ...

    def failed(self) -> None: ...


class Intake(Protocol):
    def add(self, pr: Pr, event: PrEvent) -> None: ...

    def add_thread_activity(self, pr: Pr, activity: ThreadActivity) -> None: ...


class Worklist(Protocol):
    def next(
        self, pr: Pr, *, is_author: bool, agents_enabled: bool,
        busy: bool = False,
    ) -> Taken | None: ...

    def waiting(self, pr: Pr) -> Waiting: ...

    def settling(self, pr: Pr) -> bool: ...

    def recover(self, pr: Pr) -> None: ...

    def drop_in_flight(self, pr: Pr) -> None: ...

    def is_torn_down(self, pr: Pr) -> bool: ...

    def forget(self, pr: Pr) -> bool: ...


class Queues(Protocol):
    def queues(self) -> list[Queue]: ...

    def failed_since(self, when: datetime) -> list[Entry]: ...

    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]: ...
