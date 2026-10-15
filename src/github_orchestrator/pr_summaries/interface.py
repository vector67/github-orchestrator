from collections.abc import Set
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
