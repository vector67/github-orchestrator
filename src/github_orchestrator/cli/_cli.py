import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from github_orchestrator.agent_runs import History
from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.cli._config import (
    CliConfig,
    OpenTerminals,
    Run,
    Which,
)
from github_orchestrator.cli._doctor import InstanceChecks, MachineChecks, report
from github_orchestrator.cli._hub import HubHealth
from github_orchestrator.cli._migrate import (
    drop_cron_block,
    migrate,
    move_old_config,
    old_config,
)
from github_orchestrator.cli._parser import Commands
from github_orchestrator.cli._restart_all import (
    Instance,
    OtherInstances,
    restart_instances,
)
from github_orchestrator.cli._runs import logs, runs
from github_orchestrator.cli._service import Service, launchd_label
from github_orchestrator.cli._setup import ReadLine, setup, show_config
from github_orchestrator.cli._skill import skill
from github_orchestrator.cli._start import (
    await_hub,
    hub_line,
    open_board,
    start,
    start_in_foreground,
)
from github_orchestrator.cli._status import queue, status, undismiss
from github_orchestrator.cli._stop import stop
from github_orchestrator.cli._threads import THREAD_COMMANDS
from github_orchestrator.cli._tutorial import tutorial
from github_orchestrator.cli._uninstall import uninstall
from github_orchestrator.cli._update import update
from github_orchestrator.conversation import ConversationManagerFactory
from github_orchestrator.desktop import Desktop
from github_orchestrator.domain import LocalClock, Pr, Sleep
from github_orchestrator.pr_event_queue import Queues
from github_orchestrator.pr_processes import PrProcesses
from github_orchestrator.settings import (
    ConfigFile,
    Dismissals,
    Holds,
    Logs,
)
from github_orchestrator.watcher import Releases, WatcherHealth


class OperatorCli:
    def __init__(self, config: CliConfig, run: Run, sleep: Sleep, clock: LocalClock,
                 read_line: ReadLine, which: Which, *, config_file: ConfigFile, logs: Logs,
                 desktop: Desktop, queues: Queues, history: History,
                 pr_processes: PrProcesses,
                 conversation_managers: ConversationManagerFactory, change_detection: ChangeDetection,
                 watcher_health: WatcherHealth, hub_health: HubHealth, holds: Holds,
                 dismissals: Dismissals, others: OtherInstances,
                 terminals: OpenTerminals, service: Service, checks: InstanceChecks,
                 machine: MachineChecks, releases: Releases) -> None:
        self._config = config
        self._run = run
        self._sleep = sleep
        self._clock = clock
        self._read_line = read_line
        self._which = which
        self._config_file = config_file
        self._logs = logs
        self._desktop = desktop
        self._queues = queues
        self._history = history
        self._pr_processes = pr_processes
        self._conversation_managers = conversation_managers
        self._change_detection = change_detection
        self._watcher_health = watcher_health
        self._hub_health = hub_health
        self._holds = holds
        self._dismissals = dismissals
        self._others = others
        self._terminals = terminals
        self._service = service
        self._checks = checks
        self._machine = machine
        self._releases = releases

    def main(self, argv: list[str]) -> int:
        self._argv = argv
        try:
            self._dispatch(argv)
        except SystemExit as exited:
            if exited.code is None:
                return 0
            return exited.code if isinstance(exited.code, int) else 1
        return 0

    def _this_instance(self) -> Instance:
        return Instance(self._config.instance, self._pr_processes,
                        self._queues, self._watcher_health, self._terminals, self._service,
                        self._checks, self._config_file, self._config.data_dir)

    def _every_instance(self) -> list[Instance]:
        return [self._this_instance(), *self._others.load()]

    def _start(self, args: argparse.Namespace) -> None:
        config = self._config
        if args.from_installer:
            self._start_from_installer()
            return
        migrate(self._config_file, self._run, "Migrating the config")
        if args.foreground:
            start_in_foreground(self._run, config.python, config.child_environment)
        else:
            start(self._service, config.hub_url, self._hub_health, self._sleep)

    def _start_from_installer(self) -> None:
        config = self._config
        moved = self._moved_old_config()
        if moved:
            sys.exit(self._run([config.python, "-m", "github_orchestrator.cli",
                                *self._argv]).returncode)
        instances = self._every_instance()
        for instance in instances:
            named = "" if instance.name is None else f" for {instance.name}"
            migrate(instance.config_file, self._run, f"Migrating the config{named}")
        if config.platform != "darwin":
            for line in drop_cron_block(self._run, config.config_folder / "crontab.bak"):
                print(line)
        for instance in instances:
            named = "the default instance" if instance.name is None else instance.name
            print(f"==> Starting the watcher for {named}", flush=True)
            instance.service.start(keep_old=True)
        print(hub_line(config.hub_url, await_hub(config.hub_url, self._hub_health, self._sleep)))

    def _moved_old_config(self) -> bool:
        config = self._config
        target = config.config_folder / "config.toml"
        old = old_config(config.home / "Library" / "LaunchAgents"
                         / f"{launchd_label(None)}.plist", self._run,
                         linux=config.platform != "darwin")
        here = Path(self._config_file.location())
        if config.instance is not None or here not in (target, old):
            return False
        moved, said = move_old_config(old, target)
        if said:
            print("==> Finding the config of an older install", flush=True)
            for line in said:
                print(line, flush=True)
        return moved

    def _open(self, page: str) -> None:
        open_board(self._service, self._config.hub_url, self._hub_health, self._sleep,
                   self._desktop, graphical=self._config.graphical, page=page)

    def _dispatch(self, argv: list[str]) -> None:
        config = self._config
        parsers = Commands(config.version)
        args = parsers.parser.parse_args(argv or ["help"])
        if args.command not in ("help", "config", "setup", "open", "tutorial", "doctor",
                                "status", "start", "restart", "restart-all", "uninstall",
                                "update", "skill"):
            problem = self._config_file.check()
            if problem is not None:
                print(problem, file=sys.stderr)
                sys.exit(2)
        if args.command == "thread" and args.thread_command is None:
            parsers.thread_parser.print_help()
            sys.exit(1)

        gist_model = config.summary_model if config.agents_enabled else None
        commands: dict[str, Callable[[argparse.Namespace], None]] = {
            "help": lambda a: parsers.help(a.topic),
            "status": lambda a: status(config, self._config_file, queues=self._queues,
                                       change_detection=self._change_detection,
                                       watcher_health=self._watcher_health,
                                       hub_health=self._hub_health,
                                       holds=self._holds, dismissals=self._dismissals,
                                       releases=self._releases),
            "config": lambda a: show_config(self._config_file),
            "doctor": lambda a: report([
                ("This machine", self._machine.findings()),
                *(("Default instance" if instance.name is None else f"Instance {instance.name}",
                   instance.checks.findings()) for instance in self._every_instance())]),
            "setup": lambda a: setup(config.hub_url, self._open),
            "skill": lambda a: skill(config.agent.skill_folder(config.home), status=a.status,
                                    replace=a.replace),
            "open": lambda a: self._open(""),
            "tutorial": lambda a: tutorial(config.hub_url, self._open, terminal=a.terminal,
                                          agent=config.agent.value,
                                          described=config.agent.described),
            "queue": lambda a: queue(a.pr, queues=self._queues),
            "logs": lambda a: logs(self._logs, self._service, self._run, a.which, a.lines,
                                   following=a.follow),
            "runs": lambda a: runs(config, self._config_file, self._clock(),
                                   history=self._history),
            "start": self._start,
            "restart": lambda a: restart_instances(config, self._sleep, self._clock, self._run,
                                                   [self._this_instance()]),
            "restart-all": lambda a: restart_instances(config, self._sleep, self._clock, self._run,
                                                       self._every_instance()),
            "stop": lambda a: stop(
                self._read_line,
                self._every_instance() if a.all else [self._this_instance()],
                force=a.force),
            "update": lambda a: update(config, self._run, self._which, self._releases,
                                       version=a.version, check=a.check),
            "uninstall": lambda a: uninstall(config, self._run, self._which, self._read_line,
                                             self._every_instance(), yes=a.yes),
            "undismiss": lambda a: undismiss(Pr(a.repo, a.pr),
                                             change_detection=self._change_detection,
                                             dismissals=self._dismissals),
            "thread": lambda a: THREAD_COMMANDS[a.thread_command](
                a, conversation_managers=self._conversation_managers, gist_model=gist_model),
        }
        commands[args.command](args)
