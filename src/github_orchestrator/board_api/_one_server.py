import re
import threading
from collections.abc import Callable, Collection
from pathlib import Path

import anyio
import anyio.to_thread
from starlette.types import ASGIApp, Receive, Scope, Send

from github_orchestrator.board_api import _routes as routes
from github_orchestrator.board_api._app import Board, board_app
from github_orchestrator.board_api._hub import Desk, hub_app
from github_orchestrator.board_api._loopback import loopback_url
from github_orchestrator.board_api._pages import pr_page
from github_orchestrator.board_api._wall import Wall
from github_orchestrator.board_api.interface import (
    Dashboards,
    Emojis,
    HarvestSetup,
    Holdings,
    ManagerPanels,
    MentionsList,
    ReleaseRecord,
    SetupDesk,
    Shelves,
    Told,
    TourMarker,
    WatcherPulse,
)
from github_orchestrator.board_api.interface import RunLedger as Ledger
from github_orchestrator.conversation import ConversationManagerFactory
from github_orchestrator.domain import Pr, Repo, UtcClock
from github_orchestrator.pr_summaries import PrSummaries, SummaryLane
from github_orchestrator.terminal_sessions import Terminals
from github_orchestrator.working_copies import WorkingCopies

TERMINAL_THREADS = 64
ROUTING_THREADS = 8

_BOARD_PATH = re.compile(r"^/pr/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/([0-9]+)/api/")


class _Boards:
    def __init__(self, told: Told, build: Callable[[Pr], ASGIApp]) -> None:
        self._told = told
        self._build = build
        self._built: dict[Pr, ASGIApp] = {}
        self._lock = threading.Lock()
        self.routing = anyio.CapacityLimiter(ROUTING_THREADS)

    def of(self, pr: Pr) -> ASGIApp | None:
        if pr not in self._told.held().managers:
            return None
        with self._lock:
            app = self._built.get(pr)
            if app is None:
                app = self._built[pr] = self._build(pr)
            return app


class _Routed:
    def __init__(self, hub: ASGIApp, boards: _Boards) -> None:
        self._hub = hub
        self._boards = boards

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        found = _BOARD_PATH.match(scope["path"]) if scope["type"] in ("http", "websocket") else None
        if found is not None:
            owner, name, number = found.groups()
            pr = Pr(Repo(owner, name), int(number))
            board = await anyio.to_thread.run_sync(self._boards.of, pr,
                                                   limiter=self._boards.routing)
            if board is not None:
                await board({**scope, "root_path": pr_page(pr)}, receive, send)
                return
        await self._hub(scope, receive, send)


class OneServer:
    def __init__(self, *, app_root: Path, font_dir: str | None, dashboards: Dashboards,
                 ledger: Ledger, pulse: WatcherPulse, clock: UtcClock,
                 watching: Collection[Repo], version: str | None,
                 problem: Callable[[], str | None], setup: SetupDesk, releases: ReleaseRecord,
                 tour: TourMarker, emojis: Emojis, harvest: HarvestSetup, told: Told,
                 holdings: Holdings, mentions: MentionsList,
                 conversation_managers: ConversationManagerFactory,
                 working_copies: WorkingCopies, terminals: Terminals, panels: ManagerPanels,
                 summaries: PrSummaries, lane: SummaryLane, shelves: Shelves,
                 check_presence: bool, first_names_only: bool, heartbeat_seconds: float,
                 check_seconds: float) -> None:
        self._app_root = app_root
        self._fonts = routes.served_fonts(font_dir)
        self._wall = Wall(dashboards, watching, summaries)
        self._ledger = ledger
        self._pulse = pulse
        self._clock = clock
        self._version = version
        self._problem = problem
        self._setup = setup
        self._releases = releases
        self._tour = tour
        self._emojis = emojis
        self._harvest = harvest
        self._told = told
        self._holdings = holdings
        self._mentions = mentions
        self._conversation_managers = conversation_managers
        self._working_copies = working_copies
        self._terminals = terminals
        self._panels = panels
        self._summaries = summaries
        self._lane = lane
        self._shelves = shelves
        self._check_presence = check_presence
        self._first_names_only = first_names_only
        self._heartbeat_seconds = heartbeat_seconds
        self._check_seconds = check_seconds

    def app(self, port: int, pid: int) -> ASGIApp:
        url = loopback_url(port)
        desk = Desk(holdings=self._holdings, told=self._told, wall=self._wall,
                    ledger=self._ledger, pulse=self._pulse, clock=self._clock, url=url,
                    app_root=self._app_root, fonts=self._fonts,
                    version=self._version, problem=self._problem, setup=self._setup,
                    releases=self._releases, tour=self._tour, emojis=self._emojis,
                    harvest=self._harvest, mentions=self._mentions,
                    pid=pid)

        def board(pr: Pr) -> ASGIApp:
            return board_app(Board(
                conversations=self._conversation_managers.of(pr),
                git=self._working_copies.checkout(pr), pr=pr, port=port,
                manager=self._panels.of(pr), app_root=self._app_root, hub_url=url,
                fonts=self._fonts, check_presence=self._check_presence,
                first_names_only=self._first_names_only,
                heartbeat_seconds=self._heartbeat_seconds, check_seconds=self._check_seconds,
                terminals=self._terminals.of(pr),
                terminal_threads=anyio.CapacityLimiter(TERMINAL_THREADS),
                clock=self._clock, summaries=self._summaries, lane=self._lane,
                shelf=self._shelves.of(pr),
                prefix=pr_page(pr)))

        return _Routed(hub_app(desk, port), _Boards(self._told, board))
