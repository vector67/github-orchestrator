from datetime import datetime, timezone

from github_orchestrator.domain import LocalClock, Pr
from github_orchestrator.notifications._facts import (
    AgentSkipped,
    Arrival,
    CommentArrived,
    FixReady,
    Gathered,
    Posted,
)
from github_orchestrator.notifications._news import News

__all__ = ["Arrival", "AgentSkipped", "CommentArrived", "FakeBoardPages",
           "FakeNotifications", "FixReady", "Posted"]


class FakeBoardPages:
    def board_of(self, pr: Pr) -> str:
        return f"http://127.0.0.1:8721/pr/{pr.repo}/{pr.number}"


class _Kept:
    def __init__(self) -> None:
        self.posted: list[Posted] = []
        self.gathered: list[Gathered] = []

    def post(self, posted: Posted) -> None:
        self.posted.append(posted)

    def gather(self, item: Gathered) -> None:
        self.gathered.append(item)


class _Remembered:
    def __init__(self) -> None:
        self.sent: set[str] = set()

    def first(self, key: str) -> bool:
        if key in self.sent:
            return False
        self.sent.add(key)
        return True


class FakeNotifications(News):
    def __init__(self) -> None:
        self._kept = _Kept()
        super().__init__(self._kept, _Remembered(),
                         LocalClock(lambda: datetime(2026, 9, 24, 17, 46, tzinfo=timezone.utc)))

    @property
    def posted(self) -> list[Posted]:
        return self._kept.posted

    @property
    def gathered(self) -> list[Gathered]:
        return self._kept.gathered
