from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from github_orchestrator.domain import Pr


@dataclass(frozen=True)
class ManagedPr:
    pr: Pr
    worktree: str


class PrManager(Protocol):
    def run(self) -> None: ...


class Front(Protocol):
    def session(self) -> AbstractContextManager[None]: ...

    def serve_board(self) -> None: ...

    def wait(self, timeout: float) -> None: ...
