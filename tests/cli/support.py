from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import dishka

from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.board_api import Hub
from github_orchestrator.board_api.fake import FakeHub
from github_orchestrator.cli import Cli
from github_orchestrator.desktop import Desktop
from github_orchestrator.desktop.fake import FakeDesktop
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications import BoardPages
from github_orchestrator.notifications.fake import FakeBoardPages
from github_orchestrator.pr_processes import PrProcesses
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import Settings
from github_orchestrator.terminal_sessions import Terminals, TerminalSessions
from github_orchestrator.terminal_sessions.fake import (
    FakeTerminals,
    FakeTerminalSessions,
)
from github_orchestrator.wiring import (
    CliWiring,
    OtherInstancesWiring,
    cli_config,
    make_container,
    notifications_wiring,
    watcher_wiring,
)
from tests.cli.scripted_system import WATCHER_PID as HUB_PID
from tests.cli.scripted_system import ScriptedSystem
from tests.conftest import (
    build_container,
    clocks_of,
    fake_agent_runs_roles,
    fake_github,
    fake_provider,
)
from tests.watcher.scripted_releases import ScriptedReleasesApi

ACCOUNT = 'gh_account = "octocat"\n'
HELLO_WORLD = (
    '\n[[repos]]\n'
    'repo = "octocat/hello-world"\n'
    'local_path = "/tmp/github-orchestrator-tests/hello-world"\n'
)
CONFIGURED = ACCOUNT + HELLO_WORLD


def configured(extra: str) -> str:
    return ACCOUNT + extra + HELLO_WORLD

NOW = datetime(2026, 9, 24, 12, 0, 0).astimezone()


@dataclass
class Ran:
    code: int
    out: str
    err: str

    def under(self, heading: str) -> str:
        return self.out.partition(f"==> {heading}\n")[2].partition("==> ")[0]


@dataclass
class Machine:
    data_dir: Path
    home: Path
    system: ScriptedSystem = field(default_factory=ScriptedSystem)
    github: FakeGitHub = field(default_factory=FakeGitHub)
    desktop: FakeDesktop = field(default_factory=FakeDesktop)
    pr_processes: FakePrProcesses | None = None
    agent_runs: FakeAgentRuns | None = None
    now: datetime = NOW
    platform: str = "darwin"
    uv: str | None = "/tmp/bin/uv"
    python: str = "/tools/github-orchestrator/bin/python"
    shell_path: str = "/usr/bin:/bin"
    installed: set[str] = field(default_factory=lambda: {
        "gh", "claude", "git", "node", "npm"})
    answers: list[object] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    slept: list[float] = field(default_factory=list)
    while_asleep: list[Callable[[], None]] = field(default_factory=list)
    terminals: FakeTerminals = field(default_factory=FakeTerminals)
    instance: str | None = None
    others: dict[str, "Machine"] = field(default_factory=dict)
    answering_hubs: set[str] = field(default_factory=set)
    off_service_path: set[str] = field(default_factory=set)
    hub_pid: int = HUB_PID
    hub_state: str = "watching"
    located: dict[str, str] = field(default_factory=dict)
    graphical: bool = True
    newest_release: Mapping[str, object] | None = None
    pinned_config: bool = True
    releases_api: ScriptedReleasesApi = field(default_factory=ScriptedReleasesApi)

    @property
    def tool_dir(self) -> Path:
        return self.home / ".local" / "share" / "uv" / "tools"

    def hub_health(self, hub_url: str) -> Mapping[str, object] | None:
        if hub_url not in self.answering_hubs:
            return None
        return {"status": "ok", "pid": self.hub_pid, "serves": "hub", "hub_url": hub_url,
                "state": self.hub_state, "version": "0.4.0",
                "newest_release": self.newest_release}

    def another_instance(self, name: str) -> "Machine":
        data_dir = self.home / ".local" / "share" / f"github-orchestrator-{name}"
        data_dir.mkdir(parents=True)
        other = Machine(data_dir=data_dir, home=self.home, system=self.system, now=self.now,
                        platform=self.platform, instance=name)
        other.configure()
        self.others[str(data_dir)] = other
        return other

    def _other_container(self, environment: Mapping[str, str]) -> dishka.Container:
        return self.others[environment["GITHUB_ORCHESTRATOR_DATA_DIR"]].container()

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        if self.while_asleep:
            self.while_asleep.pop(0)()

    @property
    def config_path(self) -> Path:
        if self.instance is None and self.pinned_config:
            return self.data_dir / "config.toml"
        if self.instance is None:
            return self.home / ".config" / "github-orchestrator" / "config.toml"
        return self.home / ".config" / "github-orchestrator" / f"{self.instance}.toml"

    def configure(self, extra: str = "") -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(configured(extra))

    @property
    def environment(self) -> dict[str, str]:
        pinned = {"GITHUB_ORCHESTRATOR_CONFIG": str(self.config_path)} if (
            self.pinned_config or self.instance is not None) else {}
        return {"GITHUB_ORCHESTRATOR_DATA_DIR": str(self.data_dir), **pinned}

    def settings(self) -> Settings:
        settings: Settings = make_container(self.environment, self.home).get(Settings)
        return settings

    def processes(self) -> FakePrProcesses:
        if self.pr_processes is None:
            self.pr_processes = FakePrProcesses()
        return self.pr_processes

    def runs(self) -> FakeAgentRuns:
        if self.agent_runs is None:
            self.agent_runs = FakeAgentRuns(self.processes())
        return self.agent_runs

    def read_line(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.answers:
            raise AssertionError(f"prompted with no answer left: {prompt!r}")
        answer = self.answers.pop(0)
        if answer is EOFError:
            raise EOFError
        assert isinstance(answer, str)
        return answer

    def which(self, program: str, *, path: str | None = None) -> str | None:
        if path is not None and program in self.off_service_path:
            return None
        if program in self.located:
            return self.located[program]
        if program in self.installed:
            return f"/opt/homebrew/bin/{program}"
        return {"uv": self.uv}.get(program)

    def container(self) -> dishka.Container:
        settings = self.settings()
        return build_container(
            settings, fake_github(self.github),
            fake_provider(Desktop, self.desktop),
            fake_provider(PrProcesses, self.processes()),
            fake_provider(TerminalSessions, FakeTerminalSessions()),
            fake_provider(Terminals, self.terminals),
            fake_provider(Hub, FakeHub()),
            fake_agent_runs_roles(self.runs()),
            watcher_wiring(settings, self.home, releases_api=self.releases_api),
            notifications_wiring(settings),
            fake_provider(BoardPages, FakeBoardPages()),
            OtherInstancesWiring(self.environment, self.home, self._other_container),
            CliWiring(cli_config(settings, self.home, platform=self.platform,
                                 uid=self.system.uid, shell_path=self.shell_path,
                                 python=self.python, graphical=self.graphical,
                                 tool_dir=self.tool_dir),
                      self.system, self.read_line, self.which, self.hub_health),
            clocks=clocks_of(lambda: self.now, sleep=self.sleep))

    def cli(self) -> Cli:
        cli: Cli = self.container().get(Cli)
        return cli
