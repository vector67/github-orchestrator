import http.client
import threading
from collections.abc import Callable, Collection, Sequence
from concurrent.futures import Executor, Future, wait
from datetime import datetime, timedelta

from github_orchestrator.board_api import _contract as contract
from github_orchestrator.board_api._pages import pr_page
from github_orchestrator.board_api._projection import dashboard_of
from github_orchestrator.board_api.interface import Dashboards, Holdings, WallGroup
from github_orchestrator.domain import Pr, Repo

GROUP_NAMES = {
    WallGroup.NEEDS_YOU: "Needs you",
    WallGroup.DRAFT: "Draft",
    WallGroup.AGENT_WORKING: "Agent working",
    WallGroup.WAITING_ON_OTHERS: "Waiting on others",
    WallGroup.ON_HOLD: "On hold",
    WallGroup.MENTIONED: "Mentioned",
}

TRUSTED_FOR = timedelta(seconds=30)


def board_dashboard(port: int, seconds: float) -> contract.Dashboard | None:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=seconds)
    try:
        connection.request("GET", "/api/dashboard", headers={"Accept": "application/json"})
        answer = connection.getresponse()
        if answer.status != 200:
            return None
        return contract.Dashboard.model_validate_json(answer.read())
    except (OSError, ValueError):
        return None
    finally:
        connection.close()


class Wall:
    def __init__(self, dashboards: Dashboards, watching: Collection[Repo], pool: Executor,
                 clock: Callable[[], datetime], *, board_seconds: float) -> None:
        self._dashboards = dashboards
        self._watching = sorted(str(repo) for repo in watching)
        self._pool = pool
        self._clock = clock
        self._board_seconds = board_seconds
        self._lock = threading.Lock()
        self._last_answers: dict[Pr, tuple[datetime, contract.Dashboard]] = {}

    def read(self, held: Sequence[Pr], holdings: Holdings) -> contract.HeldPullRequests:
        ports = {pr: holdings.board_port(pr) for pr in held}
        answered = self._boards_answering(ports)
        rebuilt = {pr: self._pool.submit(self._rebuilt, pr) for pr in held if pr not in answered}
        dashboards = {**{pr: asked.result() for pr, asked in rebuilt.items()}, **answered}
        return contract.HeldPullRequests(
            watching=self._watching,
            groups=[contract.WallGroupName(group=group, name=GROUP_NAMES[group])
                    for group in WallGroup],
            pull_requests=[self._row(pr, ports[pr], pr in answered, dashboards[pr], holdings)
                           for pr in sorted(held, key=lambda pr: (str(pr.repo), pr.number))])

    def _boards_answering(self, ports: dict[Pr, int | None]) -> dict[Pr, contract.Dashboard]:
        asked: dict[Pr, Future[contract.Dashboard | None]] = {
            pr: self._pool.submit(board_dashboard, port, self._board_seconds)
            for pr, port in ports.items() if port is not None}
        done, _ = wait(asked.values(), timeout=self._board_seconds)
        now = self._clock()
        with self._lock:
            for pr, future in asked.items():
                if future in done and (dashboard := future.result()) is not None:
                    self._last_answers[pr] = (now, dashboard)
            self._last_answers = {pr: (at, dashboard)
                                  for pr, (at, dashboard) in self._last_answers.items()
                                  if pr in asked and now - at <= TRUSTED_FOR}
            return {pr: dashboard for pr, (_, dashboard) in self._last_answers.items()}

    def _rebuilt(self, pr: Pr) -> contract.Dashboard:
        return dashboard_of(self._dashboards.dashboard(pr))

    @staticmethod
    def _row(pr: Pr, port: int | None, answered: bool, dashboard: contract.Dashboard,
             holdings: Holdings) -> contract.HeldPullRequest:
        return contract.HeldPullRequest(
            repo=str(pr.repo), number=pr.number, manager=holdings.manager(pr),
            board_url=None if port is None else pr_page(pr),
            board_answered=answered, dashboard=dashboard)
