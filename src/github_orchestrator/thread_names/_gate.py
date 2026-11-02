import fcntl
import logging
from collections.abc import Callable
from pathlib import Path

from github_orchestrator.thread_names._marker import LAYOUT, layout_of, write_marker

log = logging.getLogger(__name__)


class LockedNameMigration:
    def __init__(self, marker: Path, lock: Path, version: str | None,
                 rename: Callable[[], None] | None) -> None:
        self._marker = marker
        self._lock = lock
        self._version = version
        self._rename = rename
        self._seen = False

    def migrated(self) -> bool:
        if not self._seen:
            self._seen = layout_of(self._marker) >= LAYOUT
        return self._seen

    def migrate(self) -> None:
        if self._rename is None or self.migrated():
            return
        self._lock.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock, "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            if self.migrated():
                return
            log.info("migrating thread names to carry their key's case")
            self._rename()
            write_marker(self._marker, self._version)
            self._seen = True
