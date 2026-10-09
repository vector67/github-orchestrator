from github_orchestrator.board_api._loopback import loopback_url
from github_orchestrator.domain import Pr


def pr_page(pr: Pr) -> str:
    return f"/pr/{pr.repo}/{pr.number}"


class HubPages:
    def __init__(self, hub_port: int) -> None:
        self._hub = loopback_url(hub_port)

    def board_of(self, pr: Pr) -> str:
        return f"{self._hub}{pr_page(pr)}"
