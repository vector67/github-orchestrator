from collections.abc import AsyncIterator, Callable
from typing import Any

import anyio
from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from github_orchestrator.board_api._etag import tag_of

EVENT_STREAM = "text/event-stream"
RETRY_MS = 1000


async def _events(event: str, read: Callable[[], BaseModel | None], last: str | None,
                  heartbeat_seconds: float, check_seconds: float) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    quiet = 0.0
    while True:
        payload = await run_in_threadpool(read)
        body = None if payload is None else payload.model_dump_json()
        tag = None if payload is None else tag_of(payload).strip('"')
        if tag is not None and tag != last:
            last, quiet = tag, 0.0
            yield f"event: {event}\nid: {tag}\ndata: {body}\n\n"
        elif quiet >= heartbeat_seconds:
            quiet = 0.0
            yield ": heartbeat\n\n"
        await anyio.sleep(check_seconds)
        quiet += check_seconds


def streamed(request: Request, event: str, read: Callable[[], BaseModel | None],
             heartbeat_seconds: float, check_seconds: float) -> StreamingResponse:
    return StreamingResponse(
        _events(event, read, request.headers.get("Last-Event-ID"), heartbeat_seconds,
                check_seconds),
        media_type=EVENT_STREAM, headers={"Cache-Control": "no-store"})


def described(event: str, data: type[BaseModel]) -> dict[int | str, dict[str, Any]]:
    return {200: {
        "description": (
            f"An endless `{EVENT_STREAM}`. It opens with `retry: {RETRY_MS}`, sends a "
            f"`{event}` event at once and again only when its data changes, and a "
            "`: heartbeat` comment after 15 quiet seconds, so the hub's 75-second "
            "read never times out. Each "
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
