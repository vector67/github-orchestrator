import logging
from pathlib import Path

from github_orchestrator.agent_runs import History, PrWork, Run
from github_orchestrator.board_api import BoardApi, Dashboard, ManagerPanel
from github_orchestrator.change_detection import ChangeDetection, ReviewRequested
from github_orchestrator.domain import Monotonic
from github_orchestrator.github import PullRequests
from github_orchestrator.pr_event_queue import Intake, Worklist
from github_orchestrator.pr_manager._command_file import Command, CommandFiles
from github_orchestrator.pr_manager._config import ManagerConfig
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
from github_orchestrator.pr_manager._refusals import Conditions, refusal
from github_orchestrator.pr_manager._status import StatusFiles
from github_orchestrator.pr_processes import AgentChanges, PrProcesses
from github_orchestrator.settings import Boards, Dismissals, Holds

log = logging.getLogger(__name__)

NOTICE_SECONDS = 4.0

SHOWN_READ_ONLY = frozenset({"l", "d"})


class ManagerCommands(ManagerPanel):
    def __init__(self, config: ManagerConfig, board: BoardApi, run: GitRun,
                 monotonic: Monotonic, *, holds: Holds, dismissals: Dismissals,
                 boards: Boards, worklist: Worklist,
                 pull_requests: PullRequests, pr_work: PrWork, pr_processes: PrProcesses,
                 agent_changes: AgentChanges, history: History,
                 change_detection: ChangeDetection, intake: Intake,
                 status_files: StatusFiles, command_files: CommandFiles,
                 dashboards: DashboardSource) -> None:
        self._config = config
        self._board = board
        self._run = run
        self._monotonic = monotonic
        self._holds = holds
        self._dismissals = dismissals
        self._boards = boards
        self._worklist = worklist
        self._pull_requests = pull_requests
        self._pr_work = pr_work
        self._pr_processes = pr_processes
        self._agent_changes = agent_changes
        self._history = history
        self._change_detection = change_detection
        self._intake = intake
        self._status_files = status_files
        self._command_files = command_files
        self._dashboards = dashboards
        self.active_run: Run | None = None
        self._dismissed = False
        self._notice: str | None = None
        self._notice_at = 0.0

    def obey(self, *, frozen: bool) -> None:
        for pending in self._command_files.pending(self._config.pr):
            self.carry_out(pending.command, frozen=frozen)
            self._command_files.delete(pending)

    def carry_out(self, command: Command, *, frozen: bool) -> None:
        pr = self._config.pr
        if self._dismissed:
            log.info("%s: %s dropped — the manager is leaving", pr, command)
            return
        log.info("%s: %s", pr, command)
        run = self.active_run
        refused = refusal(Conditions(frozen=frozen, running=run is not None and run.is_alive()),
                          command, agents_enabled=self._config.agents_enabled)
        if refused is not None:
            log.info("%s: %s refused — %s", pr, command, refused)
            self.notify(refused)
            return
        try:
            self._act(command)
        except Exception:
            log.exception("Error carrying out %s for %s", command, pr)

    @property
    def dismissed(self) -> bool:
        return self._dismissed

    def notify(self, text: str) -> None:
        self._notice = text
        self._notice_at = self._monotonic()

    def notice(self) -> str | None:
        if self._notice is None:
            return None
        if self._monotonic() - self._notice_at >= NOTICE_SECONDS:
            self._notice = None
            return None
        return self._notice

    def dashboard(self) -> Dashboard:
        return self._dashboards.dashboard(self._config.pr)

    def changes(self) -> str | None:
        return self._agent_changes.read(Path(self._config.worktree))

    def agent_output(self, lines: int) -> list[tuple[str, bool]]:
        return self._history.transcript_tail(self._config.pr, lines)

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
        with locked(Path(f"{self._config.worktree}.git-palette.lock")):
            refused = self._refusal(command.display)
            if refused is not None:
                return -1, [refused], 0.0
            log.info("%s: git palette running %s", self._config.pr, command.display)
            result = run_captured(command, argv_for(command, keys), self._config.worktree,
                                  self._run, self._monotonic)
        return result.exit_code, result.lines, result.duration

    def open_terminal(self, keys: str) -> str | None:
        config = self._config
        pr, worktree = config.pr, config.worktree
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

    def start_board(self) -> str | None:
        pr = self._config.pr
        facts = self._change_detection.facts(pr)
        if facts is None or facts.is_author is None:
            return None
        url = self._board.start(pr, port=self._boards.board_port(pr), manager=self)
        self._boards.want_board(pr, True)
        return url

    def _refusal(self, what: str, command: Command | None = None) -> str | None:
        config = self._config
        refused = refusal(self._status_files.conditions(config.pr), command,
                          agents_enabled=config.agents_enabled)
        if refused is not None:
            log.info("%s: %s refused — %s", config.pr, what, refused)
        return refused

    def _hand(self, command: Command) -> str | None:
        refused = self._refusal(command, command)
        if refused is None:
            self._command_files.write(self._config.pr, command)
        return refused

    def _act(self, command: Command) -> None:
        match command:
            case Command.HOLD:
                self._set_on_hold(True)
            case Command.RESUME:
                self._set_on_hold(False)
            case Command.CARRY_ON:
                self._carry_on()
            case Command.START_REVIEW:
                self._start_review()
            case Command.DISMISS_UNTIL_NEXT_EVENT:
                self._dismiss(False)
            case Command.DISMISS_FOREVER:
                self._dismiss(True)
            case Command.CLOSE:
                self._close()

    def _set_on_hold(self, on_hold: bool) -> None:
        pr = self._config.pr
        self._holds.set_on_hold(pr, on_hold)
        log.info("%s: hold %s", pr, "ON" if on_hold else "OFF")

    def _start_review(self) -> None:
        pr = self._config.pr
        facts = self._change_detection.facts(pr)
        log.info("start review %s: queuing a review request", pr)
        self._intake.add(pr, ReviewRequested(title=facts.title if facts else None,
                                             url=facts.url if facts else None))

    def _carry_on(self) -> None:
        config = self._config
        pr = config.pr
        log.info("carry on %s: carrying on the last agent run", pr)
        started = self._pr_work.carry_on(config.worktree, pr)
        if isinstance(started, str):
            self.notify(started)
            return
        self.active_run = started

    def _dismiss(self, forever: bool) -> None:
        pr = self._config.pr
        if forever:
            self._dismissals.dismiss_forever(pr)
        else:
            self._dismissals.dismiss_until_next_event(pr)
        if self.active_run is not None:
            self.active_run.terminate()
        self._worklist.drop_in_flight(pr)
        log.info("Dismissed %s %s — exiting; the watcher closes its window",
                 "forever" if forever else "until the next event", pr)
        self._dismissed = True

    def _close(self) -> None:
        pr = self._config.pr
        refused = self._pull_requests.close(pr)
        if refused is not None:
            log.warning("close %s: GitHub refused — %s", pr, refused)
            self.notify(refused)
            return
        log.info("Closed %s on GitHub; the watcher tears it down on its next poll", pr)
