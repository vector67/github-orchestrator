import fcntl
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol

from github_orchestrator.cli._config import CliConfig, OpenTerminals, Run
from github_orchestrator.cli._doctor import InstanceChecks
from github_orchestrator.cli._migrate import migrate
from github_orchestrator.cli._restart import confirm_restart, restart, restart_watcher
from github_orchestrator.cli._service import Service
from github_orchestrator.domain import HubState, LocalClock, Sleep
from github_orchestrator.pr_event_queue import Queues
from github_orchestrator.pr_processes import PrProcesses
from github_orchestrator.settings import ConfigFile
from github_orchestrator.watcher import WatcherHealth

LOCK_POLL_SECONDS = 2.0


@dataclass(frozen=True)
class Instance:
    name: str | None
    pr_processes: PrProcesses
    queues: Queues
    watcher_health: WatcherHealth
    terminals: OpenTerminals
    service: Service
    checks: InstanceChecks
    config_file: ConfigFile
    data_dir: Path


class OtherInstances(Protocol):
    def load(self) -> list[Instance]: ...


def _holder(lock: IO[str]) -> str:
    lock.seek(0)
    try:
        held = json.loads(lock.read())
        return f"the restart started at {held['started']} by pid {held['pid']}"
    except (json.JSONDecodeError, KeyError, TypeError):
        return "another restart"


def _take(lock: IO[str], sleep: Sleep) -> None:
    announced = False
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if not announced:
                print(f"Waiting for {_holder(lock)} to finish; "
                      "then this run does its own full restart.", flush=True)
                announced = True
            sleep(LOCK_POLL_SECONDS)


def _heading(text: str) -> None:
    print(f"==> {text}", flush=True)


def _named(instance: Instance) -> str:
    return "" if instance.name is None else f" for {instance.name}"


def _restart_instance(sleep: Sleep, clock: LocalClock, instance: Instance) -> None:
    named = _named(instance)
    _heading(f"Restarting the agent managers{named}")
    restarted = clock()
    stopped = restart(instance.pr_processes)
    _heading(f"Restarting the watcher{named}")
    restart_watcher(instance.service)
    _heading(f"Confirming the agent managers came back{named}")
    state = instance.config_file.state()
    if state is not HubState.WATCHING:
        print(f"The watcher is back in {state}; it polls nothing until its config is complete.")
        return
    confirm_restart(restarted, stopped, clock, sleep, queues=instance.queues,
                    pr_processes=instance.pr_processes, watcher_health=instance.watcher_health)


def restart_instances(config: CliConfig, sleep: Sleep, clock: LocalClock, run: Run,
                      instances: list[Instance]) -> None:
    config.restart_lock.parent.mkdir(parents=True, exist_ok=True)
    with open(config.restart_lock, "a+") as lock:
        _take(lock, sleep)
        lock.truncate(0)
        lock.write(json.dumps({"pid": os.getpid(),
                               "started": clock().isoformat(timespec="seconds")}))
        lock.flush()
        for instance in instances:
            migrate(instance.config_file, run, f"Migrating the config{_named(instance)}")
        for instance in instances:
            _restart_instance(sleep, clock, instance)
