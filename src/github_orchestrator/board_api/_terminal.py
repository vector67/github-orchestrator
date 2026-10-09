import json
import logging
from collections.abc import Awaitable, Callable

import anyio
from starlette.websockets import WebSocket, WebSocketDisconnect

from github_orchestrator.terminal_sessions import TerminalSessions

log = logging.getLogger(__name__)

READ_SECONDS = 0.5
ENDED = 1000
GONE = 4404


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

