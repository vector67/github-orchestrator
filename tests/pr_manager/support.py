import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import dishka

from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.board_api import BoardApi
from github_orchestrator.board_api.fake import FakeBoardApi
from github_orchestrator.change_detection import ChangeDetection, Poll
from github_orchestrator.conversation import ConversationManagerFactory
from github_orchestrator.desktop import Desktop
from github_orchestrator.desktop.fake import FakeDesktop
from github_orchestrator.domain import Pr
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.pr_event_queue import Intake
from github_orchestrator.pr_manager import ManagedPr, PrManager
from github_orchestrator.pr_processes import AgentChanges, PrProcesses
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings import Logs
from github_orchestrator.settings.fake import Settings
from github_orchestrator.wiring import (
    BrowserFrontProvider,
    Part,
    PrManagerWiring,
    change_detection_wiring,
    dashboard_source_wiring,
    manager_config,
    wire,
)
from github_orchestrator.working_copies import WorkingCopies
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.change_detection.support import seen
from tests.conftest import (
    build_container,
    clocks_of,
    fake_agent_runs_roles,
    fake_github,
    fake_notifications,
    fake_provider,
)
from tests.pr_event_queue.support import PrEventQueue, event_queue_provider
from tests.pr_manager.scripted_terminal import ManualClock, ScriptedSleep, ScriptEnded

REPO = "o/n"
PR = 1
THE_PR = a_pr(PR, REPO)
BOARD_URL = "http://127.0.0.1:4321"
POLLED_AT = "2026-06-10T11:00:00Z"


def run_subprocess(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(*args, **kwargs)


def change_detection_of(settings: Settings,
                        now: Callable[[], datetime] | None = None) -> ChangeDetection:
    change_detection: ChangeDetection = wire(
        change_detection_wiring(settings), clocks_of(now)).get(ChangeDetection)
    return change_detection


def polled(settings: Settings, *polls: Poll, pr: Pr = THE_PR,
           now: Callable[[], datetime] | None = None) -> None:
    change_detection = change_detection_of(settings, now)
    for poll in polls:
        change_detection.advance(pr, poll, set())


def seed_state(settings: Settings, repo: str = REPO, pr: int = PR, *,
               is_author: bool = True, **state: Any) -> None:
    polled(settings, seen(settings.config.gh_account, is_author=is_author,
                          polled_at=POLLED_AT, **state), pr=a_pr(pr, repo))


def _say_whose(settings: Settings, pr: Pr, is_author: bool) -> None:
    change_detection = change_detection_of(settings)
    facts = change_detection.facts(pr)
    if facts is None:
        change_detection.advance(pr, seen(settings.config.gh_account, is_author=is_author,
                                          polled_at=POLLED_AT), set())
        return
    assert facts.is_author is is_author, "seed the role with seed_state(is_author=...)"


@dataclass
class Manager:
    manager: PrManager
    clock: ManualClock
    board: BoardApi
    desktop: Desktop
    notifications: FakeNotifications
    github: FakeGitHub
    event_queue: PrEventQueue
    working_copies: WorkingCopies
    pr_processes: FakePrProcesses
    agent_runs: FakeAgentRuns
    conversation_managers: ConversationManagerFactory
    container: dishka.Container

    def run(self) -> "Manager":
        try:
            self.manager.run()
        except ScriptEnded:
            pass
        return self


def manager_over(settings: Settings, *script: Any, worktree: str | Path = "/wt",
                 repo: str = REPO, pr: int = PR, is_author: bool | None = None,
                 clock: ManualClock | None = None,
                 board: BoardApi | None = None,
                 github: FakeGitHub | None = None,
                 desktop: Desktop | None = None,
                 notifications: FakeNotifications | None = None,
                 event_queue: PrEventQueue | None = None,
                 pr_processes: FakePrProcesses | None = None,
                 agent_runs: FakeAgentRuns | None = None,
                 working_copies: WorkingCopies | None = None,
                 conversation_managers: ConversationManagerFactory | None = None,
                 logs: Logs | None = None,
                 run: Any = run_subprocess) -> Manager:
    clock = clock or ManualClock()
    board = board or FakeBoardApi(url=BOARD_URL)
    github = github or FakeGitHub()
    desktop = desktop or FakeDesktop()
    notifications = notifications or FakeNotifications()
    pr_processes = pr_processes or FakePrProcesses()
    agent_runs = agent_runs or FakeAgentRuns(pr_processes)
    working_copies = working_copies or FakeWorkingCopies(github)
    managed = ManagedPr(pr=a_pr(pr, repo), worktree=str(worktree))
    if is_author is not None:
        _say_whose(settings, managed.pr, is_author)
    config = manager_config(settings, managed)
    place = getattr(working_copies, "place", None)
    if place is not None:
        place(managed.pr, worktree)
    providers: list[Part] = [
        fake_github(github),
        fake_provider(Desktop, desktop),
        fake_notifications(notifications),
        fake_provider(PrProcesses, pr_processes),
        fake_provider(AgentChanges, pr_processes),
        fake_agent_runs_roles(agent_runs),
        fake_provider(WorkingCopies, working_copies),
        fake_provider(BoardApi, board),
        PrManagerWiring(config, run),
        dashboard_source_wiring(settings),
        BrowserFrontProvider,
    ]
    if event_queue is not None:
        providers.append(event_queue_provider(event_queue))
    if conversation_managers is not None:
        providers.append(fake_provider(ConversationManagerFactory, conversation_managers))
    if logs is not None:
        providers.append(fake_provider(Logs, logs))
    sleep = ScriptedSleep(*script, clock=clock)
    container = build_container(settings, *providers,
                                clocks=clocks_of(clock.now, monotonic=clock.monotonic,
                                                 sleep=sleep))
    return Manager(
        manager=container.get(PrManager), clock=clock, board=board,
        desktop=desktop, notifications=notifications, github=github, event_queue=container.get(Intake), working_copies=working_copies,
        pr_processes=pr_processes, agent_runs=agent_runs,
        conversation_managers=container.get(ConversationManagerFactory),
        container=container,
    )


def run_manager(settings: Settings, *script: Any, **modules: Any) -> Manager:
    return manager_over(settings, *script, **modules).run()
