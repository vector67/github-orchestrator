from collections.abc import Collection, Sequence

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


class Wall:
    def __init__(self, dashboards: Dashboards, watching: Collection[Repo]) -> None:
        self._dashboards = dashboards
        self._watching = sorted(str(repo) for repo in watching)

    def read(self, held: Sequence[Pr], holdings: Holdings) -> contract.HeldPullRequests:
        return contract.HeldPullRequests(
            watching=self._watching,
            groups=[contract.WallGroupName(group=group, name=GROUP_NAMES[group])
                    for group in WallGroup],
            pull_requests=[self._row(pr, holdings)
                           for pr in sorted(held, key=lambda pr: (str(pr.repo), pr.number))])

    def _row(self, pr: Pr, holdings: Holdings) -> contract.HeldPullRequest:
        return contract.HeldPullRequest(
            repo=str(pr.repo), number=pr.number, manager=holdings.manager(pr),
            board_url=None if holdings.board_port(pr) is None else pr_page(pr),
            dashboard=dashboard_of(self._dashboards.dashboard(pr)))
