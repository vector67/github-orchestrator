import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send

from github_orchestrator.board_api import _routes as routes
from github_orchestrator.board_api._contract import ErrorCode, ErrorDetail, Errors
from github_orchestrator.board_api._loopback import loopback_url

log = logging.getLogger(__name__)

MAX_REQUEST_BYTES = 1024 * 1024

POLICY = ("default-src 'self'; img-src 'self'; object-src 'none'; "
          "style-src-elem 'self' 'unsafe-inline'; style-src-attr 'unsafe-inline'; "
          "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

GUARDING_HEADERS = {
    "Content-Security-Policy": POLICY,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
}


def _refusal(status: int, code: ErrorCode, detail: str) -> Response:
    return JSONResponse(status_code=status, content=Errors(errors=[
        ErrorDetail(status=status, code=code, detail=detail)]).model_dump(
            mode="json"))


def _foreign_host(headers: Headers, port: int, name: str) -> str | None:
    """A request addressed to any name but this server's is refused.

    A page on a name its owner points at 127.0.0.1 is same-origin with
    itself, so the browser lets it read whatever the server answers it. The
    Host it sends is its own name, which is what gives it away, on a read as
    much as on a write.
    """
    host = headers.get("Host")
    if host in (f"127.0.0.1:{port}", f"localhost:{port}"):
        return None
    return f"this {name} answers 127.0.0.1:{port}, not {host}"


def _foreign_site(headers: Headers, port: int) -> bool:
    """The server is loopback with no authentication, so what stands between
    a web page in another tab and the operator's pull requests is that a
    write, or a terminal, comes from this server's own page.
    """
    site = headers.get("Sec-Fetch-Site")
    origin = headers.get("Origin")
    return ((site is not None or origin is not None) and site != "same-origin"
            and origin != loopback_url(port))


def _unguarded(request: Request, port: int) -> Response | None:
    """What refuses a write before its body is read. A body is refused by
    its declared length rather than read to find out.
    """
    if _foreign_site(request.headers, port):
        return _refusal(403, ErrorCode.FOREIGN_ORIGIN,
                        "a write from another site's page is refused")
    declared = request.headers.get("Content-Length")
    if declared is None:
        return _refusal(411, ErrorCode.MALFORMED_REQUEST,
                        "a write must name its length")
    try:
        length = int(declared)
    except ValueError:
        return _refusal(400, ErrorCode.MALFORMED_REQUEST,
                        f"{declared} is not a length")
    if length < 0 or length > MAX_REQUEST_BYTES:
        return _refusal(413, ErrorCode.BODY_TOO_LONG,
                        f"a request body is at most {MAX_REQUEST_BYTES} bytes")
    return None


def _logged(request: Request, status: int, started: float) -> None:
    elapsed_ms = (time.monotonic() - started) * 1000
    level = (logging.WARNING if status >= 500 else logging.INFO if status >= 400
             else logging.DEBUG)
    log.log(level, "%s %s -> %d in %.0fms", request.method, request.url.path,
            status, elapsed_ms)


def guard(app: FastAPI, port: int, *, name: str, failed: str) -> None:
    @app.middleware("http")
    async def guarded(request: Request,
                      call_next: Callable[[Request], Awaitable[Response]],
                      ) -> Response:
        started = time.monotonic()
        foreign = _foreign_host(request.headers, port, name)
        answer = None if foreign is None else _refusal(403, ErrorCode.FOREIGN_ORIGIN, foreign)
        if answer is None and request.method not in ("GET", "HEAD"):
            answer = _unguarded(request, port)
        if answer is None:
            try:
                answer = await call_next(request)
            except Exception:
                log.exception("%s %s %s failed", name, request.method,
                              request.url.path)
                answer = _refusal(500, ErrorCode.SERVER_ERROR, failed)
        _logged(request, answer.status_code, started)
        answer.headers.update(GUARDING_HEADERS)
        return answer

    app.add_middleware(_GuardedSockets, port=port, name=name)


POLICY_VIOLATION = 1008


class _GuardedSockets:
    def __init__(self, app: ASGIApp, *, port: int, name: str) -> None:
        self._app = app
        self._port = port
        self._name = name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            headers = Headers(scope=scope)
            refused = _foreign_host(headers, self._port, self._name) or (
                "a connection from another site's page is refused"
                if _foreign_site(headers, self._port) else None) or (
                "a connection must come from this server's page, which names its origin"
                if headers.get("Origin") is None else None)
            if refused is not None:
                log.warning("%s refused a connection to %s: %s", self._name, scope["path"],
                            refused)
                await send({"type": "websocket.close", "code": POLICY_VIOLATION,
                            "reason": refused})
                return
        await self._app(scope, receive, send)


def target(request: HTTPConnection) -> str:
    raw: bytes = request.scope.get("raw_path") or request.url.path.encode()
    path = raw.split(b"?", 1)[0].decode("latin-1")
    query: bytes = request.scope.get("query_string") or b""
    return f"{path}?{query.decode('latin-1')}" if query else path


def _encoded(status: int, content_type: str, body: bytes,
             headers: dict[str, str], accept_encoding: str | None) -> Response:
    body, encoding = routes.encode_body(body, accept_encoding)
    sent = dict(headers)
    sent["Vary"] = "Accept-Encoding"
    if encoding:
        sent["Content-Encoding"] = encoding
    return Response(content=body, status_code=status, headers=sent,
                    media_type=content_type)


def page_at(fonts: routes.Fonts, app_root: Path, target: str,
            accept_encoding: str | None, *, failed: bytes) -> Response:
    try:
        status, content_type, body, headers = routes.handle_get(fonts, app_root, target)
    except Exception:
        log.exception("page GET %s failed", target)
        return _encoded(200, routes.HTML, failed, {}, accept_encoding)
    return _encoded(status, content_type, body, dict(headers), accept_encoding)
