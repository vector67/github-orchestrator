from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, StrEnum
from pathlib import Path
from typing import ClassVar, Protocol
from urllib.parse import quote, unquote

_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")
_HEX = re.compile(r"[0-9a-fA-F]{7,40}")


def _is_segment(part: str) -> bool:
    return part not in (".", "..") and _SEGMENT.fullmatch(part) is not None


@dataclass(frozen=True, order=True)
class Repo:
    owner: str
    name: str

    def __post_init__(self) -> None:
        if not (_is_segment(self.owner) and _is_segment(self.name)):
            raise ValueError(f"invalid repo {str(self)!r}; expected 'owner/name'")

    @classmethod
    def parse(cls, text: str) -> Repo:
        parts = text.split("/")
        if len(parts) != 2:
            raise ValueError(f"invalid repo {text!r}; expected 'owner/name'")
        return cls(*parts)

    def __str__(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True, order=True)
class Pr:
    repo: Repo
    number: int

    @property
    def in_repo(self) -> str:
        return f"#{self.number}"

    @property
    def short(self) -> str:
        return f"{self.repo.name}{self.in_repo}"

    def __str__(self) -> str:
        return f"{self.repo}{self.in_repo}"


FORK_PR_BRANCHES = "orchestrator/pr/"


def fork_pr_branch(pr: Pr) -> str:
    return f"{FORK_PR_BRANCHES}{pr.number}"


def fork_pr_number(branch: str) -> int | None:
    number = branch.removeprefix(FORK_PR_BRANCHES)
    return int(number) if number != branch and number.isdecimal() else None


@dataclass(frozen=True)
class ReviewerPick:
    reviewers: tuple[str, ...]
    detailed: str | None


@dataclass(frozen=True)
class Clone:
    path: Path
    new_worktree_command: str


class Side(Enum):
    BEFORE = "before"
    AFTER = "after"


class AuthorKind(StrEnum):
    MINE = "mine"
    HUMAN = "human"
    BOT = "bot"


_BOTS = frozenset({"claude", "codex", "copilot"})


def author_kind_of(login: str, account: str) -> AuthorKind:
    if login == account:
        return AuthorKind.MINE
    if login.lower().removesuffix("[bot]") in _BOTS:
        return AuthorKind.BOT
    return AuthorKind.HUMAN


@dataclass(frozen=True)
class ThreadRow:
    key: str
    standing: str
    state: str
    author_kind: AuthorKind
    updated_at: str | None
    mention: bool


class Listed(Protocol):
    @property
    def key(self) -> str: ...

    @property
    def is_unreadable(self) -> bool: ...


def threads_listed[T: Listed](held: Sequence[T]) -> tuple[list[T], list[str]]:
    return ([one for one in held if not one.is_unreadable],
            sorted(one.key for one in held if one.is_unreadable))


@dataclass(frozen=True)
class Sha:
    hex: str

    def __post_init__(self) -> None:
        if _HEX.fullmatch(self.hex) is None:
            raise ValueError(f"{self.hex!r} is not a commit hash")

    @classmethod
    def parse(cls, text: str | None) -> Sha | None:
        if text is None or _HEX.fullmatch(text) is None:
            return None
        return cls(text)

    def __str__(self) -> str:
        return self.hex


@dataclass(frozen=True)
class ThreadName:
    key: str

    def __post_init__(self) -> None:
        if not self.key.strip("."):
            raise ValueError(f"invalid thread key {self.key!r}")

    @classmethod
    def parse(cls, name: str) -> ThreadName | None:
        quoted, _, _ = name.rpartition("-")
        key = unquote(quoted)
        if not key.strip(".") or str(cls(key)) != name:
            return None
        return cls(key)

    def __str__(self) -> str:
        letters = "".join("1" if c.isupper() else "0" for c in self.key if c.isalpha())
        return f"{quote(self.key, safe='')}-{int(letters or '0', 2):x}"


@dataclass(frozen=True)
class Location:
    path: str
    line: int
    side: Side
    start_line: int | None = None
    start_side: Side | None = None

    def __post_init__(self) -> None:
        if (self.start_line is None) != (self.start_side is None):
            raise ValueError(f"{self.path}:{self.line} names a first line and the side "
                             f"it is on together or neither")


@dataclass(frozen=True)
class CiCheck:
    name: str
    passed: bool
    failed: bool
    done: bool
    url: str | None
    summary: str | None


@dataclass(frozen=True)
class Mention:
    author: str
    at: str | None
    kind: str
    thread: str | None
    comment_id: int | None
    body: str
    answered: bool
    edited_at: str | None = None


@dataclass(frozen=True)
class LabelledComment:
    label: str
    login: str
    body: str


@dataclass(frozen=True)
class UtcClock:
    STAMP: ClassVar[str] = "%Y-%m-%dT%H:%M:%SZ"
    now: Callable[[], datetime]

    def __call__(self) -> datetime:
        return self.now()

    def stamp(self) -> str:
        return self.now().strftime(UtcClock.STAMP)


@dataclass(frozen=True)
class LocalClock:
    now: Callable[[], datetime]

    def __call__(self) -> datetime:
        return self.now()


@dataclass(frozen=True)
class Monotonic:
    seconds: Callable[[], float]

    def __call__(self) -> float:
        return self.seconds()


@dataclass(frozen=True)
class Sleep:
    wait: Callable[[float], None]

    def __call__(self, seconds: float) -> None:
        self.wait(seconds)


class DismissUntil(StrEnum):
    NEXT_EVENT = "next-event"
    READY_FOR_REVIEW = "ready-for-review"
    FOREVER = "forever"


class HubState(StrEnum):
    SETUP = "setup"
    WATCHING = "watching"
    BROKEN = "broken"


__all__ = ["DismissUntil", "HubState", "LabelledComment", "LocalClock", "Location", "Mention", "Monotonic", "Pr", "Repo", "Sha",
           "Side", "Sleep", "ThreadName", "UtcClock"]
