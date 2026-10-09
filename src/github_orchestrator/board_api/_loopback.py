from collections.abc import Callable
from typing import Protocol

from starlette.types import ASGIApp


class Listening(Protocol):
    @property
    def port(self) -> int: ...

    def serve(self, app: ASGIApp) -> None: ...

    def close(self) -> None: ...


Listen = Callable[[int], Listening]


def loopback_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"
