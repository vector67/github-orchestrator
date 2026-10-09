from collections.abc import Set
from pathlib import Path
from typing import Any

from github_orchestrator.domain import Pr, Repo
from github_orchestrator.settings._config import (
    OrchestratorConfig as OrchestratorConfig,
)
from github_orchestrator.settings._config import Tracker as Tracker
from github_orchestrator.settings._settings import Settings as Settings
from github_orchestrator.settings.interface import ConfigRow as ConfigRow
from github_orchestrator.settings.interface import Dismissal as Dismissal
from github_orchestrator.settings.interface import Process
from github_orchestrator.settings.interface import RepoEntry as RepoEntry

FAKE_CONFIG = {
    "gh_account": "octocat",
    "repos": (RepoEntry(Repo("octocat", "hello-world"),
                        "/tmp/github-orchestrator-tests/hello-world"),),
}


def fake_settings(data_dir: Path, **config: Any) -> Settings:
    return Settings(
        data_dir=data_dir,
        config_path=data_dir / "config.toml",
        config=OrchestratorConfig(**{**FAKE_CONFIG, **config}),
    )


FIRST_BOARD_PORT = 8730


class FakeHolds:
    def __init__(self) -> None:
        self._on_hold: set[Pr] = set()

    def on_hold(self, pr: Pr) -> bool:
        return pr in self._on_hold

    def set_on_hold(self, pr: Pr, on_hold: bool) -> None:
        if on_hold:
            self._on_hold.add(pr)
        else:
            self._on_hold.discard(pr)

    def on_hold_prs(self) -> set[Pr]:
        return set(self._on_hold)

    def forget(self, pr: Pr) -> bool:
        self._on_hold.discard(pr)
        return True

    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]:
        others = sorted({str(pr.repo) for pr in self._on_hold if pr.repo not in keep})
        self._on_hold = {pr for pr in self._on_hold if pr.repo in keep}
        return [into / repo for repo in others]


class FakeDismissals:
    def __init__(self) -> None:
        self._dismissed: dict[Pr, Dismissal] = {}

    def dismissal(self, pr: Pr) -> Dismissal | None:
        return self._dismissed.get(pr)

    def dismiss_forever(self, pr: Pr) -> None:
        self._dismissed[pr] = Dismissal.FOREVER

    def dismiss_until_next_event(self, pr: Pr) -> None:
        self._dismissed[pr] = Dismissal.UNTIL_NEXT_EVENT

    def is_hidden(self, pr: Pr, events_waiting: bool) -> bool:
        dismissal = self._dismissed.get(pr)
        if dismissal is Dismissal.UNTIL_NEXT_EVENT and events_waiting:
            del self._dismissed[pr]
            return False
        return dismissal is not None

    def is_dismissed_forever(self, pr: Pr) -> bool:
        return self._dismissed.get(pr) is Dismissal.FOREVER

    def undismiss(self, pr: Pr) -> bool:
        return self._dismissed.pop(pr, None) is not None

    def dismissed_prs(self) -> set[Pr]:
        return set(self._dismissed)

    def forget(self, pr: Pr) -> bool:
        self._dismissed.pop(pr, None)
        return True


class FakeBoards:
    def __init__(self) -> None:
        self._wanted: set[Pr] = set()
        self._ports: dict[Pr, int] = {}

    def board_wanted(self, pr: Pr) -> bool:
        return pr in self._wanted

    def want_board(self, pr: Pr, wanted: bool) -> None:
        if wanted:
            self._wanted.add(pr)
        else:
            self._wanted.discard(pr)

    def board_port(self, pr: Pr) -> int:
        if pr not in self._ports:
            taken = set(self._ports.values())
            self._ports[pr] = next(
                port for port in range(FIRST_BOARD_PORT, FIRST_BOARD_PORT + len(taken) + 1)
                if port not in taken
            )
        return self._ports[pr]

    def ports_in_use(self) -> tuple[int, int]:
        return len(self._ports), 100

    def forget(self, pr: Pr) -> bool:
        self._wanted.discard(pr)
        self._ports.pop(pr, None)
        return True


class FakeLogs:
    def __init__(self) -> None:
        self.configured: list[tuple[Process, str]] = []

    def path(self, process: Process) -> Path:
        return Path("/fake-logs") / f"{process.name.lower()}.log"

    def configure_logging(self, process: Process, context: str = "") -> None:
        self.configured.append((process, context))
