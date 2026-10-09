import argparse
import os
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from github_orchestrator.server._config import ServerConfig
from github_orchestrator.server._supervisor import serve
from github_orchestrator.server._worker import Worker
from github_orchestrator.settings import Logs, Process
from github_orchestrator.wiring import make_container


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve the hub and every held pull request's board on the hub's port.")
    parser.add_argument("--port", type=int, help="serve this port instead of the config's hub_port")
    parser.add_argument("--files-in", type=Path,
                        help="keep server.lock, server.pid and server.log here instead of "
                             "the data directory")
    args = parser.parse_args(argv)
    own: Path | None = args.files_in
    container = make_container(os.environ, Path.home(), logs_dir=own)
    container.get(Logs).configure_logging(Process.SERVER)
    config = container.get(ServerConfig)
    if args.port is not None:
        config = replace(config, port=args.port)
    if own is not None:
        config = replace(config, lock=own / config.lock.name, pid=own / config.pid.name)
    return serve(config, Worker(port=config.port, pid=os.getpid(), logs_dir=own))


if __name__ == "__main__":
    sys.exit(main())
