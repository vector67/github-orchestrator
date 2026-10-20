from collections.abc import Mapping, Set
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from github_orchestrator.domain import Pr


@dataclass(frozen=True)
class Summary:
    wanted: datetime | None = None
    answered: datetime | None = None
    head_sha: str | None = None
    started: datetime | None = None
    finished: datetime | None = None
    exit_status: int | None = None
    stderr: str | None = None
    markdown: str | None = None
    mismatches: int | None = None


class PrSummaries(Protocol):
    def want(self, pr: Pr) -> None: ...

    def load(self, pr: Pr) -> Summary | None: ...

    def save(self, pr: Pr, summary: Summary) -> None: ...

    def due(self, in_flight: Set[Pr]) -> list[Pr]: ...


@dataclass(frozen=True)
class Progress:
    since: datetime
    done: Mapping[str, bool]
    agents: int


class SummaryLane(Protocol):
    def poll(self) -> None: ...

    def start(self, pr: Pr, *, use_github_api: bool) -> str | None: ...

    def progress(self, pr: Pr) -> Progress | None: ...

    def behind(self, pr: Pr, head: str | None) -> int | None: ...
