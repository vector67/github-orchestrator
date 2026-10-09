import dataclasses
import logging
import os
import threading
from collections.abc import Callable, Collection, Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Depends, FastAPI, Request, Response, WebSocket
from fastapi import Path as PathParameter
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from github_orchestrator.board_api import _etag as etag
from github_orchestrator.board_api import _routes as routes
from github_orchestrator.board_api import _setup as setup
from github_orchestrator.board_api._app import (
    HANDED_TO_THE_MANAGER,
    PREFIX,
    report_client_error,
)
from github_orchestrator.board_api._contract import (
    ErrorCode,
    Errors,
    Health,
    HeldPullRequests,
    NewestRelease,
    RunLedger,
    Tour,
)
from github_orchestrator.board_api._errors import (
    NOT_FOUND,
    Refusal,
    RefusingApp,
    add_refusal_handlers,
)
from github_orchestrator.board_api._guarded import guard, page_at, target
from github_orchestrator.board_api._loopback import Listen, Listening, loopback_url
from github_orchestrator.board_api._pages import pr_page
from github_orchestrator.board_api._proxy import forwarded
from github_orchestrator.board_api._runs import ledger_read, watcher_read
from github_orchestrator.board_api._terminal import GONE, relayed
from github_orchestrator.board_api._wall import Wall
from github_orchestrator.board_api.interface import (
    Dashboards,
    Holdings,
    ReleaseRecord,
    SetupDesk,
    TourMarker,
    WatcherPulse,
)
from github_orchestrator.board_api.interface import RunLedger as Ledger
from github_orchestrator.domain import HubState, Pr, Repo, UtcClock

log = logging.getLogger(__name__)

FAILED = "the hub failed unexpectedly; the traceback is in the watcher's log"

DESCRIPTION = """
Every pull request the watcher holds, with hold, resume and release, on
loopback with no authentication. The watcher serves it while it runs resident.
"""

NOT_FROZEN = {"description": "The pull request's manager is not frozen on the "
                             "wrong branch, so there is nothing to release.",
              "model": Errors}

HANDED_TO_THE_WATCHER: dict[int | str, dict[str, Any]] = {
    202: {"description": "Taken. The switch is on disk, and the PR manager and "
                         "the watcher act on it on their next tick. Poll the "
                         "list to see it land.",
          "headers": HANDED_TO_THE_MANAGER[202]["headers"]},
    404: NOT_FOUND}


@dataclasses.dataclass(frozen=True)
class Desk:
    holdings: Holdings
    held: Callable[[], tuple[Pr, ...]]
    told: Callable[[], bool]
    wall: Wall
    ledger: Ledger
    pulse: WatcherPulse
    clock: Callable[[], datetime]
    url: str
    app_root: Path
    fonts: routes.Fonts
    streams: anyio.CapacityLimiter
    state: HubState
    version: str | None
    problem: Callable[[], str | None]
    setup: SetupDesk
    releases: ReleaseRecord
    tour: TourMarker


async def desk_of(request: Request) -> Desk:
    desk: Desk = request.app.state.desk
    return desk


Serving = Annotated[Desk, Depends(desk_of)]

Owner = Annotated[str, PathParameter(pattern=r"^[A-Za-z0-9_.-]+$")]
Name = Annotated[str, PathParameter(pattern=r"^[A-Za-z0-9_.-]+$")]

reads = APIRouter(prefix=PREFIX)
writes = APIRouter(prefix=PREFIX, tags=["hub"])


WATCHER_STARTING = {
    "description": "No list yet. `watcher-starting`: the watcher has not finished its "
                   "first cycle, so the hub does not know yet which pull requests it "
                   "holds. `watcher-failing`: no cycle has succeeded and the last one "
                   "failed, with its error as the detail. `not-watching`: the hub is in "
                   "setup or broken state and polls nothing, with what is wrong with "
                   "the config as the detail. Ask again after `Retry-After` seconds.",
    "headers": {"Retry-After": {"schema": {"type": "integer"}}},
    "model": Errors}


@reads.get("/pull-requests", response_model=HeldPullRequests, tags=["hub"],
           operation_id="listHeldPullRequests",
           summary="Every pull request the watcher held after its last cycle.",
           responses={**etag.TAGGED, 503: WATCHER_STARTING})
def list_pull_requests(request: Request, desk: Serving) -> Response:
    """The wall: each pull request's dashboard, built from what the watcher,
    the switches and the PR managers left on disk, with each manager's status
    file laid over it, as its board builds it. Grouped by who holds the ball, and within a group in the order
    they joined it, so a row that changes group goes to the bottom of its
    new one and says where it came from.
    """
    if not desk.told():
        raise _unheld(desk)
    return etag.answered(request, desk.wall.read(desk.held(), desk.holdings))


def _unheld(desk: Desk) -> Refusal:
    again = {"Retry-After": "1"}
    if desk.state is not HubState.WATCHING:
        return Refusal(503, ErrorCode.NOT_WATCHING,
                       desk.problem() or f"the hub is in {desk.state} state", headers=again)
    failed = desk.pulse.health().last_error
    if failed is not None:
        return Refusal(503, ErrorCode.WATCHER_FAILING, failed, headers=again)
    return Refusal(503, ErrorCode.WATCHER_STARTING,
                   "the watcher has not finished its first cycle yet", headers=again)


@reads.get("/runs", response_model=RunLedger, tags=["hub"], operation_id="readRunLedger",
           summary="The agent runs of the last seven days and the watcher's health.",
           responses=etag.TAGGED)
def read_runs(request: Request, desk: Serving) -> Response:
    """The Runs page and the wall's top bar: every run the ledger says ended
    in the last seven days, newest first, how many ended today and what they
    cost, and when the watcher last polled and polls next.
    """
    return etag.answered(request, ledger_read(desk.ledger, desk.pulse, desk.held(),
                                              desk.clock()))


@reads.get("/health", tags=["hub"], operation_id="readHubHealth",
           summary="Whether the hub is serving, and from which process.")
async def read_health(desk: Serving) -> Health:
    return Health(status="ok", pid=os.getpid(), serves="hub", hub_url=desk.url,
                  font_problem=desk.fonts.problem, state=desk.state, version=desk.version,
                  watcher=watcher_read(desk.pulse.health(), desk.clock()),
                  newest_release=_newest(desk))


def _newest(desk: Desk) -> NewestRelease | None:
    seen = desk.releases.recorded()
    if seen is None or seen.checked_at is None:
        return None
    return NewestRelease(version=seen.version, checked_at=seen.checked_at.isoformat(),
                         newer=seen.newer_than(desk.version))


@reads.get("/tour", response_model=Tour, tags=["hub"], operation_id="readTour",
           summary="Whether the board's first-run tour is still to be shown.")
def read_tour(desk: Serving) -> Tour:
    return Tour(due=desk.tour.due())


@writes.post("/tour:seen", status_code=204, operation_id="sawTour",
             summary="Say the tour was seen, so it is not shown again.")
def saw_tour(desk: Serving) -> None:
    desk.tour.seen()


@reads.get("/openapi.json", include_in_schema=False)
def read_contract(request: Request) -> Response:
    document: dict[str, Any] = request.app.openapi()
    return JSONResponse(document)


def _held(desk: Desk, owner: str, name: str, number: int) -> Pr:
    pr = Pr(Repo(owner, name), number)
    if pr not in desk.held():
        raise Refusal(404, ErrorCode.NOT_FOUND,
                      f"the watcher holds no pull request {pr}")
    return pr


def _taken() -> Response:
    return Response(status_code=202, headers={"Location": f"{PREFIX}/pull-requests"})


@writes.post("/pull-requests/{owner}/{name}/{number}:hold", status_code=202,
             operation_id="holdPullRequest", responses=HANDED_TO_THE_WATCHER,
             summary="Put a pull request on hold: its manager takes no events but a closing one.")
def hold(owner: Owner, name: Name, number: int, desk: Serving) -> Response:
    """The dashboard's `p`, for a pull request whose board may not be up. A
    one on hold stays on hold.
    """
    desk.holdings.hold(_held(desk, owner, name, number))
    return _taken()


@writes.post("/pull-requests/{owner}/{name}/{number}:resume", status_code=202,
             operation_id="resumePullRequest", responses=HANDED_TO_THE_WATCHER,
             summary="Resume a pull request on hold.")
def resume(owner: Owner, name: Name, number: int, desk: Serving) -> Response:
    desk.holdings.resume(_held(desk, owner, name, number))
    return _taken()


@writes.post("/pull-requests/{owner}/{name}/{number}:release", status_code=202,
             operation_id="releasePullRequest",
             responses={**HANDED_TO_THE_WATCHER, 409: NOT_FROZEN},
             summary="Let go of the worktree a frozen pull request's manager is on.")
def release(owner: Owner, name: Name, number: int, desk: Serving) -> Response:
    """The frozen dashboard's `w`. A frozen manager stops its board, so this
    is the only page left that can ask. The watcher keeps the old worktree
    under another name and builds a fresh one on its next cycle.
    """
    pr = _held(desk, owner, name, number)
    if not desk.holdings.release(pr):
        raise Refusal(409, ErrorCode.NOT_FROZEN,
                      f"{pr}'s manager is not frozen on the wrong branch")
    return _taken()


writes.add_api_route(
    "/client-errors", report_client_error, methods=["POST"], status_code=204,
    operation_id="reportHubClientError",
    summary="Write an error the page hit into the watcher's log.")


@reads.api_route("/{unknown:path}", methods=["GET", "POST"], include_in_schema=False)
def read_nothing(unknown: str) -> Response:
    raise Refusal(404, ErrorCode.NOT_FOUND, f"the hub serves nothing at {PREFIX}/{unknown}")


async def forward_to_board(owner: Owner, name: Name, number: int, path: str,
                           request: Request, desk: Serving) -> Response:
    """Whatever the pull request's board answers at `/api/{path}`: its
    status, body and headers, with `Location` moved under
    `/pr/{owner}/{name}/{number}`.
    """
    pr = _held(desk, owner, name, number)
    port = desk.holdings.board_port(pr)
    prefix = pr_page(pr)
    body = await request.body()
    answer = None if port is None else await run_in_threadpool(
        forwarded, port, prefix, request.method, target(request)[len(prefix):],
        request.headers, body, desk.streams)
    if answer is None:
        raise Refusal(503, ErrorCode.BOARD_UNREACHABLE, f"{pr}'s board is not answering")
    return answer


async def carry_to_board(websocket: WebSocket, owner: Owner, name: Name, number: int,
                         path: str) -> None:
    """A connection to a held pull request's board at `/api/{path}`, both
    ways, closed as the board closes it.
    """
    desk: Desk = websocket.app.state.desk
    try:
        pr = _held(desk, owner, name, number)
    except Refusal as refused:
        await websocket.accept()
        await websocket.close(GONE, str(refused))
        return
    port = await run_in_threadpool(desk.holdings.board_port, pr)
    prefix = pr_page(pr)
    await relayed(websocket, port, target(websocket)[len(prefix):],
                  f"{pr}'s board is not answering")


PROXIED: dict[int | str, dict[str, Any]] = {
    404: {"description": "The watcher holds no pull request with this number in this repo.",
          "model": Errors},
    503: {"description": "The watcher holds the pull request, but its board does not "
                         "answer: it has none yet, it is starting, or its manager is "
                         "frozen or down. The code is `board-unreachable`.",
          "model": Errors}}

proxy = APIRouter(tags=["hub"])
proxy.add_api_route("/pr/{owner}/{name}/{number}/api/{path:path}", forward_to_board, methods=["GET"],
                    operation_id="readThroughTheHub", responses=PROXIED,
                    summary="A read of a held pull request's board, on the hub's address.")
proxy.add_api_route("/pr/{owner}/{name}/{number}/api/{path:path}", forward_to_board, methods=["POST"],
                    operation_id="writeThroughTheHub", responses=PROXIED,
                    summary="A write to a held pull request's board, on the hub's address.")
proxy.add_api_route("/pr/{owner}/{name}/{number}/api/{path:path}", forward_to_board,
                    methods=["PUT", "PATCH", "DELETE"], include_in_schema=False)
proxy.add_api_websocket_route("/pr/{owner}/{name}/{number}/api/{path:path}", carry_to_board)


page = APIRouter()


@page.get("/{whatever:path}", include_in_schema=False)
async def serve_the_page(request: Request, desk: Serving) -> Response:
    return await run_in_threadpool(
        page_at, desk.fonts, desk.app_root, target(request),
        request.headers.get("Accept-Encoding"),
        failed=b"<p>hub error \xe2\x80\x94 see the watcher's log</p>")


def hub_app(desk: Desk, port: int) -> FastAPI:
    app = RefusingApp(
        title="Hub",
        version="1.0.0",
        summary="Every pull request the watcher holds.",
        description=DESCRIPTION,
        openapi_url=None, docs_url=None, redoc_url=None,
        routes=[*writes.routes, *setup.writes.routes, *setup.reads.routes, *reads.routes,
                *proxy.routes, *page.routes],
    )
    app.state.desk = desk
    add_refusal_handlers(app)
    guard(app, port, name="hub", failed=FAILED)
    return app


class ServedHub:
    def __init__(self, listen: Listen, *, app_root: Path, font_dir: str | None,
                 dashboards: Dashboards, ledger: Ledger, pulse: WatcherPulse,
                 clock: UtcClock, watching: Collection[Repo], version: str | None,
                 problem: Callable[[], str | None], setup: SetupDesk, releases: ReleaseRecord,
                 tour: TourMarker, open_streams: int) -> None:
        self._listen = listen
        self._releases = releases
        self._tour = tour
        self._setup = setup
        self._version = version
        self._problem = problem
        self._open_streams = open_streams
        self._ledger = ledger
        self._pulse = pulse
        self._clock = clock
        self._app_root = app_root
        self._fonts = routes.served_fonts(font_dir)
        self._wall = Wall(dashboards, watching)
        self._lock = threading.Lock()
        self._held: tuple[Pr, ...] | None = None
        self._listening: Listening | None = None
        self._url: str | None = None

    def start(self, port: int, holdings: Holdings, state: HubState) -> str:
        with self._lock:
            if self._listening is not None and self._url is not None:
                return self._url
            listening = self._listen(port)
            url = loopback_url(listening.port)
            desk = Desk(holdings=holdings, held=self._shown, told=self._told, wall=self._wall,
                        ledger=self._ledger, pulse=self._pulse, clock=self._clock, url=url,
                        app_root=self._app_root, fonts=self._fonts,
                        streams=anyio.CapacityLimiter(self._open_streams), state=state,
                        version=self._version, problem=self._problem, setup=self._setup,
                        releases=self._releases, tour=self._tour)
            listening.serve(hub_app(desk, listening.port))
            self._listening, self._url = listening, url
            return url

    def show(self, prs: Sequence[Pr]) -> None:
        with self._lock:
            self._held = tuple(dict.fromkeys(prs))

    def stop(self) -> bool:
        with self._lock:
            if self._listening is None:
                return False
            listening = self._listening
            self._listening, self._url = None, None
        listening.close()
        return True

    def _shown(self) -> tuple[Pr, ...]:
        with self._lock:
            return self._held or ()

    def _told(self) -> bool:
        with self._lock:
            return self._held is not None
