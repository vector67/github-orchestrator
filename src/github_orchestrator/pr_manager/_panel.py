import logging
from collections.abc import Callable
from pathlib import Path

from github_orchestrator.agent_runs import History, PrWork
from github_orchestrator.board_api import Dashboard, ManagerPanel
from github_orchestrator.domain import Monotonic, Pr
from github_orchestrator.pr_manager._command_file import Command, CommandFiles
from github_orchestrator.pr_manager._dashboard_source import DashboardSource
from github_orchestrator.pr_manager._files import locked
from github_orchestrator.pr_manager._git_palette import (
    SHELL,
    argv_for,
    open_in_terminal,
    resolve,
    run_captured,
    shell_argv,
)
from github_orchestrator.pr_manager._git_palette import Run as GitRun
from github_orchestrator.pr_manager._refusals import refusal
from github_orchestrator.pr_manager._status import StatusFiles
from github_orchestrator.pr_processes import AgentChanges, PrProcesses

log = logging.getLogger(__name__)

SHOWN_READ_ONLY = frozenset({"l", "d"})


class FilePanel(ManagerPanel):
    def __init__(self, pr: Pr, worktree: Callable[[], str], *, agents_enabled: bool,
                 run: GitRun, monotonic: Monotonic, status_files: StatusFiles,
                 command_files: CommandFiles, dashboards: DashboardSource,
                 agent_changes: AgentChanges, history: History, pr_processes: PrProcesses,
                 pr_work: PrWork) -> None:
        self._pr = pr
        self._worktree = worktree
        self._agents_enabled = agents_enabled
        self._run = run
        self._monotonic = monotonic
        self._status_files = status_files
        self._command_files = command_files
        self._dashboards = dashboards
        self._agent_changes = agent_changes
        self._history = history
        self._pr_processes = pr_processes
        self._pr_work = pr_work

    def dashboard(self) -> Dashboard:
        return self._dashboards.dashboard(self._pr)

    def changes(self) -> str | None:
        return self._agent_changes.read(Path(self._worktree()))

    def agent_output(self, lines: int) -> list[tuple[str, bool]]:
        return self._history.transcript_tail(self._pr, lines)

    def set_on_hold(self, on_hold: bool) -> str | None:
        return self._hand(Command.HOLD if on_hold else Command.RESUME)

    def carry_on(self) -> str | None:
        return self._hand(Command.CARRY_ON)

    def start_review(self) -> str | None:
        return self._hand(Command.START_REVIEW)

    def dismiss(self, forever: bool) -> str | None:
        return self._hand(Command.DISMISS_FOREVER if forever else Command.DISMISS_UNTIL_NEXT_EVENT)

    def close(self) -> str | None:
        return self._hand(Command.CLOSE)

    def run_git(self, keys: str) -> tuple[int, list[str], float]:
        command = resolve(keys)
        if command is None or (command.mode != "captured" and command.keys not in SHOWN_READ_ONLY):
            raise ValueError(f"git palette keys {keys!r} name no command the page runs")
        worktree = self._worktree()
        with locked(Path(f"{worktree}.git-palette.lock")):
            refused = self._refusal(command.display)
            if refused is not None:
                return -1, [refused], 0.0
            log.info("%s: git palette running %s", self._pr, command.display)
            result = run_captured(command, argv_for(command, keys), worktree,
                                  self._run, self._monotonic)
        return result.exit_code, result.lines, result.duration

    def open_terminal(self, keys: str) -> str | None:
        pr, worktree = self._pr, self._worktree()
        command = resolve(keys)
        if keys != SHELL and (command is None or command.mode == "captured"):
            raise ValueError(f"terminal keys {keys!r} name nothing the terminal opens")
        refused = self._refusal(f"a terminal for {keys!r}")
        if refused is not None:
            return refused
        log.info("%s: opening %r in a terminal", pr, keys)
        if command is None:
            return self._pr_processes.split(pr, worktree, shell_argv())
        return open_in_terminal(command, argv_for(command, keys), pr, worktree,
                                self._pr_processes, self._pr_work)

    def _refusal(self, what: str, command: Command | None = None) -> str | None:
        refused = refusal(self._status_files.conditions(self._pr), command,
                          agents_enabled=self._agents_enabled)
        if refused is not None:
            log.info("%s: %s refused — %s", self._pr, what, refused)
        return refused

    def _hand(self, command: Command) -> str | None:
        refused = self._refusal(command, command)
        if refused is None:
            self._command_files.write(self._pr, command)
        return refused
