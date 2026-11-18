from collections.abc import Callable, Iterable
from datetime import datetime

from github_orchestrator.board_api import _contract as contract
from github_orchestrator.board_api._pages import pr_page
from github_orchestrator.domain import Pr
from github_orchestrator.terminal_sessions import Activity, Terminals, Watched

ORDER: dict[Activity, int] = {Activity.WAITING: 0, Activity.WORKING: 1, Activity.IDLE: 2}


def _place(found: tuple[Pr, Watched]) -> tuple[int, datetime, datetime]:
    _, watched = found
    return (ORDER[watched.activity], watched.waiting_since or watched.started_at,
            watched.started_at)


def _row(pr: Pr, watched: Watched) -> contract.WatchedSession:
    since = watched.waiting_since
    return contract.WatchedSession(
        repo=str(pr.repo), number=pr.number, board_url=pr_page(pr), id=watched.session.id,
        argv=list(watched.session.argv), worktree=watched.session.worktree,
        started_at=watched.started_at.isoformat(), activity=watched.activity,
        waiting_since=None if since is None else since.isoformat())


class WatchedSessions:
    def __init__(self, terminals: Terminals, agent_program: str,
                 clock: Callable[[], datetime]) -> None:
        self._terminals = terminals
        self._agent_program = agent_program
        self._clock = clock

    def _of(self, pr: Pr) -> list[Watched]:
        return self._terminals.of(pr).watched(self._clock(), self._agent_program)

    def waiting(self, pr: Pr) -> int:
        return sum(1 for watched in self._of(pr) if watched.activity is Activity.WAITING)

    def read(self, prs: Iterable[Pr]) -> contract.WatchedSessions:
        found = [(pr, watched) for pr in prs for watched in self._of(pr)]
        return contract.WatchedSessions(sessions=[_row(pr, watched)
                                                  for pr, watched in sorted(found, key=_place)])
