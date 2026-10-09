import json
from collections.abc import Callable, Set
from datetime import datetime
from pathlib import Path
from typing import Any

from github_orchestrator.change_detection._facts import facts_of
from github_orchestrator.change_detection._rules import (
    advance,
    closing,
    ended,
    is_closing,
)
from github_orchestrator.change_detection.interface import (
    Facts,
    Poll,
    PrClosed,
    PrEvent,
    Stored,
)
from github_orchestrator.change_detection.interface import (
    MergeableReason as MergeableReason,
)
from github_orchestrator.change_detection.interface import (
    ReviewDecision as ReviewDecision,
)
from github_orchestrator.change_detection.interface import (
    UnmergeableReason as UnmergeableReason,
)
from github_orchestrator.domain import Pr, Repo


class FakeChangeDetection:
    def __init__(self, account: str, poll_interval: int,
                 clock: Callable[[], datetime]) -> None:
        self._account = account
        self._poll_interval = poll_interval
        self._clock = clock
        self._held: dict[Pr, str] = {}

    def advance(self, pr: Pr, poll: Poll, pending_ci_checks: set[str]) -> list[PrEvent]:
        step = advance(pr, self._last(pr), poll, pending_ci_checks,
                       self._clock().isoformat(), account=self._account,
                       poll_interval=self._poll_interval)
        self._held[pr] = json.dumps(step.snapshot)
        return step.events

    def ended(self, *, still_open: bool, merged: bool) -> PrClosed:
        return ended(still_open=still_open, merged=merged)

    def facts(self, pr: Pr) -> Facts | None:
        snapshot = self._last(pr)
        return None if snapshot is None else facts_of(snapshot, self._account)

    def _last(self, pr: Pr) -> dict[str, Any] | None:
        held = self._held.get(pr)
        if held is None:
            return None
        snapshot: dict[str, Any] = json.loads(held)
        return snapshot

    def tracked(self) -> list[Pr]:
        return list(self._held)

    def stored(self) -> list[Stored]:
        return [Stored(pr, self.facts(pr), None) for pr in sorted(self._held)]

    def closing(self, pr: Pr) -> bool:
        return is_closing(self._last(pr))

    def close(self, pr: Pr) -> None:
        self._held[pr] = json.dumps(closing(self._last(pr)))

    def forget(self, pr: Pr) -> bool:
        self._held.pop(pr, None)
        return True

    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]:
        others = sorted({pr.repo for pr in self._held if pr.repo not in keep},
                        key=str)
        self._held = {pr: held for pr, held in self._held.items() if pr.repo in keep}
        return [into / repo.owner / repo.name for repo in others]
