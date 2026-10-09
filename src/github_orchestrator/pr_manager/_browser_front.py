import logging
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from types import FrameType

from github_orchestrator.domain import Sleep

log = logging.getLogger(__name__)


def _terminate_on_sigterm(signum: int, _frame: FrameType | None) -> None:
    raise SystemExit(f"terminated by signal {signum}")


class BrowserFront:
    def __init__(self, sleep: Sleep) -> None:
        self._sleep = sleep

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

    def wait(self, timeout: float) -> None:
        self._sleep(timeout)
