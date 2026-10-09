import http.client
import logging
import socket
from collections.abc import AsyncIterator, Mapping

import anyio
from fastapi import Response
from fastapi.responses import StreamingResponse

from github_orchestrator.board_api._loopback import loopback_url

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 75
CHUNK_BYTES = 64 * 1024

PASSED_ON = ("accept", "accept-encoding", "content-type", "if-match", "if-none-match",
             "last-event-id")

LEFT_BEHIND = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
               "trailer", "transfer-encoding", "upgrade", "server", "date", "content-length"}


def _answered_headers(answer: http.client.HTTPResponse, prefix: str) -> list[tuple[str, str]]:
    return [(name, prefix + value if name.lower() == "location" else value)
            for name, value in answer.getheaders() if name.lower() not in LEFT_BEHIND]


async def _streamed(connection: http.client.HTTPConnection, answer: http.client.HTTPResponse,
                    streams: anyio.CapacityLimiter, path: str) -> AsyncIterator[bytes]:
    try:
        while chunk := await anyio.to_thread.run_sync(
                answer.read1, CHUNK_BYTES, limiter=streams, abandon_on_cancel=True):
            yield chunk
    except (http.client.HTTPException, OSError) as dropped:
        log.info("the board went away mid-stream at %s: %r", path, dropped)
    finally:
        _hang_up(connection)


def _hang_up(connection: http.client.HTTPConnection) -> None:
    if connection.sock is not None:
        try:
            connection.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    connection.close()


def forwarded(port: int, prefix: str, method: str, target: str,
              asked: Mapping[str, str], body: bytes,
              streams: anyio.CapacityLimiter) -> Response | None:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=TIMEOUT_SECONDS)
    headers = {name: asked[name] for name in PASSED_ON if name in asked}
    headers["Origin"] = loopback_url(port)
    try:
        connection.request(method, target, body=body or None, headers=headers)
        answer = connection.getresponse()
    except OSError:
        connection.close()
        return None
    passed = _answered_headers(answer, prefix)
    if answer.getheader("Content-Length") is None and answer.status not in (204, 304):
        streaming = StreamingResponse(_streamed(connection, answer, streams, prefix + target),
                                      status_code=answer.status)
        streaming.raw_headers = [*streaming.raw_headers, *_encoded(passed)]
        return streaming
    try:
        content = answer.read()
    finally:
        connection.close()
    buffered = Response(content=content, status_code=answer.status)
    buffered.raw_headers = [*buffered.raw_headers, *_encoded(passed)]
    return buffered


def _encoded(headers: list[tuple[str, str]]) -> list[tuple[bytes, bytes]]:
    return [(name.lower().encode("latin-1"), value.encode("latin-1")) for name, value in headers]
