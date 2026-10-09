from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from github_orchestrator.board_api._contract import (
    ErrorCode,
    ErrorDetail,
    Errors,
)

NOT_FOUND = {"description": "No such thing on this pull request.",
             "model": Errors}

UNREADABLE_RECORD = {
    "description": "A record on disk will not parse. The repository says so "
                   "rather than handing back a conversation in a state the "
                   "rest of the board has to carry a row for.",
    "model": Errors}

MALFORMED_REQUEST = "The request does not say what it needs to."

BAD_RANGE = {"description": "`to_line` is before `from_line`, the range is "
                            "wider than 2000 lines, or a parameter is not "
                            "what it says it is.",
             "model": Errors}

NO_SUCH_FILE = {"description": "No such commit, or no such path at it.",
                "model": Errors}

NO_SUCH_DIFF = {"description": "The repository has no commit by one of "
                               "those names.",
                "model": Errors}

DIFF_FAILED = {"description": "git could not produce the diff.",
               "model": Errors}

PR_DIFF_FAILED = {"description": "git could not produce the diff, or find the "
                                 "head it was asked to diff.",
                  "model": Errors}

FETCH_FAILED = {"description": "git could not fetch the pull request's branch.",
                "model": Errors}

NOT_TEXT = {"description": "The file is not text, so it cannot be returned "
                           "as lines. `is_binary` on a diff says the same "
                           "thing in the other direction.",
            "model": Errors}

OUTSTANDING = {
    "description": "The domain will not take this operation. "
                   "`operation-outstanding` when the thread already has one "
                   "in flight and this is a second; otherwise the code names "
                   "what about the state forbids this particular verb, and "
                   "is one of the twelve the transition table refuses with. "
                   "The sentence beside the code is the domain's own.",
    "model": Errors}

PRECONDITION_FAILED = {
    "description": "The thread moved under you; read it again. Checked "
                   "against the conversation's `etag` field, not the "
                   "collection's header.",
    "model": Errors}

TOO_LONG = {"description": "The body is longer than GitHub will take.",
            "model": Errors}


def _malformed() -> dict[str, Any]:
    return {"description": MALFORMED_REQUEST,
            "content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/Errors"}}}}


def _fastapis_own(answer: dict[str, Any] | None) -> bool:
    schema = (answer or {}).get("content", {}).get("application/json", {}).get("schema", {})
    return bool(schema.get("$ref", "").endswith("/HTTPValidationError"))


class RefusingApp(FastAPI):
    """A FastAPI whose document declares the refusals this app gives.

    FastAPI writes a `422` carrying its own error shape onto every route with
    a parameter or a body, and `add_refusal_handlers` answers that same
    request `400` with `Errors`, so the generated document declares a
    response no route can give and omits the one it does.

    Rewriting the document is the only way to say so. FastAPI leaves the
    `422` out for a route that declares a `422`, a `4XX` or a `default` of
    its own, and each of those declares something else that is not true.
    Doing it over the whole document rather than route by route means a route
    added later is covered without being told, and a route with a sentence of
    its own for the `400` keeps it.
    """

    def openapi(self) -> dict[str, Any]:
        document = super().openapi()
        for methods in document["paths"].values():
            for operation in methods.values():
                answers = operation["responses"]
                if _fastapis_own(answers.get("422")):
                    del answers["422"]
                    answers.setdefault("400", _malformed())
        schemas = document["components"]["schemas"]
        for gone in ("HTTPValidationError", "ValidationError"):
            schemas.pop(gone, None)
        return document


class Refusal(Exception):
    """A refusal on its way out as `Errors`.

    Raised rather than returned so a read can give up wherever it notices,
    and so every route answers refusals in one shape without each one
    assembling the document.
    """

    def __init__(self, status: int, code: ErrorCode, detail: str,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.headers = headers or {}


def refused(status: int, code: ErrorCode, detail: str,
            headers: dict[str, str] | None = None) -> JSONResponse:
    document = Errors(errors=[ErrorDetail(status=status, code=code,
                                          detail=detail)])
    return JSONResponse(status_code=status, headers=headers,
                        content=document.model_dump(mode="json"))


def _sentence(exc: RequestValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors())


async def _refused(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, Refusal):
        raise exc
    return refused(exc.status, exc.code, exc.detail, exc.headers)


async def _unvalidated(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RequestValidationError):
        raise exc
    return refused(400, ErrorCode.MALFORMED_REQUEST, _sentence(exc))


def add_refusal_handlers(app: FastAPI) -> None:
    """Answer every refusal as `Errors`, including the ones FastAPI raises.

    FastAPI's own answer to a request that will not validate is a `422` with
    a `detail` array, which is a second error shape for a client to learn.
    """
    app.add_exception_handler(Refusal, _refused)
    app.add_exception_handler(RequestValidationError, _unvalidated)
