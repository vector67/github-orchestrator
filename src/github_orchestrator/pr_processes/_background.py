import json
import logging
import os
import subprocess
from collections.abc import Callable, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from github_orchestrator.domain import Pr, Repo
from github_orchestrator.pr_processes._changes import start
from github_orchestrator.pr_processes._layout import defunct_name, manager_argv
from github_orchestrator.pr_processes._places import Places
from github_orchestrator.pr_processes._pr_files import pr_file, tracked_prs
from github_orchestrator.pr_processes.interface import ManagerPane
from github_orchestrator.terminal_sessions import Terminals

log = logging.getLogger(__name__)

Run = Callable[..., subprocess.CompletedProcess[Any]]

RECORD = ".json"
OUTPUT = ".log"
DETACHED = 'output=$1; shift; "$@" </dev/null >>"$output" 2>&1 & echo $!'


@dataclass(frozen=True)
class _Record:
    pid: int
    worktree: str


def _parsed(text: str) -> _Record | None:
    try:
        fields = json.loads(text)
        pid, worktree = fields["pid"], fields["worktree"]
    except (ValueError, TypeError, KeyError):
        return None
    if type(pid) is not int or pid <= 1 or not isinstance(worktree, str):
        return None
    return _Record(pid, worktree)


class BackgroundPrProcesses:
    def __init__(self, run: Run, places: Places, terminals: Terminals) -> None:
        self._run = run
        self._places = places
        self._terminals = terminals

    def _record_file(self, pr: Pr) -> Path:
        return pr_file(self._places.manager_records_dir, pr, RECORD)

    def _record(self, pr: Pr) -> _Record | None:
        try:
            return _parsed(self._record_file(pr).read_text())
        except (OSError, UnicodeDecodeError):
            return None

    def _start(self, pr: Pr, worktree: str) -> None:
        output = pr_file(self._places.manager_logs_dir, pr, OUTPUT)
        output.parent.mkdir(parents=True, exist_ok=True)
        started = self._run(
            ["sh", "-c", DETACHED, "sh", str(output), *manager_argv(pr)],
            cwd=worktree, env={**os.environ, **self._places.environment},
            start_new_session=True, check=True, capture_output=True, text=True,
        )
        record = self._record_file(pr)
        record.parent.mkdir(parents=True, exist_ok=True)
        pid = int(started.stdout)
        record.write_text(json.dumps({"pid": pid, "worktree": worktree}))
        log.info("Started the agent manager for %s as pid %d in %s", pr, pid, worktree)

    def _runs_manager(self, pr: Pr, record: _Record) -> bool:
        listed = self._run(["ps", "-o", "command=", "-p", str(record.pid)],
                           check=False, capture_output=True, text=True)
        arguments = " ".join(manager_argv(pr)[1:])
        return listed.returncode == 0 and f" {arguments} " in f"{listed.stdout.strip()} "

    def _stop(self, pr: Pr, record: _Record) -> bool:
        if not self._runs_manager(pr, record):
            return False
        stopped = self._run(["kill", "-TERM", str(record.pid)],
                            check=False, capture_output=True, text=True)
        if stopped.returncode != 0:
            log.warning("Could not stop the agent manager for %s (pid %d): %s",
                        pr, record.pid, stopped.stderr.strip())
            return False
        log.info("Stopped the agent manager for %s (pid %d)", pr, record.pid)
        return True

    def open(self, pr: Pr, worktree: Path) -> None:
        start(worktree, pr)
        self._start(pr, str(worktree))

    def revive(self, pr: Pr) -> None:
        record = self._record(pr)
        if record is None or self._runs_manager(pr, record):
            return
        log.info("Restarting the exited agent manager for %s", pr)
        self._start(pr, record.worktree)

    def manager(self, pr: Pr) -> ManagerPane:
        if not self._record_file(pr).exists():
            return ManagerPane.NO_WINDOW
        record = self._record(pr)
        if record is None:
            return ManagerPane.UNREADABLE
        return ManagerPane.RUNNING if self._runs_manager(pr, record) else ManagerPane.EXITED

    def stop_managers(self) -> list[Pr]:
        stopped = []
        for pr in tracked_prs(self._places.manager_records_dir, RECORD):
            record = self._record(pr)
            if record is not None and self._stop(pr, record):
                stopped.append(pr)
        return stopped

    def manager_path(self, pr: Pr) -> str | None:
        record = self._record(pr)
        return None if record is None else record.worktree

    def _forget(self, pr: Pr) -> bool:
        self._terminals.of(pr).hang_up()
        record_file = self._record_file(pr)
        if not record_file.exists():
            return False
        record = self._record(pr)
        if record is not None:
            self._stop(pr, record)
        record_file.unlink(missing_ok=True)
        return True

    def detach(self, pr: Pr) -> str | None:
        if not self._forget(pr):
            return None
        defunct = defunct_name(pr)
        log.error("Detached the agent manager for %s as %s", pr, defunct)
        return defunct

    def close(self, pr: Pr) -> bool:
        if self._forget(pr):
            log.info("Closed the agent manager for %s", pr)
        return True

    def split(self, pr: Pr, worktree: str, argv: list[str]) -> str | None:
        try:
            self._terminals.of(pr).start(worktree, argv)
        except OSError as exc:
            log.warning("Could not start a terminal session for %s in %s: %s", pr, worktree, exc)
            return str(exc)
        return None

    def close_other_repos(self, keep: Set[Repo]) -> dict[Pr, str | None]:
        closing = {pr: self.manager_path(pr)
                   for pr in tracked_prs(self._places.manager_records_dir, RECORD)
                   if pr.repo not in keep}
        return {pr: worktree for pr, worktree in closing.items() if self._forget(pr)}
