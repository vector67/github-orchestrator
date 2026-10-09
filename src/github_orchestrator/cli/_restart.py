import datetime
import sys

from github_orchestrator.cli._service import Service
from github_orchestrator.domain import LocalClock, Pr, Sleep
from github_orchestrator.pr_event_queue import Queues
from github_orchestrator.pr_processes import ManagerPane, PrProcesses
from github_orchestrator.watcher import Health, WatcherHealth

WATCHER_ATTEMPTS = 450
MANAGER_ATTEMPTS = 60
POLL_SECONDS = 2.0


def _polled_since(restarted: datetime.datetime, health: Health, now: datetime.datetime) -> bool:
    return health.since_last_poll is not None and now - health.since_last_poll >= restarted


def _await_watcher(restarted: datetime.datetime, watcher_health: WatcherHealth, clock: LocalClock,
                   sleep: Sleep) -> Health | None:
    for attempt in range(WATCHER_ATTEMPTS):
        health = watcher_health.health()
        if _polled_since(restarted, health, clock()):
            return None
        if attempt == 0:
            print("Waiting for the watcher to finish its first poll since the restart.", flush=True)
        if attempt < WATCHER_ATTEMPTS - 1:
            sleep(POLL_SECONDS)
    return health


def _await_managers(expected: set[Pr], pr_processes: PrProcesses, sleep: Sleep, *,
                    attempts: int) -> set[Pr]:
    waiting_on: set[Pr] = set()
    for attempt in range(attempts):
        missing = {pr for pr in expected if pr_processes.manager(pr) is not ManagerPane.RUNNING}
        if not missing:
            return missing
        if attempts > 1 and missing != waiting_on:
            named = ", ".join(str(pr) for pr in sorted(missing))
            print(f"The watcher has polled; waiting for {len(missing)} agent manager(s) "
                  f"to come back: {named}.", flush=True)
            waiting_on = missing
        if attempt < attempts - 1:
            sleep(POLL_SECONDS)
    return missing


def restart(pr_processes: PrProcesses) -> set[Pr]:
    stopped = pr_processes.stop_managers()
    if stopped:
        print("Killed agent manager processes. Watcher will restart them within 1 minute.")
    else:
        print("No agent manager processes running.")
    return set(stopped)


def confirm_restart(restarted: datetime.datetime, expected: set[Pr], clock: LocalClock, sleep: Sleep,
                    *, queues: Queues, pr_processes: PrProcesses,
                    watcher_health: WatcherHealth) -> None:
    unpolled = _await_watcher(restarted, watcher_health, clock, sleep)
    if unpolled is not None:
        failed = (f"; its last cycle failed: {unpolled.last_error}"
                  if unpolled.last_error is not None else ".")
        print(f"The watcher has not finished a poll since the restart{failed}")
    missing = _await_managers(expected, pr_processes, sleep,
                              attempts=1 if unpolled is not None else MANAGER_ATTEMPTS)
    failures = queues.failed_since(restarted)

    for pr in sorted(missing):
        print(f"Agent manager for {pr} did not come back.")
    for failure in failures:
        event_type = failure.event.kind if failure.event is not None else "?"
        queued = failure.queued_at.isoformat(timespec="seconds")
        print(f"Event failed since the restart: {failure.pr} {event_type} (queued {queued})")
    if unpolled is not None or missing or failures:
        sys.exit(1)
    print(f"{len(expected)} agent manager(s) back up; no event has failed since the restart.")


def restart_watcher(service: Service) -> None:
    service.start()
    print("Restarted the watcher daemon. Agent managers were left running.")
