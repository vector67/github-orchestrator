import hashlib
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import KW_ONLY, dataclass, replace
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from threading import Lock, Thread
from typing import Protocol

import dishka
from dishka import Provider, Scope, from_context, provide

from github_orchestrator.agent_runs import (
    Agent,
    History,
    PrWork,
    Summaries,
    ThreadWork,
)
from github_orchestrator.agent_runs._report_commands import ReportCommands
from github_orchestrator.agent_runs._runs import (
    AgentRuns,
    command_argv,
    command_program,
)
from github_orchestrator.agent_runs._runs import Popen as AgentPopen
from github_orchestrator.agent_runs._summaries import Run as GistRun
from github_orchestrator.board_api import BoardApi, Hub
from github_orchestrator.board_api._app_files import APP_ROOT
from github_orchestrator.board_api._loopback import Listen, Listening, loopback_url
from github_orchestrator.board_api._pages import HubPages
from github_orchestrator.board_api._routes import fonts_in
from github_orchestrator.board_api.interface import (
    Dashboards,
    SetupDesk,
    TourMarker,
)
from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.change_detection._disk import DiskChangeDetection
from github_orchestrator.change_detection._would import WouldSaveChangeDetection
from github_orchestrator.cli import Cli
from github_orchestrator.cli._cli import OperatorCli
from github_orchestrator.cli._command_lines import (
    restart_line,
    setup_line,
    undismiss_line,
)
from github_orchestrator.cli._config import (
    CliConfig,
    OpenTerminals,
    Which,
)
from github_orchestrator.cli._config import Run as CliRun
from github_orchestrator.cli._doctor import InstanceChecks, MachineChecks, clone_problem
from github_orchestrator.cli._hub import HubHealth, hub_health
from github_orchestrator.cli._install_checks import requirement_fixes
from github_orchestrator.cli._report_commands import CliReportCommands
from github_orchestrator.cli._restart_all import Instance, OtherInstances
from github_orchestrator.cli._service import Service, service_for
from github_orchestrator.cli._setup import ReadLine
from github_orchestrator.cli._tool_install import service_python
from github_orchestrator.conversation import ConversationManagerFactory
from github_orchestrator.conversation._application.settings import ThreadsConfig
from github_orchestrator.conversation._threads import GitHubConversationManagerFactory
from github_orchestrator.desktop import Desktop
from github_orchestrator.desktop._command import Run as DesktopRun
from github_orchestrator.desktop._linux import LinuxDesktop
from github_orchestrator.desktop._macos import MacDesktop
from github_orchestrator.domain import (
    Clone,
    LocalClock,
    Monotonic,
    Pr,
    Repo,
    Sleep,
    UtcClock,
)
from github_orchestrator.github import Access, PullRequests, Reviews, Threads
from github_orchestrator.github._client import GhCliGitHub
from github_orchestrator.github._gh_cli import Run
from github_orchestrator.notifications import (
    BoardPages,
    Courier,
    Polling,
    PrStatus,
    Runs,
    Settling,
    Standing,
    ThreadNews,
    Worktrees,
)
from github_orchestrator.notifications._disk import (
    DiskCourier,
    DiskOutbox,
)
from github_orchestrator.notifications._news import News
from github_orchestrator.pr_event_queue import Intake, Queues, Worklist
from github_orchestrator.pr_event_queue._disk import DiskPrEventQueue
from github_orchestrator.pr_event_queue._would import WouldIntake
from github_orchestrator.pr_manager import Front, ManagedPr, PrManager
from github_orchestrator.pr_manager._browser_front import BrowserFront
from github_orchestrator.pr_manager._carry_out import EventCarryOut
from github_orchestrator.pr_manager._command_file import CommandFiles
from github_orchestrator.pr_manager._commands import ManagerCommands
from github_orchestrator.pr_manager._config import ManagerConfig
from github_orchestrator.pr_manager._dashboard_source import ConfigOf, DashboardSource
from github_orchestrator.pr_manager._git_palette import Run as GitRun
from github_orchestrator.pr_manager._manager import ManagerLoop
from github_orchestrator.pr_manager._status import StatusFiles
from github_orchestrator.pr_processes import AgentChanges, PrProcesses
from github_orchestrator.pr_processes._background import BackgroundPrProcesses
from github_orchestrator.pr_processes._background import Run as ManagerRun
from github_orchestrator.pr_processes._changes import DiskAgentChanges
from github_orchestrator.pr_processes._places import Places
from github_orchestrator.settings import (
    Boards,
    ConfigFile,
    Dismissals,
    Holds,
    Logs,
    Process,
)
from github_orchestrator.settings._config import (
    RepoEntry,
    TomlConfigFile,
    Tracker,
)
from github_orchestrator.settings._load import (
    INSTANCES_FOLDER,
    instance_name,
    load_settings,
)
from github_orchestrator.settings._load import instance_refused as instance_refused
from github_orchestrator.settings._load import other_instances as other_instances
from github_orchestrator.settings._load import with_instance as with_instance
from github_orchestrator.settings._logging import (
    DEFAULT_BACKUP_COUNT,
    DEFAULT_MAX_BYTES,
    LogFiles,
)
from github_orchestrator.settings._settings import Settings
from github_orchestrator.settings._switches import (
    FlagFileBoards,
    FlagFileDismissals,
    FlagFileHolds,
)
from github_orchestrator.terminal_sessions import Terminals, TerminalSessions
from github_orchestrator.terminal_sessions._pty import Popen as PtyPopen
from github_orchestrator.terminal_sessions._pty import PtyTerminals
from github_orchestrator.thread_records import ThreadRecords
from github_orchestrator.thread_records._files import DiskThreadRecords
from github_orchestrator.watcher import Releases, Watcher, WatcherHealth
from github_orchestrator.watcher._config import WatcherConfig
from github_orchestrator.watcher._cycle import PollingWatcher, Say, said_to_the_log
from github_orchestrator.watcher._health import HealthFiles
from github_orchestrator.watcher._holdings import WatchedHoldings
from github_orchestrator.watcher._leaving import Leaving
from github_orchestrator.watcher._placing import Placement, WindowPlacement
from github_orchestrator.watcher._releases import (
    Get,
    GitHubReleases,
    ReleasesApi,
    http_get,
)
from github_orchestrator.watcher._saving import CycleSaving, Saving
from github_orchestrator.watcher._setup import Archives, ConfigSetup, SetupSeams
from github_orchestrator.watcher._teardown import PrTeardown, Teardown
from github_orchestrator.watcher._tour import TourFile
from github_orchestrator.watcher._would import (
    WouldDeliver,
    WouldPlace,
    WouldSave,
    WouldServeHub,
    WouldTearDown,
)
from github_orchestrator.working_copies import WorkingCopies
from github_orchestrator.working_copies._git import GitWorkingCopies


class Wiring:
    def provider(self) -> type[Provider]:
        return _PROVIDERS[type(self)]

    def context(self) -> Mapping[object, object]:
        return {type(self): self}


type Part = Wiring | type[Provider]

_PROVIDERS: dict[type[Wiring], type[Provider]] = {}


def wires[P: type[Provider]](wiring: type[Wiring]) -> Callable[[P], P]:
    def attach(provider: P) -> P:
        _PROVIDERS[wiring] = provider
        return provider
    return attach


_ROOTS: dict[tuple[type[Provider], ...], dishka.Container] = {}


def wire(*parts: Part) -> dishka.Container:
    context = {key: value for part in parts if isinstance(part, Wiring)
               for key, value in part.context().items()}
    shape = tuple(part.provider() if isinstance(part, Wiring) else part for part in parts)
    root = _ROOTS.get(shape)
    if root is None:
        root = _ROOTS[shape] = dishka.make_container(*(provider() for provider in shape),
                                                     start_scope=Scope.RUNTIME)
    return root(context=context, lock_factory=Lock)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def local_now() -> datetime:
    return datetime.now().astimezone()


def which(program: str, *, path: str | None = None) -> str | None:
    return shutil.which(program, path=path)


@dataclass(frozen=True)
class ClocksWiring(Wiring):
    utc: UtcClock
    local: LocalClock
    monotonic: Monotonic
    sleep: Sleep

    def context(self) -> Mapping[object, object]:
        return {UtcClock: self.utc, LocalClock: self.local, Monotonic: self.monotonic,
                Sleep: self.sleep}


@wires(ClocksWiring)
class ClocksProvider(Provider):
    scope = Scope.APP
    utc = from_context(provides=UtcClock, scope=Scope.APP)
    local = from_context(provides=LocalClock, scope=Scope.APP)
    monotonic = from_context(provides=Monotonic, scope=Scope.APP)
    sleep = from_context(provides=Sleep, scope=Scope.APP)


SYSTEM_CLOCKS = ClocksWiring(UtcClock(utcnow), LocalClock(local_now), Monotonic(time.monotonic),
                             Sleep(time.sleep))


@dataclass(frozen=True)
class SettingsWiring(Wiring):
    settings: Settings


@wires(SettingsWiring)
class SettingsProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=SettingsWiring, scope=Scope.APP)

    @provide
    def settings(self, wiring: SettingsWiring) -> Settings:
        return wiring.settings

    @provide
    def config_file(self, wiring: SettingsWiring) -> ConfigFile:
        settings = wiring.settings
        return TomlConfigFile(settings.config_path, settings.problem, setup_line(),
                              restart_line(), settings.data_dir)


@dataclass(frozen=True)
class LogsWiring(Wiring):
    logs_dir: Path
    level: str
    _: KW_ONLY
    max_bytes: int = DEFAULT_MAX_BYTES
    backup_count: int = DEFAULT_BACKUP_COUNT


@wires(LogsWiring)
class LogsProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=LogsWiring, scope=Scope.APP)

    @provide
    def logs(self, wiring: LogsWiring) -> Logs:
        return LogFiles(wiring.logs_dir, wiring.level, max_bytes=wiring.max_bytes,
                        backup_count=wiring.backup_count)


@dataclass(frozen=True)
class SwitchesWiring(Wiring):
    on_hold_dir: Path
    dismissed_dir: Path
    board_dir: Path


@wires(SwitchesWiring)
class SwitchesProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=SwitchesWiring, scope=Scope.APP)

    @provide
    def holds(self, wiring: SwitchesWiring) -> Holds:
        return FlagFileHolds(wiring.on_hold_dir)

    @provide
    def dismissals(self, wiring: SwitchesWiring) -> Dismissals:
        return FlagFileDismissals(wiring.dismissed_dir)

    @provide
    def boards(self, wiring: SwitchesWiring) -> Boards:
        return FlagFileBoards(wiring.board_dir)


@dataclass(frozen=True)
class GitHubWiring(Wiring):
    account: str
    run: Run


@wires(GitHubWiring)
class GitHubProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=GitHubWiring, scope=Scope.APP)

    @provide
    def client(self, wiring: GitHubWiring) -> GhCliGitHub:
        return GhCliGitHub(wiring.account, wiring.run)

    @provide
    def pull_requests(self, client: GhCliGitHub) -> PullRequests:
        return client

    @provide
    def threads(self, client: GhCliGitHub) -> Threads:
        return client

    @provide
    def reviews(self, client: GhCliGitHub) -> Reviews:
        return client

    @provide
    def access(self, client: GhCliGitHub) -> Access:
        return client


@dataclass(frozen=True)
class DesktopWiring(Wiring):
    run: DesktopRun
    apps: Path
    platform: str


@wires(DesktopWiring)
class DesktopProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=DesktopWiring, scope=Scope.APP)

    @provide
    def desktop(self, wiring: DesktopWiring) -> Desktop:
        if wiring.platform == "darwin":
            return MacDesktop(wiring.run, wiring.apps)
        return LinuxDesktop(wiring.run)


@dataclass(frozen=True)
class PrEventQueueWiring(Wiring):
    queues_dir: Path


@wires(PrEventQueueWiring)
class PrEventQueueProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=PrEventQueueWiring, scope=Scope.APP)

    @provide
    def event_queue(self, wiring: PrEventQueueWiring) -> DiskPrEventQueue:
        return DiskPrEventQueue(wiring.queues_dir)

    @provide
    def intake(self, event_queue: DiskPrEventQueue) -> Intake:
        return event_queue

    @provide
    def worklist(self, event_queue: DiskPrEventQueue) -> Worklist:
        return event_queue

    @provide
    def queues(self, event_queue: DiskPrEventQueue) -> Queues:
        return event_queue

    @provide
    def settling(self, event_queue: DiskPrEventQueue) -> Settling:
        return event_queue


@dataclass(frozen=True)
class NotificationsWiring(Wiring):
    notifications_dir: Path


@wires(NotificationsWiring)
class NotificationsProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=NotificationsWiring, scope=Scope.APP)

    @provide
    def news(self, wiring: NotificationsWiring, clock: LocalClock) -> News:
        return News(DiskOutbox(wiring.notifications_dir, clock))

    @provide
    def thread_news(self, news: News) -> ThreadNews:
        return news

    @provide
    def runs(self, news: News) -> Runs:
        return news

    @provide
    def worktrees(self, news: News) -> Worktrees:
        return news

    @provide
    def pr_status(self, news: News) -> PrStatus:
        return news

    @provide
    def polling(self, news: News) -> Polling:
        return news

    @provide
    def courier(self, wiring: NotificationsWiring, clock: LocalClock, desktop: Desktop,
                summaries: Summaries, standing: Standing, settling: Settling,
                pages: BoardPages) -> Courier:
        return DiskCourier(wiring.notifications_dir, desktop, clock, summaries,
                           standing, settling, pages)


@dataclass(frozen=True)
class BoardPagesWiring(Wiring):
    pages: BoardPages


@wires(BoardPagesWiring)
class BoardPagesProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=BoardPagesWiring, scope=Scope.APP)

    @provide
    def board_pages(self, wiring: BoardPagesWiring) -> BoardPages:
        return wiring.pages


@dataclass(frozen=True)
class WorkingCopiesWiring(Wiring):
    mismatched_dir: Path
    worktree_conflicts_dir: Path
    thread_worktrees_dir: Path
    clones: Mapping[Repo, Clone]
    _: KW_ONLY
    grace_seconds: int
    run_idle_seconds: int


@wires(WorkingCopiesWiring)
class WorkingCopiesProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=WorkingCopiesWiring, scope=Scope.APP)

    @provide
    def working_copies(self, wiring: WorkingCopiesWiring, pull_requests: PullRequests,
                       worktrees: Worktrees) -> WorkingCopies:
        return GitWorkingCopies(pull_requests, worktrees,
                                wiring.mismatched_dir, wiring.worktree_conflicts_dir,
                                wiring.thread_worktrees_dir, wiring.clones,
                                grace_seconds=wiring.grace_seconds,
                                run_idle_seconds=wiring.run_idle_seconds)


def working_copies_wiring(settings: Settings) -> WorkingCopiesWiring:
    config = settings.config
    return WorkingCopiesWiring(
        mismatched_dir=settings.mismatched_dir,
        worktree_conflicts_dir=settings.worktree_conflicts_dir,
        thread_worktrees_dir=settings.thread_worktrees_dir,
        clones=settings.repos,
        grace_seconds=config.mismatch_grace_seconds,
        run_idle_seconds=config.mismatch_run_idle_seconds,
    )


@dataclass(frozen=True)
class ThreadRecordsWiring(Wiring):
    threads_dir: Path


@wires(ThreadRecordsWiring)
class ThreadRecordsProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=ThreadRecordsWiring, scope=Scope.APP)

    @provide
    def thread_records(self, wiring: ThreadRecordsWiring) -> ThreadRecords:
        return DiskThreadRecords(wiring.threads_dir)


@dataclass(frozen=True)
class ChangeDetectionWiring(Wiring):
    state_dir: Path
    account: str
    poll_interval: int


@wires(ChangeDetectionWiring)
class ChangeDetectionProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=ChangeDetectionWiring, scope=Scope.APP)

    @provide
    def change_detection(self, wiring: ChangeDetectionWiring,
                         clock: UtcClock) -> ChangeDetection:
        return DiskChangeDetection(wiring.state_dir, wiring.account, wiring.poll_interval,
                                   clock)


@dataclass(frozen=True)
class BackgroundPrProcessesWiring(Wiring):
    run: ManagerRun
    places: Places


@wires(BackgroundPrProcessesWiring)
class BackgroundPrProcessesProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=BackgroundPrProcessesWiring, scope=Scope.APP)

    @provide
    def pr_processes(self, wiring: BackgroundPrProcessesWiring, terminals: Terminals) -> PrProcesses:
        return BackgroundPrProcesses(wiring.run, wiring.places, terminals)


FIRST_CONNECTION_SECONDS = 30.0
SHORT_ENOUGH_FOR_A_SOCKET = Path("/tmp")


def terminal_sessions_dir(settings: Settings) -> Path:
    digest = hashlib.sha256(str(settings.data_dir.resolve()).encode()).hexdigest()[:16]
    return SHORT_ENOUGH_FOR_A_SOCKET / f"gho-{os.getuid()}" / digest


@dataclass(frozen=True)
class TerminalSessionsWiring(Wiring):
    popen: PtyPopen
    environment: Mapping[str, str]
    directory: Path
    pr: Pr | None
    _: KW_ONLY
    first_connection_seconds: float = FIRST_CONNECTION_SECONDS


@wires(TerminalSessionsWiring)
class TerminalSessionsProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=TerminalSessionsWiring, scope=Scope.APP)

    @provide
    def pty_terminals(self, wiring: TerminalSessionsWiring) -> PtyTerminals:
        return PtyTerminals(wiring.popen, wiring.environment, wiring.directory,
                            first_connection_seconds=wiring.first_connection_seconds)

    @provide
    def terminals(self, terminals: PtyTerminals) -> Terminals:
        return terminals

    @provide
    def terminal_sessions(self, wiring: TerminalSessionsWiring,
                          terminals: PtyTerminals) -> TerminalSessions:
        if wiring.pr is None:
            return terminals.unmanaged()
        return terminals.of(wiring.pr)


class AgentChangesProvider(Provider):
    scope = Scope.APP

    @provide
    def agent_changes(self) -> AgentChanges:
        return DiskAgentChanges()


@dataclass(frozen=True)
class ReportCommandsWiring(Wiring):
    python: str


@wires(ReportCommandsWiring)
class ReportCommandsProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=ReportCommandsWiring, scope=Scope.APP)

    @provide
    def report_commands(self, wiring: ReportCommandsWiring) -> ReportCommands:
        return CliReportCommands(wiring.python)


@dataclass(frozen=True)
class AgentRunsWiring(Wiring):
    popen: AgentPopen
    run: GistRun
    _: KW_ONLY
    agent: Agent
    command: str
    model: str
    summary_model: str
    pytest_workers: int
    transcripts_dir: Path
    runs_log: Path


@wires(AgentRunsWiring)
class AgentRunsProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=AgentRunsWiring, scope=Scope.APP)

    @provide
    def runs(self, wiring: AgentRunsWiring, monotonic: Monotonic,
             pr_processes: PrProcesses, agent_changes: AgentChanges,
             report_commands: ReportCommands) -> AgentRuns:
        return AgentRuns(wiring.popen, wiring.run, monotonic,
                               pr_processes=pr_processes, report_commands=report_commands,
                               changes_file=agent_changes.file_name(),
                               agent=wiring.agent, command=wiring.command,
                               model=wiring.model,
                               summary_model=wiring.summary_model,
                               pytest_workers=wiring.pytest_workers,
                               transcripts_dir=wiring.transcripts_dir,
                               runs_log=wiring.runs_log)

    @provide
    def history(self, runs: AgentRuns) -> History:
        return runs

    @provide
    def summaries(self, runs: AgentRuns) -> Summaries:
        return runs

    @provide
    def pr_work(self, runs: AgentRuns) -> PrWork:
        return runs

    @provide
    def thread_work(self, runs: AgentRuns) -> ThreadWork:
        return runs


@dataclass(frozen=True)
class ConversationWiring(Wiring):
    config: ThreadsConfig

    def context(self) -> Mapping[object, object]:
        return {ThreadsConfig: self.config}


@wires(ConversationWiring)
class ConversationProvider(Provider):
    scope = Scope.APP
    config = from_context(provides=ThreadsConfig, scope=Scope.APP)
    github_conversation_managers = provide(GitHubConversationManagerFactory)

    @provide
    def conversation_managers(self, conversation_managers: GitHubConversationManagerFactory) -> ConversationManagerFactory:
        return conversation_managers

    @provide
    def standing(self, conversation_managers: GitHubConversationManagerFactory) -> Standing:
        return conversation_managers


@dataclass(frozen=True)
class WatcherWiring(Wiring):
    config: WatcherConfig
    seams: SetupSeams
    releases_api: ReleasesApi

    def context(self) -> Mapping[object, object]:
        return {WatcherConfig: self.config, SetupSeams: self.seams,
                ReleasesApi: self.releases_api}


@wires(WatcherWiring)
class WatcherProvider(Provider):
    scope = Scope.APP
    config = from_context(provides=WatcherConfig, scope=Scope.APP)
    seams = from_context(provides=SetupSeams, scope=Scope.APP)
    releases_api = from_context(provides=ReleasesApi, scope=Scope.APP)
    holdings = provide(WatchedHoldings)
    leaving = provide(Leaving)
    setup = provide(ConfigSetup, provides=SetupDesk)
    tour = provide(TourFile, provides=TourMarker)
    placement = provide(WindowPlacement, provides=Placement)
    teardown = provide(PrTeardown, provides=Teardown)
    saving = provide(CycleSaving, provides=Saving)
    watcher = provide(PollingWatcher, provides=Watcher)
    watcher_health = provide(HealthFiles, provides=WatcherHealth)

    @provide
    def say(self) -> Say:
        return said_to_the_log

    @provide
    def releases(self, config: WatcherConfig, api: ReleasesApi, clock: UtcClock) -> Releases:
        return GitHubReleases(api.get, config.newest_release, clock,
                              enabled=config.check_for_updates, token=config.github_token)

    @provide
    def archives(self, change_detection: ChangeDetection, queues: Queues, history: History,
                 holds: Holds) -> Archives:
        return Archives(state=change_detection, queues=queues, transcripts=history,
                        on_hold=holds)


def say_dry_run(line: str) -> None:
    print(f"[dry-run] {line}")


@dataclass(frozen=True)
class WouldSaveWiring(Wiring):
    say: Callable[[str], None]


@wires(WouldSaveWiring)
class WouldSaveProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=WouldSaveWiring, scope=Scope.APP)

    @provide
    def change_detection(self, wiring: WouldSaveWiring, detection: ChangeDetectionWiring,
                         clock: UtcClock) -> ChangeDetection:
        return WouldSaveChangeDetection(detection.state_dir, detection.account,
                                        detection.poll_interval, clock, wiring.say)


@dataclass(frozen=True)
class WouldEnqueueWiring(Wiring):
    say: Callable[[str], None]
    agents_enabled: bool


@wires(WouldEnqueueWiring)
class WouldEnqueueProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=WouldEnqueueWiring, scope=Scope.APP)

    @provide
    def would_intake(self, wiring: WouldEnqueueWiring,
                     change_detection: ChangeDetection) -> WouldIntake:
        return WouldIntake(change_detection, wiring.agents_enabled, wiring.say)

    @provide
    def intake(self, would_intake: WouldIntake) -> Intake:
        return would_intake


@dataclass(frozen=True)
class WouldWatchWiring(Wiring):
    say: Callable[[str], None]


@wires(WouldWatchWiring)
class WouldWatchProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=WouldWatchWiring, scope=Scope.APP)

    @provide
    def say(self, wiring: WouldWatchWiring) -> Say:
        return wiring.say

    @provide
    def placement(self, wiring: WouldWatchWiring, config: WatcherConfig, dismissals: Dismissals,
                  worklist: Worklist, would_intake: WouldIntake) -> Placement:
        return WouldPlace(config, dismissals=dismissals, worklist=worklist,
                          enqueued=would_intake.enqueued, say=wiring.say)

    @provide
    def teardown(self, wiring: WouldWatchWiring) -> Teardown:
        return WouldTearDown(wiring.say)

    @provide
    def saving(self) -> Saving:
        return WouldSave()

    @provide
    def hub(self, wiring: WouldWatchWiring) -> Hub:
        return WouldServeHub(wiring.say)

    @provide
    def courier(self) -> Courier:
        return WouldDeliver()


def dry_run_parts(settings: Settings) -> list[Part]:
    return [WouldSaveWiring(say_dry_run),
            WouldEnqueueWiring(say_dry_run, settings.config.agents_enabled),
            WouldWatchWiring(say_dry_run)]


class BrowserFrontProvider(Provider):
    scope = Scope.APP
    front = provide(BrowserFront, provides=Front)


def listen_on_loopback(port: int) -> Listening:
    from github_orchestrator.board_api._server import listen_on_loopback as listen
    return listen(port)


HEARTBEAT_SECONDS = 15.0
STREAM_CHECK_SECONDS = 0.5


@dataclass(frozen=True)
class BoardApiWiring(Wiring):
    listen: Listen
    _: KW_ONLY
    app_root: Path
    font_dir: str | None
    check_presence: bool
    hub_port: int
    first_names_only: bool
    heartbeat_seconds: float = HEARTBEAT_SECONDS
    check_seconds: float = STREAM_CHECK_SECONDS


@wires(BoardApiWiring)
class BoardApiProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=BoardApiWiring, scope=Scope.APP)

    @provide
    def board_api(self, wiring: BoardApiWiring, conversation_managers: ConversationManagerFactory,
                  working_copies: WorkingCopies, terminals: TerminalSessions,
                  clock: UtcClock) -> BoardApi:
        from github_orchestrator.board_api._server import ServedBoardApi
        return ServedBoardApi(wiring.listen, conversation_managers, working_copies, terminals,
                              app_root=wiring.app_root, font_dir=wiring.font_dir,
                              check_presence=wiring.check_presence, hub_port=wiring.hub_port,
                              heartbeat_seconds=wiring.heartbeat_seconds,
                              check_seconds=wiring.check_seconds,
                              first_names_only=wiring.first_names_only, clock=clock)


OPEN_STREAMS = 200


@dataclass(frozen=True)
class HubWiring(Wiring):
    listen: Listen
    _: KW_ONLY
    app_root: Path
    font_dir: str | None
    watching: Collection[Repo]
    version: str | None
    open_streams: int = OPEN_STREAMS


@wires(HubWiring)
class HubProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=HubWiring, scope=Scope.APP)

    @provide
    def hub(self, wiring: HubWiring, clock: UtcClock, dashboards: Dashboards,
            history: History, watcher_health: WatcherHealth, config_file: ConfigFile,
            setup: SetupDesk, releases: Releases, tour: TourMarker) -> Hub:
        from github_orchestrator.board_api._hub import ServedHub
        return ServedHub(wiring.listen, app_root=wiring.app_root, font_dir=wiring.font_dir,
                         dashboards=dashboards, ledger=history, pulse=watcher_health,
                         clock=clock, watching=wiring.watching, version=wiring.version,
                         problem=config_file.check, setup=setup, releases=releases, tour=tour,
                         open_streams=wiring.open_streams)


@dataclass(frozen=True)
class PrManagerWiring(Wiring):
    config: ManagerConfig
    run: GitRun

    def context(self) -> Mapping[object, object]:
        return {ManagerConfig: self.config, GitRun: self.run}


@wires(PrManagerWiring)
class PrManagerProvider(Provider):
    scope = Scope.APP
    config = from_context(provides=ManagerConfig, scope=Scope.APP)
    run = from_context(provides=GitRun, scope=Scope.APP)
    commands = provide(ManagerCommands)
    events = provide(EventCarryOut)
    pr_manager = provide(ManagerLoop, provides=PrManager)


@dataclass(frozen=True)
class DashboardSourceWiring(Wiring):
    config_of: ConfigOf
    data_dir: Path

    def context(self) -> Mapping[object, object]:
        return {ConfigOf: self.config_of, DashboardSourceWiring: self}


@wires(DashboardSourceWiring)
class DashboardSourceProvider(Provider):
    scope = Scope.APP
    config_of = from_context(provides=ConfigOf, scope=Scope.APP)
    wiring = from_context(provides=DashboardSourceWiring, scope=Scope.APP)
    source = provide(DashboardSource)

    @provide
    def dashboards(self, source: DashboardSource) -> Dashboards:
        return source

    @provide
    def status_files(self, wiring: DashboardSourceWiring, clock: UtcClock) -> StatusFiles:
        return StatusFiles(wiring.data_dir, clock)

    @provide
    def command_files(self, wiring: DashboardSourceWiring) -> CommandFiles:
        return CommandFiles(wiring.data_dir)


class EveryTerminal:
    def __init__(self, terminals: Terminals) -> None:
        self._terminals = terminals

    def count(self) -> int:
        return sum(len(sessions.listed()) for sessions in self._terminals.everywhere())

    def close(self) -> int:
        closed = 0
        for sessions in self._terminals.everywhere():
            closed += len(sessions.listed())
            sessions.hang_up()
        return closed


@dataclass(frozen=True)
class CliWiring(Wiring):
    config: CliConfig
    run: CliRun
    read_line: ReadLine
    which: Which
    hub_health: HubHealth

    def context(self) -> Mapping[object, object]:
        return {CliConfig: self.config, CliRun: self.run, ReadLine: self.read_line,
                Which: self.which, HubHealth: self.hub_health}


@wires(CliWiring)
class CliProvider(Provider):
    scope = Scope.APP
    config = from_context(provides=CliConfig, scope=Scope.APP)
    run = from_context(provides=CliRun, scope=Scope.APP)
    read_line = from_context(provides=ReadLine, scope=Scope.APP)
    which = from_context(provides=Which, scope=Scope.APP)
    hub_health = from_context(provides=HubHealth, scope=Scope.APP)
    cli = provide(OperatorCli, provides=Cli)
    checks = provide(InstanceChecks)
    machine = provide(MachineChecks)

    @provide
    def open_terminals(self, terminals: Terminals) -> OpenTerminals:
        return EveryTerminal(terminals)

    @provide
    def service(self, config: CliConfig, run: CliRun, sleep: Sleep, logs: Logs) -> Service:
        return service_for(config, run, sleep, logs.path(Process.LAUNCHD))


class ContainerInstances:
    def __init__(self, env: Mapping[str, str], home: Path,
                 build: Callable[[Mapping[str, str]], dishka.Container]) -> None:
        self._env = env
        self._home = home
        self._build = build

    def load(self) -> list[Instance]:
        return [self._instance(name, self._build({**self._env, **environment}))
                for name, environment in other_instances(self._env, self._home).items()]

    def _instance(self, name: str | None, container: dishka.Container) -> Instance:
        return Instance(name, container.get(PrProcesses),
                        container.get(Queues), container.get(WatcherHealth),
                        container.get(OpenTerminals), container.get(Service),
                        container.get(InstanceChecks), container.get(ConfigFile),
                        container.get(Settings).data_dir)


@dataclass(frozen=True)
class OtherInstancesWiring(Wiring):
    env: Mapping[str, str]
    home: Path
    build: Callable[[Mapping[str, str]], dishka.Container]


@wires(OtherInstancesWiring)
class OtherInstancesProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=OtherInstancesWiring, scope=Scope.APP)

    @provide
    def others(self, wiring: OtherInstancesWiring) -> OtherInstances:
        return ContainerInstances(wiring.env, wiring.home, wiring.build)


def uv_tool_dir(env: Mapping[str, str], home: Path) -> Path:
    if env.get("UV_TOOL_DIR"):
        return Path(env["UV_TOOL_DIR"])
    data_home = Path(env["XDG_DATA_HOME"]) if env.get("XDG_DATA_HOME") else home / ".local" / "share"
    return data_home / "uv" / "tools"


def cli_config(settings: Settings, home: Path, *, platform: str, uid: int,
               shell_path: str, python: str, graphical: bool, tool_dir: Path) -> CliConfig:
    config = settings.config
    runs_on = service_python(python, tool_dir)
    return CliConfig(
        python=runs_on.python,
        python_note=runs_on.note,
        child_environment=settings.child_environment(),
        shell_path=shell_path,
        archive_dir=settings.archive_dir,
        data_dir=settings.data_dir,
        config_folder=home / INSTANCES_FOLDER,
        restart_lock=settings.restart_lock,
        repos=settings.repos,
        gh_account=config.gh_account,
        agents_enabled=config.agents_enabled,
        agent=config.agent,
        agent_argv=tuple(command_argv(config.agent_command)),
        agent_program=command_program(config.agent_command),
        summary_model=config.summary_model,
        home=home,
        platform=platform,
        uid=uid,
        hub_url=loopback_url(config.hub_port),
        instance=instance_name(settings.config_path, home),
        font_problem=fonts_in(board_font_dir(settings)).problem,
        version=installed_version(),
        graphical=graphical,
        check_for_updates=config.check_for_updates,
    )


def manager_config(settings: Settings, managed: ManagedPr) -> ManagerConfig:
    config = settings.config
    return ManagerConfig(
        pr=managed.pr,
        worktree=managed.worktree,
        account=config.gh_account,
        agents_enabled=config.agents_enabled,
        agent_name=config.agent.display_name,
        refresh_interval=config.dashboard_refresh_interval,
        undismiss_command=undismiss_line(managed.pr),
    )


def dashboard_source_wiring(settings: Settings) -> DashboardSourceWiring:
    return DashboardSourceWiring(
        lambda pr, worktree: manager_config(settings, ManagedPr(pr=pr, worktree=worktree)),
        settings.data_dir)


def installed_version() -> str | None:
    try:
        return metadata.version("github-orchestrator")
    except metadata.PackageNotFoundError:
        return None


def board_font_dir(settings: Settings) -> str | None:
    return os.path.expanduser(settings.config.board_font_dir) or None


def watcher_config(settings: Settings, home: Path, github_token: str | None) -> WatcherConfig:
    config = settings.config
    return WatcherConfig(
        repos=settings.repos,
        gh_account=config.gh_account,
        config_location=str(settings.config_path),
        agents_enabled=config.agents_enabled,
        poll_interval=config.watcher_poll_interval,
        heartbeat=settings.watcher_heartbeat,
        lock=settings.watcher_lock,
        failures=settings.watcher_failures,
        log_file=settings.log_path(Process.WATCHER),
        hub_port=config.hub_port,
        home=home,
        archive_dir=settings.archive_dir,
        newest_release=settings.newest_release,
        tour_due=settings.tour_due,
        check_for_updates=config.check_for_updates,
        github_token=github_token,
    )


def conversation_config(settings: Settings) -> ThreadsConfig:
    config = settings.config
    return ThreadsConfig(
        gh_account=config.gh_account,
        agents_enabled=config.agents_enabled,
        max_thread_runs=config.max_thread_runs,
        agent_timeout=config.agent_timeout,
        poll_interval=config.watcher_poll_interval,
        tracker=None if config.tracker is Tracker.NONE else config.tracker.value,
        tracker_project=config.tracker_project or None,
    )


def pr_processes_places(settings: Settings) -> Places:
    return Places(
        manager_records_dir=settings.pr_managers_dir,
        manager_logs_dir=settings.logs_dir / "pr_managers",
        environment=settings.child_environment(),
    )


def logs_wiring(settings: Settings) -> LogsWiring:
    return LogsWiring(settings.logs_dir, settings.config.log_level)


def switches_wiring(settings: Settings) -> SwitchesWiring:
    return SwitchesWiring(settings.on_hold_dir, settings.dismissed_dir, settings.board_dir)


def pr_event_queue_wiring(settings: Settings) -> PrEventQueueWiring:
    return PrEventQueueWiring(settings.queues_dir)


def notifications_wiring(settings: Settings) -> NotificationsWiring:
    return NotificationsWiring(settings.notifications_dir)


def thread_records_wiring(settings: Settings) -> ThreadRecordsWiring:
    return ThreadRecordsWiring(settings.threads_dir)


def change_detection_wiring(settings: Settings) -> ChangeDetectionWiring:
    return ChangeDetectionWiring(settings.state_dir, settings.config.gh_account,
                                 settings.config.watcher_poll_interval)


def conversation_wiring(settings: Settings) -> ConversationWiring:
    return ConversationWiring(conversation_config(settings))


def in_a_thread(work: Callable[[], None]) -> None:
    Thread(target=work, name="setup-write").start()


def watcher_wiring(settings: Settings, home: Path, *,
                   clone_problem_at: Callable[[Repo, Path], str | None] | None = None,
                   requirements: Callable[[], Sequence[tuple[str, str | None]]] | None = None,
                   run_in: Callable[[Callable[[], None]], None] = in_a_thread,
                   releases_api: Get = http_get,
                   github_token: str | None = None) -> WatcherWiring:
    agent = command_program(settings.config.agent_command)
    return WatcherWiring(watcher_config(settings, home, github_token), SetupSeams(
        clone_problem=clone_problem_at or clone_problem(subprocess.run),
        requirements=requirements or (lambda: requirement_fixes(which, settings.config.agent, agent,
                                                                      sys.platform)),
        run_in=run_in, agent_name=settings.config.agent.display_name), ReleasesApi(releases_api))


class PreviewGitHub(PullRequests, Threads, Reviews, Access, Protocol):
    pass


class PreviewAgentRuns(Summaries, ThreadWork, History, Protocol):
    pass


@dataclass(frozen=True)
class PreviewFakesWiring(Wiring):
    github: PreviewGitHub
    desktop: Desktop
    agent_runs: PreviewAgentRuns
    pr_processes: PrProcesses


@wires(PreviewFakesWiring)
class PreviewFakesProvider(Provider):
    scope = Scope.APP
    wiring = from_context(provides=PreviewFakesWiring, scope=Scope.APP)

    @provide
    def pull_requests(self, wiring: PreviewFakesWiring) -> PullRequests:
        return wiring.github

    @provide
    def threads(self, wiring: PreviewFakesWiring) -> Threads:
        return wiring.github

    @provide
    def reviews(self, wiring: PreviewFakesWiring) -> Reviews:
        return wiring.github

    @provide
    def access(self, wiring: PreviewFakesWiring) -> Access:
        return wiring.github

    @provide
    def desktop(self, wiring: PreviewFakesWiring) -> Desktop:
        return wiring.desktop

    @provide
    def summaries(self, wiring: PreviewFakesWiring) -> Summaries:
        return wiring.agent_runs

    @provide
    def thread_work(self, wiring: PreviewFakesWiring) -> ThreadWork:
        return wiring.agent_runs

    @provide
    def history(self, wiring: PreviewFakesWiring) -> History:
        return wiring.agent_runs

    @provide
    def pr_processes(self, wiring: PreviewFakesWiring) -> PrProcesses:
        return wiring.pr_processes


def preview_container(env: Mapping[str, str], home: Path, *, data_dir: Path,
                      repo: Repo, local_path: Path, github: PreviewGitHub, desktop: Desktop,
                      agent_runs: PreviewAgentRuns, pr_processes: PrProcesses,
                      agents_enabled: bool) -> tuple[dishka.Container, str]:
    loaded = load_settings(env, home)
    settings = replace(loaded, data_dir=data_dir,
                       config=replace(loaded.config, agents_enabled=agents_enabled,
                                      repos=(RepoEntry(repo, str(local_path)),)))
    return wire(
        SYSTEM_CLOCKS,
        SettingsWiring(settings),
        PreviewFakesWiring(github, desktop, agent_runs, pr_processes),
        pr_event_queue_wiring(settings),
        switches_wiring(settings),
        notifications_wiring(settings),
        BoardPagesWiring(HubPages(settings.config.hub_port)),
        working_copies_wiring(settings),
        thread_records_wiring(settings),
        change_detection_wiring(settings),
        conversation_wiring(settings),
        TerminalSessionsWiring(subprocess.Popen, settings.child_environment(),
                               terminal_sessions_dir(settings), None),
        BoardApiWiring(listen_on_loopback, app_root=APP_ROOT,
                       font_dir=board_font_dir(settings), check_presence=False,
                       hub_port=settings.config.hub_port,
                       first_names_only=settings.config.first_names_only),
        dashboard_source_wiring(settings),
    ), settings.config.gh_account


def mode_wirings(settings: Settings, managed: ManagedPr | None) -> list[Part]:
    places = pr_processes_places(settings)
    sessions = TerminalSessionsWiring(
        subprocess.Popen, settings.child_environment(),
        terminal_sessions_dir(settings), None if managed is None else managed.pr)
    windows = BackgroundPrProcessesWiring(subprocess.run, places)
    pages = BoardPagesWiring(HubPages(settings.config.hub_port))
    fronts: list[Part] = [] if managed is None else [BrowserFrontProvider]
    return [sessions, windows, pages, *fronts]


def make_container(env: Mapping[str, str], home: Path,
                   managed: ManagedPr | None = None, *,
                   check_presence: bool = True, dry_run: bool = False) -> dishka.Container:
    settings = load_settings(env, home)
    managers = [] if managed is None else [
        PrManagerWiring(manager_config(settings, managed), subprocess.run),
    ]
    return wire(
        SYSTEM_CLOCKS,
        SettingsWiring(settings),
        logs_wiring(settings),
        switches_wiring(settings),
        GitHubWiring(settings.config.gh_account, subprocess.run),
        DesktopWiring(subprocess.run, home / "Applications", platform=sys.platform),
        pr_event_queue_wiring(settings),
        notifications_wiring(settings),
        working_copies_wiring(settings),
        thread_records_wiring(settings),
        change_detection_wiring(settings),
        *mode_wirings(settings, managed),
        AgentChangesProvider,
        ReportCommandsWiring(sys.executable),
        AgentRunsWiring(
            subprocess.Popen, subprocess.run,
            agent=settings.config.agent,
            command=settings.config.agent_command,
            model=settings.config.agent_model,
            summary_model=settings.config.summary_model,
            pytest_workers=settings.config.pytest_workers,
            transcripts_dir=settings.transcripts_dir,
            runs_log=settings.runs_log,
        ),
        conversation_wiring(settings),
        watcher_wiring(settings, home, github_token=env.get("GITHUB_ORCHESTRATOR_GITHUB_TOKEN")),
        CliWiring(cli_config(settings, home, platform=sys.platform, uid=os.getuid(),
                             shell_path=env.get("PATH", ""), python=sys.executable,
                             tool_dir=uv_tool_dir(env, home),
                             graphical=sys.platform == "darwin" or bool(
                                 env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))),
                  subprocess.run, input, which, hub_health),
        OtherInstancesWiring(env, home, lambda environment: make_container(environment, home)),
        BoardApiWiring(listen_on_loopback, app_root=APP_ROOT,
                       font_dir=board_font_dir(settings), check_presence=check_presence,
                       hub_port=settings.config.hub_port,
                       first_names_only=settings.config.first_names_only),
        HubWiring(listen_on_loopback, app_root=APP_ROOT, font_dir=board_font_dir(settings),
                  watching=tuple(settings.repos), version=installed_version()),
        dashboard_source_wiring(settings),
        *managers,
        *(dry_run_parts(settings) if dry_run else []),
    )
