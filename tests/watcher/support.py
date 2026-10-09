from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dishka

from github_orchestrator.board_api import Hub
from github_orchestrator.board_api.fake import FakeHub
from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.desktop import Desktop
from github_orchestrator.desktop.fake import FakeDesktop
from github_orchestrator.domain import Repo
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications import BoardPages
from github_orchestrator.notifications.fake import FakeBoardPages, FakeNotifications
from github_orchestrator.pr_processes import PrProcesses
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings import Logs
from github_orchestrator.settings.fake import Settings
from github_orchestrator.thread_records import ThreadRecords
from github_orchestrator.watcher import Health, Watcher, WatcherHealth
from github_orchestrator.wiring import (
    Part,
    dry_run_parts,
    notifications_wiring,
    watcher_wiring,
)
from github_orchestrator.working_copies import WorkingCopies
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.conftest import (
    build_container,
    clocks_of,
    fake_agent_runs,
    fake_agent_runs_roles,
    fake_github,
    fake_notifications,
    fake_provider,
)
from tests.pr_event_queue.support import PrEventQueue, event_queue_provider
from tests.watcher.scripted_releases import ScriptedReleasesApi

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def at_now() -> datetime:
    return NOW


def never_sleeps(seconds: float) -> None:
    raise AssertionError(f"the watcher slept {seconds}s in a test that runs one cycle")


class StopAfter:
    def __init__(self, cycles: int, seen: list[object]) -> None:
        self.cycles = cycles
        self.seen = seen
        self.slept: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)
        if len(self.seen) >= self.cycles:
            raise KeyboardInterrupt


def stop_after(cycles: int, seen: list[object]) -> StopAfter:
    return StopAfter(cycles, seen)


def the_clone(settings: Settings) -> Path:
    [clone] = settings.repos.values()
    return clone.path


def watching(settings: Settings) -> FakeGitHub:
    github = FakeGitHub(account=settings.config.gh_account)
    github.repos.update(settings.repos)
    return github


def watcher_container(settings: Settings, *, github: FakeGitHub | None = None,
                      desktop: Desktop | None = None, event_queue: PrEventQueue | None = None,
                      pr_processes: PrProcesses | None = None,
                      change_detection: ChangeDetection | None = None,
                      thread_records: ThreadRecords | None = None,
                      working_copies: WorkingCopies | None = None,
                      notifications: FakeNotifications | None = None,
                      logs: Logs | None = None,
                      hub: Hub | None = None,
                      clock: Callable[[], datetime] | None = None,
                      sleep: Callable[[float], None] = never_sleeps,
                      dry_run: bool = False, home: Path | None = None,
                      clone_problem: Callable[[Repo, Path], str | None] | None = None,
                      requirements: Callable[[], list[tuple[str, str | None]]] | None = None,
                      releases_api: ScriptedReleasesApi | None = None,
                      github_token: str | None = None,
                      ) -> dishka.Container:
    github = github or watching(settings)
    providers: list[Part] = [
        fake_github(github),
        fake_provider(Desktop, desktop or FakeDesktop()),
        fake_provider(PrProcesses, pr_processes or FakePrProcesses()),
        fake_provider(Hub, hub or FakeHub()),
        fake_agent_runs_roles(fake_agent_runs()),
        fake_provider(WorkingCopies, working_copies or FakeWorkingCopies(github)),
        watcher_wiring(settings, home or settings.data_dir / "home",
                       clone_problem_at=clone_problem or (lambda repo, path: None),
                       requirements=requirements or (lambda: []), run_in=lambda work: work(),
                       releases_api=releases_api or ScriptedReleasesApi(), github_token=github_token),
        notifications_wiring(settings),
        fake_provider(BoardPages, FakeBoardPages()),
    ]
    if event_queue is not None:
        providers.append(event_queue_provider(event_queue))
    if change_detection is not None:
        providers.append(fake_provider(ChangeDetection, change_detection))
    if thread_records is not None:
        providers.append(fake_provider(ThreadRecords, thread_records))
    if notifications is not None:
        providers.append(fake_notifications(notifications))
    if logs is not None:
        providers.append(fake_provider(Logs, logs))
    if dry_run:
        providers.extend(dry_run_parts(settings))
    return build_container(settings, *providers, clocks=clocks_of(clock or at_now, sleep=sleep))


def watcher_over(settings: Settings, **modules: Any) -> Watcher:
    watcher: Watcher = watcher_container(settings, **modules).get(Watcher)
    return watcher


def health(settings: Settings) -> Health:
    watcher_health: WatcherHealth = watcher_container(settings).get(WatcherHealth)
    return watcher_health.health()
