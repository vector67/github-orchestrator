from datetime import datetime
from typing import Protocol

from github_orchestrator.domain import Pr


class StartUnread(Exception):
    pass


class StartLine(Protocol):
    def mentions_start(self, now: datetime) -> datetime: ...

    def move_mentions_start(self, to: datetime) -> None: ...


class MentionsInbox(Protocol):
    def search_if_due(self) -> None: ...

    def unbuilt(self) -> list[Pr]: ...
