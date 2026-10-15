import functools
import http.client
import socket
import threading
from collections.abc import Callable, Collection, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict, Unpack

import anyio
import anyio.to_thread
import httpx2
import uvicorn
from fastapi.testclient import TestClient
from starlette.types import ASGIApp

from github_orchestrator.agent_runs import History
from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.board_api import ManagerPanel
from github_orchestrator.board_api.fake import (
    FakeDashboards,
    FakeHoldings,
    FakeManagerPanel,
    FakeSetupDesk,
    FakeTold,
    FakeTour,
)
from github_orchestrator.board_api.interface import (
    Dashboards,
    Held,
    Holdings,
    ManagerPanels,
    ServerApp,
    SetupDesk,
    Told,
    TourMarker,
)
from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.conversation import Conversation, ConversationManagerFactory
from github_orchestrator.conversation.fake import FakeConversationManagerFactory
from github_orchestrator.domain import Pr, Repo
from github_orchestrator.github import ThreadComment
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings import ConfigFile
from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.terminal_sessions import Terminals, TerminalSessions
from github_orchestrator.terminal_sessions.fake import (
    FakeTerminals,
    FakeTerminalSessions,
)
from github_orchestrator.watcher import Health, Releases, WatcherHealth
from github_orchestrator.wiring import (
    Part,
    PrSummariesWiring,
    ServerAppWiring,
    SummaryLaneWiring,
    wire,
)
from github_orchestrator.working_copies import WorkingCopies
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.conftest import clocks_of, fake_provider
from tests.conversation.support import (
    Stage,
    at,
    fake_conversation_managers,
    hear,
    on_github,
    propose,
    said,
    start_run,
    world,
)
from tests.thread_records.support import disk_thread_records
from tests.waiting import until

REPO_ROOT = Path(__file__).resolve().parents[2]

REPO = "acme/widgets"
PR = 54
THE_PR = a_pr(PR, REPO)
WORKTREE = "/nonexistent/worktree"
PORT = 8888
HUB_PORT = 8720
STREAM_CHECK_SECONDS = 0.05
WORKERS_WAIT_SECONDS = 2
UNBUILT = Path("/nonexistent/board-app")
BOARD_PATH = "/pr/acme/widgets/54"
THE_ROOT = f"http://127.0.0.1:{PORT}"


def page_of(pr: Pr) -> str:
    return f"/pr/{pr.repo}/{pr.number}"
SERVED_APP = REPO_ROOT / "src" / "github_orchestrator" / "board_api" / "static" / "app"

MOMENT = "2026-08-28T10:00:00Z"

KEY = "PRRT_101"
COMMENT_ID = 101
BODY = "Please rename this helper."
ACCOUNT = "vector67"
TITLE = "Rename the helper"


def fake_threads(github: FakeGitHub | None = None,
                 working_copies: FakeWorkingCopies | None = None,
                 agent_runs: FakeAgentRuns | None = None, *,
                 clock: Callable[[], datetime] = at(MOMENT), **config: Any) -> FakeConversationManagerFactory:
    github = github or FakeGitHub()
    return fake_conversation_managers(agent_runs, github=github,
                               working_copies=working_copies or FakeWorkingCopies(github),
                               clock=clock, **config)


class Serving(TypedDict, total=False):
    check_presence: bool
    app_root: Path
    font_dir: str | None
    manager: ManagerPanel | None
    heartbeat_seconds: float
    sessions: TerminalSessions | None
    first_names_only: bool
    clock: Callable[[], datetime]
    port: int
    pr: Pr
    summaries: list[Part]


class NoHeads:
    def facts(self, pr: Pr) -> None:
        return None


def summaries_in(directory: Path) -> list[Part]:
    return [PrSummariesWiring(directory),
            SummaryLaneWiring(Path("/nonexistent/config.toml"), {}, False, "octocat"),
            fake_provider(ChangeDetection, NoHeads())]


def no_summaries() -> list[Part]:
    return summaries_in(Path("/nonexistent/summaries"))


@dataclass
class OneTerminal:
    sessions: TerminalSessions

    def of(self, pr: Pr) -> TerminalSessions:
        return self.sessions

    def everywhere(self) -> list[TerminalSessions]:
        return [self.sessions]


@dataclass
class OnePanel:
    panel: ManagerPanel

    def of(self, pr: Pr) -> ManagerPanel:
        return self.panel


def board_app(conversation_managers: ConversationManagerFactory, working_copies: WorkingCopies,
              **serving: Unpack[Serving]) -> ASGIApp:
    server: ServerApp = wire(
        fake_provider(Told, holding(serving.get("pr", THE_PR))),
        *_hub_parts(),
        fake_provider(ConversationManagerFactory, conversation_managers),
        fake_provider(WorkingCopies, working_copies),
        fake_provider(Terminals, OneTerminal(serving.get("sessions") or FakeTerminalSessions())),
        fake_provider(ManagerPanels, OnePanel(serving.get("manager") or FakeManagerPanel())),
        *serving.get("summaries", no_summaries()),
        clocks_of(serving.get("clock", at(MOMENT))),
        ServerAppWiring(app_root=serving.get("app_root", UNBUILT), font_dir=serving.get("font_dir"),
                        watching=(Repo("acme", "widgets"),), version="0.1.0",
                        check_presence=serving.get("check_presence", False),
                        first_names_only=serving.get("first_names_only", False),
                        heartbeat_seconds=serving.get("heartbeat_seconds", 15.0),
                        check_seconds=STREAM_CHECK_SECONDS)).get(ServerApp)
    return server.app(serving.get("port", PORT), SERVER_PID)


@contextmanager
def on_loopback(app_at: Callable[[int], ASGIApp]) -> Iterator[int]:
    listening = socket.socket()
    listening.bind(("127.0.0.1", 0))
    listening.listen()
    port = int(listening.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(app_at(port), log_config=None, access_log=False,
                                           lifespan="off", timeout_graceful_shutdown=1))
    serving = threading.Thread(target=server.run, kwargs={"sockets": [listening]}, daemon=True)
    serving.start()
    try:
        assert until(lambda: server.started)
        yield port
    finally:
        server.should_exit = True
        serving.join(timeout=5)
        listening.close()


def served_board(conversation_managers: ConversationManagerFactory, working_copies: WorkingCopies,
                 **serving: Unpack[Serving]) -> TestClient:
    return TestClient(board_app(conversation_managers, working_copies, **serving),
                      base_url=f"http://127.0.0.1:{serving.get('port', PORT)}"
                               f"{page_of(serving.get('pr', THE_PR))}")


@dataclass
class Pulse:
    now: Health

    def health(self) -> Health:
        return self.now


POLLED = Health(alive=True, since_last_poll=timedelta(seconds=20), last_error=None, fix=None,
                polls_every=timedelta(minutes=1))


@dataclass
class Words:
    problem: str | None

    def check(self) -> str | None:
        return self.problem


def _hub_parts(*, dashboards: Dashboards | None = None, ledger: History | None = None,
               pulse: WatcherHealth | None = None, config_file: Words = Words(None),
               setup: SetupDesk | None = None, releases: Any = None,
               tour: TourMarker | None = None,
               holdings: Holdings | None = None) -> list[Part]:
    return [
        fake_provider(Holdings, holdings or FakeHoldings()),
        fake_provider(Releases, releases or NoReleaseYet()),
        fake_provider(Dashboards, dashboards or FakeDashboards()),
        fake_provider(SetupDesk, setup or FakeSetupDesk()),
        fake_provider(TourMarker, tour or FakeTour()),
        fake_provider(History, ledger or FakeAgentRuns(FakePrProcesses())),
        fake_provider(WatcherHealth, pulse or Pulse(POLLED)),
        fake_provider(ConfigFile, config_file),
    ]


def served_hub(app_root: Path = UNBUILT, *, clock: Callable[[], datetime] = at(MOMENT),
               watching: Collection[Repo] = (Repo("acme", "widgets"),),
               told: Told | None = None, summaries: list[Part] | None = None,
               **wall: Any) -> TestClient:
    fake = fake_threads()
    server: ServerApp = wire(
        fake_provider(Told, told or FakeTold()),
        *_hub_parts(**wall),
        fake_provider(ConversationManagerFactory, fake),
        fake_provider(WorkingCopies, fake.working_copies),
        fake_provider(Terminals, FakeTerminals()),
        fake_provider(ManagerPanels, OnePanel(FakeManagerPanel())),
        *(summaries or no_summaries()),
        clocks_of(clock),
        ServerAppWiring(app_root=app_root, font_dir=None, watching=watching, version="0.1.0",
                        check_presence=False, first_names_only=False,
                        check_seconds=STREAM_CHECK_SECONDS)).get(ServerApp)
    return TestClient(server.app(HUB_PORT, SERVER_PID), base_url=f"http://127.0.0.1:{HUB_PORT}")


class NoReleaseYet:
    def recorded(self) -> None:
        return None


def holding(*prs: Pr, managers: dict[Pr, str] | None = None) -> FakeTold:
    return FakeTold(Held(told=True, managers={pr: (managers or {}).get(pr, "running")
                                              for pr in prs}))


@dataclass
class Served:
    threads: Any
    client: TestClient
    stage: Stage
    manager: ManagerPanel


def _placed(working_copies: FakeWorkingCopies) -> None:
    if THE_PR not in working_copies.placed:
        working_copies.add_repo(Path(WORKTREE), {"f": "one\n"}, "first")
        working_copies.place(THE_PR, WORKTREE)


def _served(conversation_managers: ConversationManagerFactory, stage: Stage, threads: Any,
            **serving: Unpack[Serving]) -> Served:
    manager = serving["manager"] = serving.get("manager") or FakeManagerPanel()
    client = served_board(conversation_managers, stage.working_copies, **serving)
    return Served(threads=threads, client=client, stage=stage, manager=manager)


def board_on(fake: FakeConversationManagerFactory, *, is_author: bool = True, title: str | None = TITLE,
             base_branch: str | None = "main", head_sha: str | None = None,
             branch: str | None = None, created_at: str | None = None,
             commits: int | None = None, additions: int | None = None,
             deletions: int | None = None,
             **serving: Unpack[Serving]) -> Served:
    _placed(fake.working_copies)
    fake.watch(THE_PR, is_author=is_author, title=title, base_branch=base_branch,
               head_sha=head_sha, branch=branch, created_at=created_at, commits=commits,
               additions=additions, deletions=deletions)
    threads = fake.of(THE_PR)
    hear(threads)
    return _served(fake, fake, threads, **serving)


def disk_board(threads_dir: Path, *, is_author: bool = True, **fakes: Any) -> Served:
    settings = fake_settings(threads_dir / "data", agents_enabled=True)
    here = world(settings, thread_records=disk_thread_records(threads_dir), **fakes)
    _placed(here.working_copies)
    here.polled(repo=REPO, pr=PR, title=TITLE, base_branch="main", is_author=is_author)
    threads = here.threads(repo=REPO, pr=PR, worktree=WORKTREE)
    return _served(here.conversation_managers, here, threads)


def heard_on(board: Served, key: str = KEY, *comments: ThreadComment, **fields: Any) -> Conversation:
    on_github(board.stage.github, key, *(comments or (said(COMMENT_ID, BODY),)), pr=THE_PR,
              **fields)
    hear(board.threads)
    found: Conversation = board.threads.get(key)
    return found


def running(board: Served) -> None:
    start_run(board.stage, board.threads, finishes=False)


def proposed(board: Served, key: str = KEY, files: dict[str, str] | None = None,
             **ready: Any) -> Conversation:
    return propose(board.stage, board.threads, key, files, pr=THE_PR, **ready)


def board_for(pr_title: str | None = TITLE, base_branch: str | None = "main",
              is_author: bool = True, head_sha: str | None = "8f73fe8",
              working_copies: FakeWorkingCopies | None = None,
              github: FakeGitHub | None = None, created_at: str | None = None,
              commits: int | None = None, additions: int | None = None,
              deletions: int | None = None,
              **serving: Unpack[Serving]) -> Served:
    return board_on(fake_threads(github, working_copies), is_author=is_author, title=pr_title,
                    base_branch=base_branch, head_sha=head_sha, branch="rename-the-helper",
                    created_at=created_at, commits=commits, additions=additions,
                    deletions=deletions, **serving)


def followed(web: TestClient, answer: httpx2.Response) -> httpx2.Response:
    return web.get(f"{web.base_url.scheme}://{web.base_url.netloc.decode()}"
                   f"{answer.headers['Location']}")


def client_of(board: Served) -> TestClient:
    return board.client


def client_for(**fields: Any) -> TestClient:
    return client_of(board_for(**fields))


async def _take_every_worker() -> tuple[anyio.CapacityLimiter, list[object]]:
    limiter = anyio.to_thread.current_default_thread_limiter()
    holders = [object() for _ in range(int(limiter.total_tokens))]
    for holder in holders:
        await limiter.acquire_on_behalf_of(holder)
    return limiter, holders


def _give_back(limiter: anyio.CapacityLimiter, holders: list[object]) -> None:
    for holder in holders:
        limiter.release_on_behalf_of(holder)


def asked_with_every_worker_taken(web: TestClient, path: str) -> httpx2.Response:
    with web, ThreadPoolExecutor(1) as asking:
        assert web.portal is not None
        limiter, holders = web.portal.call(_take_every_worker)
        answer = asking.submit(web.get, path)
        try:
            return answer.result(timeout=WORKERS_WAIT_SECONDS)
        finally:
            web.portal.call(_give_back, limiter, holders)


def rewritten(path: Path, wanted: str) -> str:
    held = path.read_text() if path.exists() else ""
    if held != wanted:
        path.write_text(wanted)
    return held


@functools.cache
def board_contract() -> Any:
    return client_for().get("/api/openapi.json").json()


@functools.cache
def hub_contract() -> Any:
    return served_hub().get("/api/openapi.json").json()


def _block_after(css: str, selector: str) -> str:
    start = css.index("{", css.index(selector)) + 1
    return css[start:css.index("}", start)]


def css_variables(css: str) -> dict[str, dict[str, str]]:
    return {theme: {name.strip(): value.strip()
                    for name, _, value in (pair.partition(":")
                                           for pair in _block_after(css, selector).split(";"))
                    if name.strip().startswith("--")}
            for theme, selector in (("light", ":root {"), ("dark", ":root:not"))}


class Events:
    def __init__(self, port: int, path: str, headers: dict[str, str] | None = None) -> None:
        self.connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        self.connection.request("GET", path, headers=headers or {})
        self.answer = self.connection.getresponse()

    def block(self) -> dict[str, str]:
        fields: dict[str, str] = {}
        while (line := self.answer.readline().decode()) != "\n":
            if not line:
                raise EOFError(f"the stream ended after {fields}")
            name, _, value = line.rstrip("\n").partition(":")
            fields[name] = value.removeprefix(" ")
        return fields

    def event(self) -> dict[str, str]:
        while "data" not in (fields := self.block()):
            pass
        return fields

    def close(self) -> None:
        self.connection.close()


@dataclass
class CountedPanels:
    panel: FakeManagerPanel
    asked: list[Pr]

    def of(self, pr: Pr) -> ManagerPanel:
        self.asked.append(pr)
        return self.panel


SERVER_PID = 4242


@dataclass
class OneServer:
    client: TestClient
    panels: CountedPanels
    told: FakeTold
    holdings: FakeHoldings
    terminals: FakeTerminals


def one_server(*held: Pr, app_root: Path = UNBUILT, port: int = HUB_PORT,
               host: str | None = None) -> OneServer:
    fake = fake_threads()
    _placed(fake.working_copies)
    fake.watch(THE_PR, is_author=True, title=TITLE, base_branch="main", head_sha="8f73fe8",
               branch="rename-the-helper")
    hear(fake.of(THE_PR))
    panels = CountedPanels(FakeManagerPanel(), [])
    told = holding(*held)
    holdings = FakeHoldings()
    terminals = FakeTerminals()
    server: ServerApp = wire(
        fake_provider(Told, told),
        *_hub_parts(holdings=holdings),
        fake_provider(ConversationManagerFactory, fake),
        fake_provider(WorkingCopies, fake.working_copies),
        fake_provider(Terminals, terminals),
        fake_provider(ManagerPanels, panels),
        *no_summaries(),
        clocks_of(at(MOMENT)),
        ServerAppWiring(app_root=app_root, font_dir=None, watching=(Repo("acme", "widgets"),),
                        version="0.1.0", check_presence=False, first_names_only=False,
                        check_seconds=STREAM_CHECK_SECONDS)).get(ServerApp)
    client = TestClient(server.app(port, SERVER_PID),
                        base_url=f"http://{host or f'127.0.0.1:{port}'}")
    return OneServer(client=client, panels=panels, told=told, holdings=holdings,
                     terminals=terminals)
