import fcntl
import logging
import os
import socket
from collections.abc import Callable
from pathlib import Path

import uvicorn
from starlette.types import ASGIApp
from uvicorn.supervisors import Multiprocess

from github_orchestrator.server._config import ServerConfig

log = logging.getLogger(__name__)

GRACE_SECONDS = 1


def _bound(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
        sock.listen()
    except OSError:
        sock.close()
        raise
    return sock


def _write_pid(path: Path) -> None:
    written = path.with_name(f".{path.name}.{os.getpid()}")
    written.write_text(f"{os.getpid()}\n")
    os.replace(written, path)


def serve(config: ServerConfig, worker: Callable[[], ASGIApp]) -> int:
    config.lock.parent.mkdir(parents=True, exist_ok=True)
    with open(config.lock, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log.error("another server holds %s, so this one leaves", config.lock)
            return 1
        try:
            sock = _bound(config.port)
        except OSError as error:
            log.error("port %d is taken (%s), so the server leaves", config.port, error)
            return 1
        with sock:
            _write_pid(config.pid)
            log.info("server %d serving 127.0.0.1:%d with %d workers", os.getpid(), config.port,
                     config.workers)
            Multiprocess(uvicorn.Config(
                worker, factory=True, workers=config.workers, log_config=None,
                access_log=False, lifespan="off", proxy_headers=False,
                timeout_graceful_shutdown=GRACE_SECONDS), [sock]).run()
        log.info("server %d stopped", os.getpid())
        return 0
