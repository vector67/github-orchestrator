import os
from dataclasses import dataclass
from pathlib import Path

from starlette.types import ASGIApp

from github_orchestrator.board_api.interface import ServerApp
from github_orchestrator.settings import Logs, Process
from github_orchestrator.wiring import make_container


@dataclass(frozen=True)
class Worker:
    port: int
    pid: int
    logs_dir: Path | None

    def __call__(self) -> ASGIApp:
        container = make_container(os.environ, Path.home(), logs_dir=self.logs_dir)
        container.get(Logs).configure_logging(Process.SERVER)
        server: ServerApp = container.get(ServerApp)
        return server.app(self.port, self.pid)
