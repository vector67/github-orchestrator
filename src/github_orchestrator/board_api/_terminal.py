import json
import logging
from collections.abc import Awaitable, Callable

import anyio
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake
from websockets.typing import Origin

from github_orchestrator.board_api._loopback import loopback_url
from github_orchestrator.terminal_sessions import TerminalSessions

log = logging.getLogger(__name__)

READ_SECONDS = 0.5
ENDED = 1000
GONE = 4404
UNREACHABLE = 4503
OPEN_SECONDS = 5


def _size_of(text: str) -> tuple[int, int] | None:
    try:
        asked = json.loads(text)
        columns, rows = asked["columns"], asked["rows"]
    except (ValueError, TypeError, KeyError):
        return None
    if type(columns) is not int or type(rows) is not int or columns < 1 or rows < 1:
        return None
    return columns, rows


async def carried(websocket: WebSocket, sessions: TerminalSessions, session: str,
                  after: int, threads: anyio.CapacityLimiter) -> None:
    connection = sessions.attach(session, after)
    if connection is None:
        await websocket.accept()
        await websocket.close(GONE, "the session has ended")
        return

    async def typed() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                await anyio.to_thread.run_sync(connection.write, message["bytes"],
                                               limiter=threads)
            elif message.get("text") is not None:
                size = _size_of(message["text"])
                if size is None:
                    log.info("terminal session %s: ignored %r from the page", session,
                             message["text"][:80])
                else:
                    await anyio.to_thread.run_sync(connection.resize, *size,
                                                   limiter=threads)

    async def printed() -> None:
        while (chunk := await anyio.to_thread.run_sync(
                connection.read, READ_SECONDS, limiter=threads,
                abandon_on_cancel=True)) is not None:
            if chunk:
                await websocket.send_bytes(chunk)
        await websocket.send_text(json.dumps({"exit_code": connection.exit_code()}))
        await websocket.close(ENDED)

    try:
        await websocket.accept()
        async with anyio.create_task_group() as sides:
            async def until_either_ends(side: Callable[[], Awaitable[None]]) -> None:
                await side()
                sides.cancel_scope.cancel()

            sides.start_soon(until_either_ends, typed)
            sides.start_soon(until_either_ends, printed)
    except* (WebSocketDisconnect, RuntimeError, OSError):
        log.info("terminal session %s: the page went away", session)
    finally:
        connection.close()


async def _board_socket(port: int, target: str) -> ClientConnection | None:
    try:
        return await connect(f"ws://127.0.0.1:{port}{target}",
                             origin=Origin(loopback_url(port)),
                             open_timeout=OPEN_SECONDS, max_size=None)
    except (OSError, InvalidHandshake, TimeoutError):
        log.info("the board on %d did not take a connection to %s", port, target)
        return None


async def relayed(websocket: WebSocket, port: int | None, target: str,
                  unreachable: str) -> None:
    board = None if port is None else await _board_socket(port, target)
    await websocket.accept()
    if board is None:
        await websocket.close(UNREACHABLE, unreachable)
        return

    async def to_the_board() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                await board.send(message["bytes"])
            elif message.get("text") is not None:
                await board.send(message["text"])

    async def to_the_page() -> None:
        try:
            async for message in board:
                if isinstance(message, bytes):
                    await websocket.send_bytes(message)
                else:
                    await websocket.send_text(message)
        except ConnectionClosed as closed:
            if closed.rcvd is None:
                log.info("the board went away mid-terminal at %s", target)
                await websocket.close(UNREACHABLE, unreachable)
                return
        await websocket.close(board.close_code or ENDED, board.close_reason or "")

    try:
        async with board, anyio.create_task_group() as sides:
            async def until_either_ends(side: Callable[[], Awaitable[None]]) -> None:
                await side()
                sides.cancel_scope.cancel()

            sides.start_soon(until_either_ends, to_the_board)
            sides.start_soon(until_either_ends, to_the_page)
    except* (WebSocketDisconnect, ConnectionClosed, RuntimeError, OSError):
        log.info("a terminal through the hub to %s went away", target)
