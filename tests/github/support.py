from typing import Any

import dishka

from github_orchestrator.github import Access, PullRequests, Reviews, Threads
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.wiring import GitHubWiring, wire
from tests.github.scripted_gh import ScriptedGh

ROLES = (PullRequests, Threads, Reviews, Access)


class WiredGitHub:
    def __init__(self, container: dishka.Container) -> None:
        self._roles = [(role, container.get(role)) for role in ROLES]

    def __getattr__(self, name: str) -> Any:
        for role, provided in self._roles:
            if name in vars(role):
                return getattr(provided, name)
        raise AttributeError(f"no GitHub role offers {name}")


def real_github(world: FakeGitHub | None = None, gh: ScriptedGh | None = None,
                account: str = "octocat") -> Any:
    run = gh if gh is not None else ScriptedGh(world)
    return WiredGitHub(wire(GitHubWiring(account, run)))
