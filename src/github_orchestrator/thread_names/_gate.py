import fcntl
import logging
import time
from pathlib import Path

from github_orchestrator.terminal_sessions import Terminals
from github_orchestrator.thread_names._marker import LAYOUT, layout_of, write_marker
from github_orchestrator.thread_names._pass import ThreadNames, ThreadRename
from github_orchestrator.thread_names.interface import HeldFolder

log = logging.getLogger(__name__)

CLOSE_CHECKS = 50
CLOSE_CHECK_SECONDS = 0.1


def _inside(worktree: str, folder: Path) -> bool:
    return Path(worktree).resolve().is_relative_to(folder.resolve())


class LockedNameMigration:
    def __init__(self, marker: Path, lock: Path, version: str | None,
                 names: ThreadNames | None, terminals: Terminals) -> None:
        self._marker = marker
        self._lock = lock
        self._version = version
        self._names = names
        self._terminals = terminals
        self._seen = False

    def migrated(self) -> bool:
        if not self._seen:
            self._seen = layout_of(self._marker) >= LAYOUT
        return self._seen

    def _sessions_in(self, planned: list[ThreadRename]) -> list[HeldFolder]:
        worktrees = [session.worktree for sessions in self._terminals.everywhere()
                     for session in sessions.listed()]
        return [HeldFolder(thread.pr, thread.key, str(thread.folder)) for thread in planned
                if thread.left is None and thread.folder is not None
                and any(_inside(worktree, thread.folder) for worktree in worktrees)]

    def held(self) -> list[HeldFolder]:
        if self._names is None or self.migrated():
            return []
        return self._sessions_in(self._names.planned())

    def close_sessions(self) -> None:
        for _ in range(CLOSE_CHECKS):
            held = self.held()
            if not held:
                return
            for sessions in self._terminals.everywhere():
                if any(_inside(session.worktree, Path(one.folder))
                       for session in sessions.listed() for one in held):
                    sessions.hang_up()
            time.sleep(CLOSE_CHECK_SECONDS)

    def migrate(self) -> list[HeldFolder]:
        if self._names is None or self.migrated():
            return []
        self._lock.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.migrated():
                return []
            planned = self._names.planned()
            held = self._sessions_in(planned)
            if held:
                return held
            log.info("migrating thread names to carry their key's case")
            if not self._names.rename(planned):
                return []
            write_marker(self._marker, self._version)
            self._seen = True
        return []
