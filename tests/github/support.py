import os
from pathlib import Path
from typing import Any

import dishka

from github_orchestrator.github import Access, PullRequests, Reviews, Threads
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.wiring import GitHubWiring, wire
from tests.conftest import clocks_of
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
                account: str = "octocat", requests_log: Path | None = None) -> Any:
    run = gh if gh is not None else ScriptedGh(world)
    log = requests_log or Path(os.environ["GITHUB_ORCHESTRATOR_DATA_DIR"]) / "gh_calls.csv"
    return WiredGitHub(wire(clocks_of(), GitHubWiring(account, run, log)))
