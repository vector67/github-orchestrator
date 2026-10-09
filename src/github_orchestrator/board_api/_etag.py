import hashlib
import json
from typing import Any

from fastapi import Request, Response
from pydantic import BaseModel

JSON = "application/json"

HEADER: dict[str, Any] = {
    "ETag": {"description": "The resource's revision. Echo it as "
                            "`If-None-Match` on the next read. For an "
                            "operation, send the conversation's `etag` field "
                            "as `If-Match` rather than this.",
             "schema": {"type": "string"}}}

TAGGED: dict[int | str, dict[str, Any]] = {
    200: {"headers": HEADER},
    304: {"description": "Unchanged since the `If-None-Match` you sent. No "
                         "body.",
          "headers": HEADER}}


def etag_of(body: bytes) -> str:
    """The revision of a serialised payload.

    Hashing what goes on the wire, rather than stamping a clock or counting
    writes, is what makes the tag stable across a restart: a client's cached
    copy survives the board being stopped and started, and two boards serving
    the same facts agree.
    """
    return f'"{hashlib.sha256(body).hexdigest()[:16]}"'


AS_OF = "listed_at"


def _content(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _content(item) for key, item in value.items() if key != AS_OF}
    if isinstance(value, list):
        return [_content(item) for item in value]
    return value


def tag_of(payload: BaseModel) -> str:
    return etag_of(json.dumps(_content(payload.model_dump(mode="json"))).encode())


def _offered(header: str | None) -> set[str]:
    return {tag.strip() for tag in (header or "").split(",") if tag.strip()}


def answered(request: Request, payload: BaseModel) -> Response:
    """The payload with its `ETag`, or `304` when the client already has it."""
    body = payload.model_dump_json().encode()
    tag = tag_of(payload)
    offered = _offered(request.headers.get("If-None-Match"))
    if tag in offered or "*" in offered:
        return Response(status_code=304, headers={"ETag": tag})
    return Response(content=body, media_type=JSON, headers={"ETag": tag})
