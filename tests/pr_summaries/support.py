import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

from github_orchestrator.domain import Pr


class HeadsAt:
    def __init__(self, head: str | None) -> None:
        self._head = head

    def facts(self, pr: Pr) -> SimpleNamespace:
        return SimpleNamespace(head_sha=self._head)


def run_now(work: Callable[[], None]) -> None:
    work()


class Held:
    def __init__(self) -> None:
        self.work: list[Callable[[], None]] = []

    def __call__(self, work: Callable[[], None]) -> None:
        self.work.append(work)

    def finish(self) -> None:
        while self.work:
            self.work.pop()()


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def three_commits(root: Path) -> tuple[str, str, str]:
    clone = root / "repo"
    clone.mkdir()
    _git(clone, "init", "-q", "-b", "main")
    _git(clone, "config", "user.email", "t@example.com")
    _git(clone, "config", "user.name", "T")
    shas = []
    for message in ("one", "two", "three"):
        _git(clone, "commit", "-q", "--allow-empty", "-m", message)
        shas.append(_git(clone, "rev-parse", "HEAD"))
    return shas[0], shas[1], shas[2]
