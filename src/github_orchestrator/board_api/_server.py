import socket
import threading
from pathlib import Path

import anyio
import uvicorn
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from github_orchestrator.board_api import _routes as routes
from github_orchestrator.board_api._app import Board, board_app
from github_orchestrator.board_api._loopback import Listen, Listening, loopback_url
from github_orchestrator.board_api.interface import ManagerPanel
from github_orchestrator.conversation import ConversationManagerFactory
from github_orchestrator.domain import Pr, UtcClock
from github_orchestrator.terminal_sessions import TerminalSessions
from github_orchestrator.working_copies import WorkingCopies

GRACE_SECONDS = 1
TERMINAL_THREADS = 64


class _EndsOnShutdown:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._closing: anyio.Event | None = None

    def close(self) -> None:
        if self._closing is not None:
            self._closing.set()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        if self._closing is None:
            self._closing = anyio.Event()
        closing = self._closing
        unfinished = False

        async def sending(message: Message) -> None:
            nonlocal unfinished
            if message["type"] == "http.response.start":
                unfinished = True
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                unfinished = False
            await send(message)

        async with anyio.create_task_group() as group:
            async def cut_short() -> None:
                await closing.wait()
                group.cancel_scope.cancel()

            group.start_soon(cut_short)
            await self._app(scope, receive, sending)
            group.cancel_scope.cancel()
        if unfinished:
            await send({"type": "http.response.body", "body": b"", "more_body": False})


class _Server(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, app: _EndsOnShutdown) -> None:
        super().__init__(config)
        self._ending = app

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        self._ending.close()
        await super().shutdown(sockets)


class _Loopback:
    def __init__(self, port: int) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            sock.listen()
        except OSError:
            sock.close()
            raise
        self._sock = sock
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self._sock.getsockname()[1])

    def serve(self, app: ASGIApp) -> None:
        ending = _EndsOnShutdown(app)
        self._server = _Server(uvicorn.Config(
            ending, log_config=None, access_log=False,
            lifespan="off", proxy_headers=False,
            timeout_graceful_shutdown=GRACE_SECONDS), ending)
        self._thread = threading.Thread(target=self._server.run,
                                        kwargs={"sockets": [self._sock]}, daemon=True)
        self._thread.start()

    def close(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)


def listen_on_loopback(port: int) -> Listening:
    return _Loopback(port)


class ServedBoardApi:
    def __init__(self, listen: Listen, conversation_managers: ConversationManagerFactory,
                 working_copies: WorkingCopies, terminals: TerminalSessions, *, app_root: Path,
                 font_dir: str | None, check_presence: bool, hub_port: int,
                 heartbeat_seconds: float, check_seconds: float, first_names_only: bool,
                 clock: UtcClock) -> None:
        self._listen = listen
        self._clock = clock
        self._first_names_only = first_names_only
        self._heartbeat_seconds = heartbeat_seconds
        self._check_seconds = check_seconds
        self._hub_url = loopback_url(hub_port)
        self._conversation_managers = conversation_managers
        self._working_copies = working_copies
        self._terminals = terminals
        self._app_root = app_root
        self._fonts = routes.served_fonts(font_dir)
        self._check_presence = check_presence
        self._lock = threading.Lock()
        self._listening: Listening | None = None
        self._url: str | None = None

    def start(self, pr: Pr, *, port: int, manager: ManagerPanel) -> str:
        with self._lock:
            if self._listening is not None and self._url is not None:
                return self._url
            threads = self._conversation_managers.of(pr)
            listening = self._listen(port)
            board = Board(conversations=threads,
                          git=self._working_copies.checkout(pr),
                          pr=pr, port=listening.port, manager=manager,
                          app_root=self._app_root, hub_url=self._hub_url,
                          fonts=self._fonts,
                          check_presence=self._check_presence,
                          first_names_only=self._first_names_only,
                          heartbeat_seconds=self._heartbeat_seconds,
                          check_seconds=self._check_seconds,
                          terminals=self._terminals,
                          terminal_threads=anyio.CapacityLimiter(TERMINAL_THREADS),
                          clock=self._clock)
            listening.serve(board_app(board))
            self._listening = listening
            self._url = loopback_url(listening.port)
            return self._url

    def stop(self) -> bool:
        with self._lock:
            if self._listening is None:
                return False
            listening = self._listening
            self._listening, self._url = None, None
        listening.close()
        return True

    def is_running(self) -> bool:
        with self._lock:
            return self._listening is not None
