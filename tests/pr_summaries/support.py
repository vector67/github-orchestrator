import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.domain import Pr
from github_orchestrator.pr_summaries import PrSummaries, SummaryLane
from github_orchestrator.wiring import PrSummariesWiring, SummaryLaneWiring, wire
from tests.builders import a_pr
from tests.conftest import clocks_of, fake_provider, ticking_clock


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


THE_PR = a_pr(7, "acme/widgets")
FAKE_PLUGIN = Path(__file__).with_name("fake_plugin.py")
HEAD = "abc123"


class Lane:
    def __init__(self, tmp_path: Path, behaviour: str, *, run_in: Callable[[Callable[[], None]], None] = run_now,
                 agents_enabled: bool = True, timeout: float = 60, head: str | None = HEAD,
                 plugin: tuple[str, ...] | None = None, clone: Path | None = None, mcp_config: str = "") -> None:
        self.clone = clone or tmp_path / "clone"
        self.clone.mkdir(exist_ok=True)
        self.config = tmp_path / "config.toml"
        self.summaries_dir = tmp_path / "summaries"
        container = wire(
            PrSummariesWiring(self.summaries_dir),
            SummaryLaneWiring(plugin=plugin or (sys.executable, str(FAKE_PLUGIN), "--behaviour", behaviour),
                              config_path=self.config, clones={THE_PR.repo: self.clone}, gh_account="octocat",
                              agents_enabled=agents_enabled, mcp_config=mcp_config, timeout=timeout, run_in=run_in),
            clocks_of(ticking_clock()),
            fake_provider(ChangeDetection, HeadsAt(head)),
        )
        self.summaries: PrSummaries = container.get(PrSummaries)
        self.lane: SummaryLane = container.get(SummaryLane)

    @property
    def folder(self) -> Path:
        return self.summaries_dir / "acme" / "widgets" / "7"

    def call(self) -> dict[str, object]:
        called: dict[str, object] = json.loads((self.folder / "call.json").read_text())
        return called


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
