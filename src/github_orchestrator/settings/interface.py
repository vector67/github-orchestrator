from collections.abc import Mapping, Set
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Protocol

from github_orchestrator.domain import (
    Clone,
    DismissUntil,
    HubState,
    Pr,
    Repo,
    ReviewerPick,
)


class Process(Enum):
    WATCHER = auto()
    PR_MANAGER = auto()
    LAUNCHD = auto()
    SERVER = auto()


class Logs(Protocol):
    def path(self, process: Process) -> Path: ...

    def configure_logging(self, process: Process, context: str = "") -> None: ...


@dataclass(frozen=True)
class ConfigRow:
    key: str
    value: object
    source: str
    unset: bool


@dataclass(frozen=True)
class RepoEntry:
    repo: Repo
    local_path: str
    new_worktree_command: str | None = None
    has_tests: bool = True
    pr_skill: str | None = None
    draft: bool | None = None

    def __str__(self) -> str:
        return f"{self.repo} at {self.local_path}"


@dataclass(frozen=True)
class ConfigDescription:
    rows: list[ConfigRow]
    problem: str | None
    exists: bool
    legacy: tuple[str, ...] = ()


class ConfigFile(Protocol):
    def check(self) -> str | None: ...

    def state(self) -> HubState: ...

    def location(self) -> str: ...

    def describe(self) -> ConfigDescription: ...

    def repos(self) -> tuple[RepoEntry, ...]: ...

    def check_write(self, values: Mapping[str, str | int | bool], *,
                    repos: Mapping[Repo, Clone]) -> str | None: ...

    def write(self, values: Mapping[str, str | int | bool], *,
              repos: Mapping[Repo, Clone]) -> None: ...

    def move_aside(self, now: datetime) -> str: ...

    def migrate(self) -> list[str]: ...

    def pr_skill(self) -> str: ...

    def record_pr_skill(self, name: str) -> None: ...


class Holds(Protocol):
    def on_hold(self, pr: Pr) -> bool: ...

    def set_on_hold(self, pr: Pr, on_hold: bool) -> None: ...

    def on_hold_prs(self) -> set[Pr]: ...

    def forget(self, pr: Pr) -> bool: ...

    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]: ...


class Dismissals(Protocol):
    def migrate(self) -> None: ...

    def dismissal(self, pr: Pr) -> DismissUntil | None: ...

    def dismiss_forever(self, pr: Pr) -> None: ...

    def dismiss_until_next_event(self, pr: Pr) -> None: ...

    def dismiss_until_ready_for_review(self, pr: Pr) -> None: ...

    def is_hidden(self, pr: Pr, *, events_waiting: bool, draft: bool) -> bool: ...

    def is_dismissed_forever(self, pr: Pr) -> bool: ...

    def undismiss(self, pr: Pr) -> bool: ...

    def dismissed_prs(self) -> set[Pr]: ...

    def forget(self, pr: Pr) -> bool: ...


class ReviewerPicks(Protocol):
    def saved(self, pr: Pr) -> ReviewerPick | None: ...

    def save(self, pr: Pr, pick: ReviewerPick) -> None: ...

    def forget(self, pr: Pr) -> bool: ...
