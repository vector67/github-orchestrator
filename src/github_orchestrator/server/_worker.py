import logging
import os
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from starlette.types import ASGIApp

from github_orchestrator.board_api.interface import ServerApp
from github_orchestrator.settings import Logs, Process
from github_orchestrator.wiring import make_container

log = logging.getLogger(__name__)

ORPHAN_CHECK_SECONDS = 1.0


def _leave_once_orphaned(supervisor: int) -> None:
    while os.getppid() == supervisor:
        time.sleep(ORPHAN_CHECK_SECONDS)
    log.error("worker %d lost its server %d, so it leaves", os.getpid(), supervisor)
    os.kill(os.getpid(), signal.SIGTERM)


@dataclass(frozen=True)
class Worker:
    port: int
    pid: int
    logs_dir: Path | None

    def __call__(self) -> ASGIApp:
        container = make_container(os.environ, Path.home(), logs_dir=self.logs_dir)
        container.get(Logs).configure_logging(Process.SERVER)
        threading.Thread(target=_leave_once_orphaned, args=(self.pid,), daemon=True,
                         name="orphan-check").start()
        server: ServerApp = container.get(ServerApp)
        return server.app(self.port, self.pid)
