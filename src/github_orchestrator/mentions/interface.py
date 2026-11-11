from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from github_orchestrator.domain import Pr


class StartUnread(Exception):
    pass


class StartLine(Protocol):
    def mentions_start(self, now: datetime) -> datetime: ...

    def move_mentions_start(self, to: datetime) -> None: ...


@dataclass(frozen=True)
class PrNow:
    head_sha: str | None
    approved: bool
    last_event_at: str | None
    closed: bool
    merged: bool


class MentionsInbox(Protocol):
    def search_if_due(self) -> None: ...

    def unbuilt(self) -> list[Pr]: ...

    def settle_deferrals(self, prs: Mapping[Pr, PrNow]) -> None: ...
