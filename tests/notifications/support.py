from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.desktop import Desktop
from github_orchestrator.domain import Pr
from github_orchestrator.notifications import (
    BoardPages,
    Courier,
    FixProgress,
    Polling,
    PrStatus,
    Runs,
    Settling,
    Standing,
    ThreadNews,
    Worktrees,
)
from github_orchestrator.notifications.fake import FakeBoardPages
from github_orchestrator.wiring import NotificationsWiring, wire
from tests.conftest import (
    clocks_of,
    fake_agent_runs,
    fake_agent_runs_roles,
    fake_provider,
)

CEST = timezone(timedelta(hours=2))
LONG_AWAKE = datetime(2026, 9, 1, tzinfo=CEST)


class Clock:
    def __init__(self) -> None:
        self.at = datetime(2026, 9, 24, 17, 46, tzinfo=CEST)

    def __call__(self) -> datetime:
        return self.at

    def advance(self, **delta: float) -> None:
        self.at += timedelta(**delta)


class Board:
    """How the courier finds each item standing: every fix unseen, every comment
    unanswered, no fix under way and nothing waiting to be materialised,
    unless a test says otherwise."""

    def __init__(self) -> None:
        self.handled: set[str] = set()
        self.fixes: dict[str, FixProgress] = {}
        self.busy: set[Pr] = set()

    def fix_still_news(self, pr: Pr, key: str) -> bool:
        return key not in self.handled

    def comment_still_news(self, pr: Pr, key: str, since: str) -> bool:
        return key not in self.handled

    def fix_progress(self, pr: Pr, key: str) -> FixProgress:
        return self.fixes.get(key, FixProgress.NONE)

    def settling(self, pr: Pr) -> bool:
        return pr in self.busy


@dataclass(frozen=True)
class Opened:
    thread_news: ThreadNews
    runs: Runs
    worktrees: Worktrees
    pr_status: PrStatus
    polling: Polling
    courier: Courier

    def __iter__(self) -> Iterator[object]:
        return iter((self, self.courier))


def opened(root: Path, desktop: Desktop, clock: Callable[[], datetime],
           agent_runs: FakeAgentRuns | None = None,
           board: Board | None = None) -> Opened:
    board = board or Board()
    container = wire(NotificationsWiring(root),
                     clocks_of(local=clock),
                     fake_provider(Desktop, desktop),
                     fake_agent_runs_roles(agent_runs or fake_agent_runs()),
                     fake_provider(Standing, board),
                     fake_provider(Settling, board),
                     fake_provider(BoardPages, FakeBoardPages()))
    return Opened(container.get(ThreadNews), container.get(Runs), container.get(Worktrees),
                  container.get(PrStatus), container.get(Polling), container.get(Courier))
