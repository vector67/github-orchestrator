import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import dishka

from github_orchestrator.agent_runs.fake import FakeAgentRuns, Outcome
from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.change_detection.fake import FakeChangeDetection
from github_orchestrator.conversation import (
    Conversation,
    ConversationManagerFactory,
)
from github_orchestrator.conversation.fake import FakeConversationManagerFactory
from github_orchestrator.desktop import Desktop
from github_orchestrator.desktop.fake import FakeDesktop
from github_orchestrator.domain import Pr
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    Thread,
    ThreadComment,
)
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications import Standing
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.pr_processes import PrProcesses
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import Settings, fake_settings
from github_orchestrator.thread_records import ThreadRecords
from github_orchestrator.thread_records.fake import FakeThreadRecords
from github_orchestrator.wiring import (
    ClocksWiring,
    Part,
    conversation_config,
    utcnow,
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
    fake_provider,
)

REPO = "acme/widgets"
PR = 7
THE_PR = a_pr(PR, REPO)
WORKTREE = "/tmp/prwork"


def at(iso: str) -> Callable[[], datetime]:
    moment = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return lambda: moment


@dataclass
class World:
    settings: Settings
    github: FakeGitHub
    working_copies: FakeWorkingCopies
    agent_runs: FakeAgentRuns
    thread_records: ThreadRecords
    pr_processes: FakePrProcesses
    conversation_managers: ConversationManagerFactory
    change_detection: ChangeDetection
    standing: Standing
    clock: Callable[[], datetime] | None = None
    monotonic: Callable[[], float] | None = None

    def threads(self, *, is_author: bool | None = None, worktree: str = WORKTREE,
                repo: str = REPO, pr: int = PR, pr_run_live: bool = False,
                agents_enabled: bool | None = None) -> Any:
        if agents_enabled is not None and agents_enabled != self.settings.config.agents_enabled:
            return self.claude(agents_enabled).threads(is_author=is_author, worktree=worktree,
                                                      repo=repo, pr=pr,
                                                      pr_run_live=pr_run_live)
        the_pr = a_pr(pr, repo)
        facts = self.change_detection.facts(the_pr)
        if facts is None or facts.is_author is None or (
                is_author is not None and facts.is_author is not is_author):
            self.polled(repo=repo, pr=pr, is_author=is_author is not False)
        place = getattr(self.working_copies, "place", None)
        if place is not None:
            place(the_pr, worktree)
        if pr_run_live:
            self.agent_runs.script(Outcome(finishes=False))
            self.agent_runs.carry_on(worktree, the_pr)
        return self.conversation_managers.of(the_pr)

    def claude(self, enabled: bool) -> "World":
        config = replace(self.settings.config, agents_enabled=enabled)
        return world(replace(self.settings, config=config), github=self.github,
                     working_copies=self.working_copies, agent_runs=self.agent_runs,
                     thread_records=self.thread_records,
                     change_detection=self.change_detection, clock=self.clock,
                     monotonic=self.monotonic, pr_processes=self.pr_processes)

    def load(self, key: str, *, repo: str = REPO, pr: int = PR) -> Conversation | None:
        found: Conversation | None = self.threads(repo=repo, pr=pr).get(key)
        return found

    def polled(self, *, repo: str = REPO, pr: int = PR, is_author: bool = True,
               **state: Any) -> None:
        self.change_detection.advance(
            a_pr(pr, repo), seen(self.settings.config.gh_account, is_author=is_author, **state),
            set())


def without_runs(settings: Settings) -> Settings:
    return replace(settings, config=replace(settings.config, max_thread_runs=0))


RECHECK_SECONDS = 5


def lost(threads: Any, key: str) -> None:
    threads.recheck(threads.get(key))
    deadline = time.monotonic() + RECHECK_SECONDS
    while (any(thread.name == "presence" for thread in threading.enumerate())
           and time.monotonic() < deadline):
        time.sleep(0.005)


def _container(settings: Settings, github: FakeGitHub, agent_runs: FakeAgentRuns | None,
               desktop: FakeDesktop, pr_processes: FakePrProcesses,
               working_copies: WorkingCopies | None,
               thread_records: ThreadRecords | None,
               clocks: ClocksWiring,
               change_detection: ChangeDetection | None = None) -> dishka.Container:
    providers: list[Part] = [
        fake_github(github),
        fake_provider(Desktop, desktop),
        fake_provider(PrProcesses, pr_processes),
        fake_agent_runs_roles(agent_runs or FakeAgentRuns(pr_processes)),
    ]
    if working_copies is not None:
        providers.append(fake_provider(WorkingCopies, working_copies))
    if thread_records is not None:
        providers.append(fake_provider(ThreadRecords, thread_records))
    if change_detection is not None:
        providers.append(fake_provider(ChangeDetection, change_detection))
    return build_container(settings, *providers, clocks=clocks)


def _clocks(clock: Callable[[], datetime] | None,
            monotonic: Callable[[], float] | None) -> ClocksWiring:
    return clocks_of(clock, monotonic=monotonic or time.monotonic)


def world(settings: Settings, *, github: FakeGitHub | None = None,
          working_copies: FakeWorkingCopies | None = None,
          agent_runs: FakeAgentRuns | None = None,
          thread_records: ThreadRecords | None = None,
          change_detection: ChangeDetection | None = None,
          clock: Callable[[], datetime] | None = None,
          monotonic: Callable[[], float] | None = None,
          pr_processes: FakePrProcesses | None = None) -> World:
    github = github or FakeGitHub()
    working_copies = working_copies or FakeWorkingCopies(github)
    pr_processes = pr_processes or FakePrProcesses()
    desktop = FakeDesktop()
    agent_runs = agent_runs or FakeAgentRuns(pr_processes)
    thread_records = thread_records or FakeThreadRecords()
    clocks = _clocks(clock, monotonic)
    change_detection = change_detection or FakeChangeDetection(
        settings.config.gh_account, settings.config.watcher_poll_interval, clocks.utc)
    container = _container(settings, github, agent_runs, desktop, pr_processes,
                           working_copies, thread_records, clocks, change_detection)
    return World(settings, github, working_copies, agent_runs, thread_records,
                 pr_processes, container.get(ConversationManagerFactory), container.get(ChangeDetection),
                 container.get(Standing), clock, monotonic)


def conversation_managers_over(settings: Settings, *, github: FakeGitHub | None = None,
                        working_copies: WorkingCopies | None = None,
                        agent_runs: FakeAgentRuns | None = None,
                        thread_records: ThreadRecords | None = None,
                        clock: Callable[[], datetime] | None = None,
                        monotonic: Callable[[], float] | None = None) -> ConversationManagerFactory:
    conversation_managers: ConversationManagerFactory = _container(
        settings, github or FakeGitHub(), agent_runs, FakeDesktop(), FakePrProcesses(),
        working_copies, thread_records, _clocks(clock, monotonic)).get(ConversationManagerFactory)
    return conversation_managers


def diff_over(here: "World", path: str, lines: int = 60, *, is_author: bool = False) -> str:
    before = "".join(f"line {number}\n" for number in range(1, lines + 1))
    after = "".join(f"changed {number}\n" for number in range(1, lines + 1))
    repo_at(here.working_copies, WORKTREE, {path: before})
    head = here.working_copies.commit(WORKTREE, {path: after}, "change every line")
    here.polled(head_sha=head, base_branch="main", is_author=is_author)
    return head


def repo_at(working_copies: FakeWorkingCopies, worktree: str | Path,
            files: dict[str, str] | None = None, pr: Pr = THE_PR) -> str:
    sha = working_copies.add_repo(Path(worktree), files or {"README": "hello"}, "first")
    working_copies.place(pr, worktree)
    return sha


class Moment:
    def __init__(self, iso: str) -> None:
        self.iso = iso

    def __call__(self) -> datetime:
        return at(self.iso)()


EARLIER = "2026-08-28T00:00:00Z"


class Stage(Protocol):
    github: FakeGitHub
    working_copies: FakeWorkingCopies
    agent_runs: FakeAgentRuns


def said(comment_id: int, body: str, *, author: str = "reviewer",
         created_at: str | None = EARLIER, author_name: str = "") -> ThreadComment:
    return ThreadComment(id=comment_id, author=author, body=body, created_at=created_at,
                         author_name=author_name)


def on_github(github: FakeGitHub, key: str, *comments: ThreadComment, pr: Pr = THE_PR,
              kind: CommentKind = CommentKind.REVIEW, path: str | None = "f",
              line: int | None = 1, **fields: Any) -> None:
    if pr not in github.prs:
        github.add_pr(pr)
    github.add_thread(pr, Thread(key=key, kind=kind, path=path, line=line,
                                 comments=comments, **fields))


def hear(threads: Any) -> Any:
    polled = threads.poll(PullRequestState())
    polled.commit()
    if polled.activity is None:
        return None
    return threads.absorb(polled.activity)


def first_poll(github: FakeGitHub, threads: Any, pr: Pr = THE_PR) -> None:
    if pr not in github.prs:
        github.add_pr(pr)
    hear(threads)


def drain(threads: Any) -> None:
    threads.tick(FakeNotifications(), on_hold=False)


def commit_fix(stage: Stage, key: str, files: dict[str, str] | None = None, *,
               pr: Pr = THE_PR, message: str = "Rename the helper") -> str:
    workspace = stage.working_copies.thread_checkout(pr, key)
    return stage.working_copies.commit(workspace, files or {"f": "new\n"}, message)


def start_run(stage: Stage, threads: Any, *, finishes: bool = True) -> None:
    stage.agent_runs.script(Outcome(finishes=finishes))
    drain(threads)


def propose(stage: Stage, threads: Any, key: str, files: dict[str, str] | None = None,
            *, pr: Pr = THE_PR, **ready: Any) -> Conversation:
    start_run(stage, threads)
    sha = commit_fix(stage, key, files, pr=pr)
    with threads.editing(key) as editable:
        proposed = editable.ready(sha, **ready)
    assert isinstance(proposed, Conversation), proposed
    drain(threads)
    return proposed


NO_DATA = Path("/nonexistent/review-threads-fake")


def fake_conversation_managers(agent_runs: FakeAgentRuns | None = None, *,
                        github: FakeGitHub | None = None,
                        working_copies: FakeWorkingCopies | None = None,
                        data_dir: Path = NO_DATA,
                        clock: Callable[[], datetime] | None = None,
                        monotonic: Callable[[], float] = time.monotonic,
                        **config: Any) -> FakeConversationManagerFactory:
    if github is not None:
        config.setdefault("gh_account", github.account)
    settings = fake_settings(data_dir, **config)
    return FakeConversationManagerFactory(agent_runs or FakeAgentRuns(FakePrProcesses()),
                             conversation_config(settings), github=github,
                             working_copies=working_copies, clock=clock or utcnow,
                             monotonic=monotonic)
