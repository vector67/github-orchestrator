import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from github_orchestrator.domain import Pr
from github_orchestrator.thread_records.interface import PrRecords


@dataclass
class _Failure:
    error: Exception | None = None
    times: int | None = None

    def strike(self) -> None:
        if self.error is None:
            return
        error = self.error
        if self.times is not None:
            self.times -= 1
            if self.times <= 0:
                self.error, self.times = None, None
        raise error


@dataclass
class _Faults:
    saves: _Failure = field(default_factory=_Failure)
    lists: _Failure = field(default_factory=_Failure)
    locks: dict[str, Exception] = field(default_factory=dict)


class FakePrRecords:
    def __init__(self, faults: _Faults | None = None) -> None:
        self.documents: dict[tuple[str, str], bytes] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._faults = faults or _Faults()

    def save(self, kind: str, key: str, document: bytes) -> None:
        self._faults.saves.strike()
        self.documents.pop((kind, key), None)
        self.documents[(kind, key)] = bytes(document)

    def load(self, kind: str, key: str) -> bytes | None:
        return self.documents.get((kind, key))

    def list(self, kind: str) -> dict[str, bytes | None]:
        self._faults.lists.strike()
        return {key: document for (stored_kind, key), document in self.documents.items()
                if stored_kind == kind}

    @contextmanager
    def lock(self, name: str) -> Iterator[None]:
        refused = self._faults.locks.get(name)
        if refused is not None:
            raise refused
        with self._locks.setdefault(name, threading.Lock()):
            yield

    def delete(self, kind: str, key: str) -> None:
        self.documents.pop((kind, key), None)


class FakeThreadRecords:
    def __init__(self) -> None:
        self.prs: dict[Pr, FakePrRecords] = {}
        self._faults = _Faults()

    def of(self, pr: Pr) -> PrRecords:
        return self.pr(pr)

    def pr(self, pr: Pr) -> FakePrRecords:
        return self.prs.setdefault(pr, FakePrRecords(self._faults))

    def forget(self, pr: Pr) -> bool:
        self.prs.pop(pr, None)
        return True

    def fail_saves(self, error: Exception | None, *, times: int | None = None) -> None:
        self._faults.saves = _Failure(error, times)

    def fail_lists(self, error: Exception | None, *, times: int | None = None) -> None:
        self._faults.lists = _Failure(error, times)

    def refuse_lock(self, name: str, error: Exception) -> None:
        self._faults.locks[name] = error
