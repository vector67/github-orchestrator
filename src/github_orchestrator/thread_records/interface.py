from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Protocol

from github_orchestrator.domain import Pr


class UnreadableThread(Exception):
    pass


class PrRecords(Protocol):
    def save(self, kind: str, key: str, document: bytes) -> None: ...

    def load(self, kind: str, key: str) -> bytes | None: ...

    def list(self, kind: str) -> Mapping[str, bytes | None]: ...

    def lock(self, name: str) -> AbstractContextManager[None]: ...

    def delete(self, kind: str, key: str) -> None: ...


class ThreadRecords(Protocol):
    def of(self, pr: Pr) -> PrRecords: ...

    def forget(self, pr: Pr) -> bool: ...
