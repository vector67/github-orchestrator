import argparse
import logging
import os
import sys
from pathlib import Path

from github_orchestrator.domain import HubState
from github_orchestrator.settings import ConfigFile, Dismissals, Logs, Process
from github_orchestrator.thread_names import HeldFolder, NameMigration
from github_orchestrator.watcher import Watcher
from github_orchestrator.wiring import make_container

log = logging.getLogger(__name__)


def in_the_way(held: list[HeldFolder]) -> str:
    return "; ".join(f"a terminal session is in {one.folder}, the folder of {one.pr}'s thread "
                     f"{one.thread}" for one in held)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "GitHub PR watcher: polls open PRs, diffs state, and enqueues events "
            "for each PR's agent manager, its board and the notifications."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Poll and diff state but do not enqueue events, save state, or start "
            "agent managers. Prints what would happen to stdout."
        ),
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help=(
            "Run continuously as a resident daemon, polling every "
            "watcher_poll_interval seconds (how the LaunchAgent and the systemd "
            "unit run it). Without it, run one cycle and exit."
        ),
    )
    args = parser.parse_args()

    container = make_container(os.environ, Path.home(), dry_run=args.dry_run)
    logs = container.get(Logs)
    logs.configure_logging(Process.WATCHER)
    config_file = container.get(ConfigFile)
    state = config_file.state()
    if state is not HubState.WATCHING:
        problem = config_file.check()
        log.warning("nothing to poll in %s: %s", state, problem)
        if not args.loop:
            print(problem, file=sys.stderr)
            sys.exit(1)

    watcher = container.get(Watcher)
    if not args.dry_run and not watcher.take_lock():
        log.info("Another watcher instance is running, skipping")
        print("Another watcher instance is running, skipping")
        sys.exit(0)

    if not args.dry_run:
        container.get(Dismissals).migrate()
    migration = container.get(NameMigration)
    held = migration.migrate() if not args.dry_run and state is HubState.WATCHING else []
    if held:
        log.warning("waiting to migrate thread names: %s", in_the_way(held))
    if held and not args.loop:
        print(f"The thread names cannot migrate yet: {in_the_way(held)}", file=sys.stderr)
        sys.exit(1)

    if args.loop:
        try:
            if state is HubState.WATCHING:
                if held:
                    watcher.wait_to_migrate(lambda: bool(migration.migrate()))
                watcher.run_forever()
            else:
                watcher.wait_in(state, config_file.state)
        except KeyboardInterrupt:
            pass
        return

    try:
        watcher.run_cycle()
    except Exception as exc:
        print(f"Watcher failed: {exc}", file=sys.stderr)
        print(f"Details in {logs.path(Process.WATCHER)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
