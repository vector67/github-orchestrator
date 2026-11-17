import json
import math
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

import anyio
from anyio.streams.memory import MemoryObjectSendStream
from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Scope, Send

from github_orchestrator.board_api._etag import tag_of

EVENT_STREAM = "text/event-stream"
RETRY_MS = 1000


async def _events(event: str, read: Callable[[], BaseModel], last: str | None,
                  heartbeat_seconds: float, check_seconds: float) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    quiet = 0.0
    while True:
        payload = await run_in_threadpool(read)
        tag = tag_of(payload).strip('"')
        if tag != last:
            last, quiet = tag, 0.0
            yield f"event: {event}\nid: {tag}\ndata: {payload.model_dump_json()}\n\n"
        elif quiet >= heartbeat_seconds:
            quiet = 0.0
            yield ": heartbeat\n\n"
        await anyio.sleep(check_seconds)
        quiet += check_seconds


def streamed(request: Request, event: str, read: Callable[[], BaseModel],
             heartbeat_seconds: float, check_seconds: float) -> StreamingResponse:
    return StreamingResponse(
        _events(event, read, request.headers.get("Last-Event-ID"), heartbeat_seconds,
                check_seconds),
        media_type=EVENT_STREAM, headers={"Cache-Control": "no-store"})


FOLLOWABLE = re.compile(
    r"^/pr/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/[0-9]{1,18}/api/[a-z/-]+/stream(\?[^#]*)?$")

_SENT_ALONE = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
               "http_version": "1.1", "method": "GET", "root_path": ""}


def _alone(scope: Scope, follow: str) -> Scope:
    path, _, query = follow.partition("?")
    headers = [(name, value) for name, value in scope["headers"]
               if name.lower() != b"last-event-id"]
    return {**_SENT_ALONE, "scheme": scope.get("scheme", "http"), "server": scope.get("server"),
            "client": scope.get("client"), "path": path, "raw_path": path.encode(),
            "query_string": query.encode(), "headers": headers, "state": {}}


def _retold(follow: str, block: bytes) -> bytes | None:
    fields = dict(line.partition(":")[::2] for line in block.decode().split("\n"))
    if "" in fields:
        return b": heartbeat\n\n"
    if "data" not in fields:
        return None
    event, data = fields.get("event", "").strip(), fields["data"].removeprefix(" ")
    return f'event: {event}\ndata: {{"path":{json.dumps(follow)},"data":{data}}}\n\n'.encode()


async def _relayed(served: ASGIApp, scope: Scope, follow: str,
                   heard: MemoryObjectSendStream[bytes]) -> None:
    status = 200
    buffered = b""

    async def never_hung_up() -> Message:
        await anyio.sleep_forever()
        raise AssertionError

    async def told(message: Message) -> None:
        nonlocal status, buffered
        if message["type"] == "http.response.start":
            status = message["status"]
            return
        if status != 200:
            return
        *blocks, buffered = (buffered + message.get("body", b"")).split(b"\n\n")
        for block in blocks:
            retold = _retold(follow, block)
            if retold is not None:
                await heard.send(retold)

    async with heard:
        await served(_alone(scope, follow), never_hung_up, told)
        if status != 200:
            await heard.send(
                f'event: refused\ndata: {{"path":{json.dumps(follow)},"status":{status}}}\n\n'
                .encode())


async def _nothing() -> AsyncIterator[bytes]:
    return
    yield


class Followed(StreamingResponse):
    def __init__(self, served: ASGIApp, scope: Scope, follows: list[str]) -> None:
        super().__init__(_nothing(), media_type=EVENT_STREAM, headers={"Cache-Control": "no-store"})
        self._served = served
        self._scope = scope
        self._follows = follows

    async def stream_response(self, send: Send) -> None:
        await send({"type": "http.response.start", "status": self.status_code,
                    "headers": self.raw_headers})
        sending, heard = anyio.create_memory_object_stream[bytes](math.inf)
        async with anyio.create_task_group() as relays:
            with sending:
                for follow in self._follows:
                    relays.start_soon(_relayed, self._served, self._scope, follow, sending.clone())
            try:
                await send({"type": "http.response.body", "body": f"retry: {RETRY_MS}\n\n".encode(),
                            "more_body": True})
                async with heard:
                    async for block in heard:
                        await send({"type": "http.response.body", "body": block, "more_body": True})
            except OSError:
                relays.cancel_scope.cancel()
                return
        await send({"type": "http.response.body", "body": b"", "more_body": False})


FOLLOWED: dict[int | str, dict[str, Any]] = {200: {
    "description": (
        f"An endless `{EVENT_STREAM}` carrying every followed stream on one connection. "
        f"It opens with `retry: {RETRY_MS}`. Each followed stream's event comes as an "
        "event of the same name whose data is `{\"path\", \"data\"}`: the followed path and "
        "that stream's data. A followed path the hub refuses comes once as a `refused` event "
        "whose data is `{\"path\", \"status\"}`. Each followed stream's `: heartbeat` comments "
        "come through, so a page can tell a quiet connection from a dropped one."),
    "content": {EVENT_STREAM: {"itemSchema": {
        "type": "object",
        "required": ["event", "data"],
        "properties": {
            "event": {"type": "string"},
            "data": {"type": "string", "contentMediaType": "application/json",
                     "contentSchema": {
                         "type": "object",
                         "required": ["path"],
                         "properties": {"path": {"type": "string"}, "data": {},
                                        "status": {"type": "integer"}}}},
        }}}}}}


def described(event: str, data: type[BaseModel]) -> dict[int | str, dict[str, Any]]:
    return {200: {
        "description": (
            f"An endless `{EVENT_STREAM}`. It opens with `retry: {RETRY_MS}`, sends a "
            f"`{event}` event at once and again only when its data changes, and a "
            "`: heartbeat` comment after 15 quiet seconds, so a page can tell a quiet "
            "stream from a dropped one. Each "
            "event's `id` is the `ETag` the matching read would answer, without its "
            "quotes; reconnect with it as `Last-Event-ID` and the stream sends "
            "nothing until the data moves past it."),
        "content": {EVENT_STREAM: {"itemSchema": {
            "type": "object",
            "required": ["event", "id", "data"],
            "properties": {
                "event": {"const": event},
                "id": {"type": "string"},
                "data": {"type": "string", "contentMediaType": "application/json",
                         "contentSchema": {"$ref": f"#/components/schemas/{data.__name__}"}},
            }}}}}}
