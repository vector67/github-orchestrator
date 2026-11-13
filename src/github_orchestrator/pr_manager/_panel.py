import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from github_orchestrator.agent_runs import History, PrWork
from github_orchestrator.board_api import Dashboard, ManagerPanel, ManagerWorktree
from github_orchestrator.board_api.interface import ManagerRefusal
from github_orchestrator.change_detection import ChangeDetection, CiFailed
from github_orchestrator.domain import DismissUntil, Monotonic, Pr
from github_orchestrator.pr_manager._command_file import Command, CommandFiles
from github_orchestrator.pr_manager._dashboard_source import ConfigOf, DashboardSource
from github_orchestrator.pr_manager._files import locked
from github_orchestrator.pr_manager._git_palette import (
    SHELL,
    argv_for,
    open_in_terminal,
    resolve,
    run_captured,
)
from github_orchestrator.pr_manager._git_palette import Run as GitRun
from github_orchestrator.pr_manager._refusals import refusal
from github_orchestrator.pr_manager._status import StatusFiles
from github_orchestrator.pr_processes import AgentChanges, PrProcesses, shell_argv

log = logging.getLogger(__name__)

SHOWN_READ_ONLY = frozenset({"l", "d"})

_DISMISS_COMMANDS = {
    DismissUntil.NEXT_EVENT: Command.DISMISS_UNTIL_NEXT_EVENT,
    DismissUntil.READY_FOR_REVIEW: Command.DISMISS_UNTIL_READY_FOR_REVIEW,
    DismissUntil.FOREVER: Command.DISMISS_FOREVER,
}


class FilePanel(ManagerPanel, ManagerWorktree):
    def __init__(self, pr: Pr, worktree: Callable[[], str], *, agents_enabled: bool,
                 run: GitRun, monotonic: Monotonic, status_files: StatusFiles,
                 command_files: CommandFiles, dashboards: DashboardSource,
                 agent_changes: AgentChanges, history: History, pr_processes: PrProcesses,
                 pr_work: PrWork, change_detection: ChangeDetection) -> None:
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
        self._change_detection = change_detection

    def _yours(self) -> bool:
        facts = self._change_detection.facts(self._pr)
        return facts is not None and facts.is_author is True

    def dashboard(self) -> Dashboard:
        return self._dashboards.dashboard(self._pr)

    def changes(self) -> str | None:
        return self._agent_changes.read(Path(self._worktree()))

    def agent_output(self, lines: int) -> list[tuple[str, bool]]:
        return self._history.transcript_tail(self._pr, lines)

    def set_on_hold(self, on_hold: bool) -> ManagerRefusal | None:
        return self._hand(Command.HOLD if on_hold else Command.RESUME)

    def carry_on(self) -> ManagerRefusal | None:
        return self._hand(Command.CARRY_ON, pushes=self._last_run_fixed_ci())

    def _last_run_fixed_ci(self) -> bool:
        last = self._history.last_run(self._pr)
        return last is not None and last.event_type == CiFailed.kind

    def start_review(self) -> ManagerRefusal | None:
        return self._hand(Command.START_REVIEW)

    def dismiss(self, until: DismissUntil) -> ManagerRefusal | None:
        return self._hand(_DISMISS_COMMANDS[until])

    def close(self) -> ManagerRefusal | None:
        return self._hand(Command.CLOSE)

    def reopen(self) -> ManagerRefusal | None:
        return self._hand(Command.REOPEN)

    def mark_ready(self) -> ManagerRefusal | None:
        return self._hand(Command.MARK_READY)

    def convert_to_draft(self) -> ManagerRefusal | None:
        return self._hand(Command.CONVERT_TO_DRAFT)

    def assign_reviewers(self, reviewers: Sequence[str], detailed: str | None) -> ManagerRefusal | None:
        return self._hand(Command.ASSIGN_REVIEWERS,
                          {"reviewers": list(reviewers), "detailed": detailed})

    def assign_when_ready(self, reviewers: Sequence[str], detailed: str | None) -> ManagerRefusal | None:
        return self._hand(Command.ASSIGN_WHEN_READY,
                          {"reviewers": list(reviewers), "detailed": detailed})

    def take_over(self) -> ManagerRefusal | None:
        return self._hand(Command.TAKE_OVER, pushes=True)

    def hand_back(self) -> ManagerRefusal | None:
        return self._hand(Command.HAND_BACK)

    def answer_agent_settings(self, digest: str, *, allowed: bool) -> bool:
        answered = self._dashboards.answer_agent_settings(self._pr, self._worktree(), digest,
                                                          allowed=allowed)
        log.info("%s: agent settings %s — %s", self._pr, digest[:12],
                 ("allowed" if allowed else "run without them") if answered
                 else "refused, they changed since the page showed them")
        return answered

    def run_git(self, keys: str) -> tuple[int, list[str], float] | ManagerRefusal:
        command = resolve(keys)
        if command is None or (command.mode != "captured" and command.keys not in SHOWN_READ_ONLY):
            raise ValueError(f"git palette keys {keys!r} name no command the page runs")
        worktree = self._worktree()
        if not worktree:
            return ManagerRefusal.NO_WORKTREE
        with locked(Path(f"{worktree}.git-palette.lock")):
            refused = self._refusal(command.display, pushes=command.pushes)
            if refused is not None:
                return refused
            log.info("%s: git palette running %s", self._pr, command.display)
            result = run_captured(command, argv_for(command, keys), worktree,
                                  self._run, self._monotonic)
        return result.exit_code, result.lines, result.duration

    def open_terminal(self, keys: str) -> ManagerRefusal | str | None:
        pr, worktree = self._pr, self._worktree()
        command = resolve(keys)
        if keys != SHELL and (command is None or command.mode == "captured"):
            raise ValueError(f"terminal keys {keys!r} name nothing the terminal opens")
        if not worktree:
            return ManagerRefusal.NO_WORKTREE
        refused = self._refusal(f"a terminal for {keys!r}",
                                starts_an_agent=command is not None and command.mode == "agent")
        if refused is not None:
            return refused
        log.info("%s: opening %r in a terminal", pr, keys)
        if command is None:
            return self._pr_processes.split(pr, worktree, shell_argv())
        return open_in_terminal(command, argv_for(command, keys), pr, worktree,
                                self._pr_processes, self._pr_work, yours=self._yours())

    def ask(self, prompt: str) -> ManagerRefusal | str | None:
        worktree = self._worktree()
        if not worktree:
            return ManagerRefusal.NO_WORKTREE
        refused = self._refusal("a question for the agent", starts_an_agent=True)
        if refused is not None:
            return refused
        log.info("%s: asking the agent in a terminal", self._pr)
        return self._pr_work.ask_in_session(self._pr, worktree, prompt, yours=self._yours())

    def _refusal(self, what: str, command: Command | None = None, *,
                 pushes: bool = False, starts_an_agent: bool = False) -> ManagerRefusal | None:
        refused = refusal(self._status_files.conditions(self._pr), command,
                          agents_enabled=self._agents_enabled, pushes=pushes,
                          starts_an_agent=starts_an_agent)
        if refused is not None:
            log.info("%s: %s refused — %s", self._pr, what, refused)
        return refused

    def _hand(self, command: Command, fields: dict[str, Any] | None = None, *,
              pushes: bool = False) -> ManagerRefusal | None:
        refused = self._refusal(command, command, pushes=pushes)
        if refused is None:
            self._command_files.write(self._pr, command, fields or {})
        return refused


class FilePanels:
    def __init__(self, config_of: ConfigOf, run: GitRun, monotonic: Monotonic, *,
                 status_files: StatusFiles, command_files: CommandFiles,
                 dashboards: DashboardSource, agent_changes: AgentChanges, history: History,
                 pr_processes: PrProcesses, pr_work: PrWork,
                 change_detection: ChangeDetection) -> None:
        self._config_of = config_of
        self._run = run
        self._monotonic = monotonic
        self._status_files = status_files
        self._command_files = command_files
        self._dashboards = dashboards
        self._agent_changes = agent_changes
        self._history = history
        self._pr_processes = pr_processes
        self._pr_work = pr_work
        self._change_detection = change_detection

    def of(self, pr: Pr) -> ManagerPanel:
        return self._panel(pr)

    def worktree(self, pr: Pr) -> ManagerWorktree:
        return self._panel(pr)

    def _panel(self, pr: Pr) -> FilePanel:
        return FilePanel(pr, lambda: self._pr_processes.manager_path(pr) or "",
                         agents_enabled=self._config_of(pr, "").agents_enabled, run=self._run,
                         monotonic=self._monotonic, status_files=self._status_files,
                         command_files=self._command_files, dashboards=self._dashboards,
                         agent_changes=self._agent_changes, history=self._history,
                         pr_processes=self._pr_processes, pr_work=self._pr_work,
                         change_detection=self._change_detection)
