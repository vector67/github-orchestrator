from collections.abc import Callable
from pathlib import Path
from typing import Any

from github_orchestrator.change_detection._disk import DiskChangeDetection
from github_orchestrator.domain import Pr, UtcClock


class WouldSaveChangeDetection(DiskChangeDetection):
    def __init__(self, state_dir: Path, account: str, poll_interval: int,
                 clock: UtcClock, say: Callable[[str], None]) -> None:
        super().__init__(state_dir, account, poll_interval, clock)
        self._say = say

    def _save(self, pr: Pr, snapshot: dict[str, Any]) -> None:
        self._say(f"would save state for {pr}")
