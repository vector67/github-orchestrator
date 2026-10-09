import logging
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from types import FrameType

from github_orchestrator.board_api import BoardApi
from github_orchestrator.domain import Sleep
from github_orchestrator.pr_manager._commands import ManagerCommands
from github_orchestrator.pr_manager._config import ManagerConfig

log = logging.getLogger(__name__)


def _terminate_on_sigterm(signum: int, _frame: FrameType | None) -> None:
    raise SystemExit(f"terminated by signal {signum}")


class BrowserFront:
    def __init__(self, config: ManagerConfig, board: BoardApi, commands: ManagerCommands,
                 sleep: Sleep) -> None:
        self._pr = config.pr
        self._board = board
        self._commands = commands
        self._sleep = sleep
        self._board_held_back: str | None = None

    @contextmanager
    def session(self) -> Iterator[None]:
        previous_handler = None
        try:
            previous_handler = signal.signal(signal.SIGTERM, _terminate_on_sigterm)
        except ValueError:
            log.warning("Not the main thread; SIGTERM will not record the run's end")
        try:
            yield
        finally:
            if previous_handler is not None:
                signal.signal(signal.SIGTERM, previous_handler)

    def serve_board(self) -> None:
        pr = self._pr
        if self._board.is_running():
            return
        try:
            url = self._commands.start_board()
        except OSError:
            self._hold_board_back("would not start", logging.ERROR,
                                  "loop %s: the board will not start; trying again each tick",
                                  pr, exc_info=True)
            return
        if url is None:
            self._hold_board_back("unknown owner", logging.INFO,
                                  "loop %s: the board waits for a poll to say whose PR this is", pr)
            return
        self._board_held_back = None
        log.info("loop %s: board at %s", pr, url)

    def wait(self, timeout: float) -> None:
        self._sleep(timeout)

    def _hold_board_back(self, reason: str, level: int, message: str, *args: object,
                         exc_info: bool = False) -> None:
        if self._board_held_back == reason:
            level = logging.DEBUG
        self._board_held_back = reason
        log.log(level, message, *args, exc_info=exc_info)
