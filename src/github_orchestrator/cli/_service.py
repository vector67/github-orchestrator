import plistlib
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Protocol

from github_orchestrator.cli._config import CliConfig, Run
from github_orchestrator.cli._findings import Finding, fail, ok, warn
from github_orchestrator.cli._tail import follow, print_tail, tail_command
from github_orchestrator.domain import Sleep

LAUNCHD_LABEL = "com.github-orchestrator.watcher"
BOOTSTRAP_ATTEMPTS = 10
COMMAND_TIMEOUT = 30
LAUNCHCTL_PRINT_FIELDS = ("state", "program", "last exit code", "pid")
START_ATTEMPTS = 10
SYSTEMD_UNIT = "github-orchestrator"
UNIT_TEMPLATE = "github-orchestrator.service.template"
START = "github-orchestrator start"
RESTART = "github-orchestrator restart"
SHOWS_WHY = f"{RESTART}; github-orchestrator logs service shows why it stopped"
SYSTEMD_FACTS = ("ActiveState", "SubState", "ExecMainStatus", "MainPID", "NRestarts", "Result",
                 "ExecStart")


@dataclass(frozen=True)
class ServiceCheck:
    findings: list[Finding]
    path: str | None
    pid: int | None


class Service(Protocol):
    def start(self, *, keep_old: bool = False) -> None: ...

    def stop(self) -> None: ...

    def running(self) -> bool: ...

    def show_log(self, lines: int, *, following: bool = False) -> None: ...

    def check(self) -> ServiceCheck: ...

    def remove(self) -> None: ...


def _written(path: Path, definition: bytes, *, keep_old: bool) -> None:
    if keep_old and path.exists() and path.read_bytes() != definition:
        kept = path.with_name(f"{path.name}.bak")
        kept.write_bytes(path.read_bytes())
        print(f"Rewrote {path} for this release; the old one is {kept}.")
    path.write_bytes(definition)


def _pid(text: str) -> int | None:
    return int(text) if text.isdigit() and int(text) > 0 else None


def launchd_label(instance: str | None) -> str:
    if instance is None:
        return LAUNCHD_LABEL
    return f"{LAUNCHD_LABEL}.{instance}"


def _folders_once(path: str) -> str:
    kept: list[str] = []
    for entry in path.split(":"):
        if entry not in kept and Path(entry).is_absolute() and Path(entry).is_dir():
            kept.append(entry)
    return ":".join(kept)


def launchagent(*, label: str, python: str, path: str, environment: Mapping[str, str],
                log: Path) -> bytes:
    return plistlib.dumps({
        "Label": label,
        "ProgramArguments": [python, "-m", "github_orchestrator.watcher", "--loop"],
        "EnvironmentVariables": {"PATH": _folders_once(path), **environment},
        "KeepAlive": True,
        "ThrottleInterval": 1,
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    })


def _quoted(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{escaped}"'


def systemd_unit(*, description: str, python: str, path: str,
                 environment: Mapping[str, str]) -> str:
    variables = {"PATH": _folders_once(path), **environment}
    replacements = {
        "@DESCRIPTION@": description,
        "@PYTHON@": _quoted(python).replace("$", "$$"),
        "@ENVIRONMENT@": "\n".join(f"Environment={_quoted(f'{name}={value}')}"
                                   for name, value in variables.items()),
    }
    unit = (files(__package__) / "services" / UNIT_TEMPLATE).read_text()
    for placeholder, value in replacements.items():
        unit = unit.replace(placeholder, value)
    return unit


def _unquoted(value: str) -> str:
    if len(value) < 2 or value[0] != '"' or value[-1] != '"':
        return value
    out: list[str] = []
    chars = iter(value[1:-1])
    for char in chars:
        out.append(next(chars, "") if char in ("\\", "%") else char)
    return "".join(out)


def _unit_path(unit: str) -> str | None:
    for line in unit.splitlines():
        key, _, value = line.partition("=")
        name, _, setting = _unquoted(value).partition("=")
        if key == "Environment" and name == "PATH":
            return setting
    return None


def _plist_path(plist: Path) -> str | None:
    try:
        environment = plistlib.loads(plist.read_bytes()).get("EnvironmentVariables", {})
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None
    path = environment.get("PATH") if isinstance(environment, dict) else None
    return path if isinstance(path, str) else None


def _ran(run: Run, cmd: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        done: subprocess.CompletedProcess[str] = run(
            cmd, capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"{' '.join(cmd)} timed out after {COMMAND_TIMEOUT}s.")
        sys.exit(1)
    return done


def _ran_or_exit(run: Run, cmd: list[str], *, ignore_failure: bool = False) -> None:
    done = _ran(run, cmd)
    if done.returncode != 0 and not ignore_failure:
        print(f"{' '.join(cmd)} failed.")
        print(str(done.stderr).strip())
        sys.exit(1)


def _parse_launchctl_print(text: str) -> dict[str, str]:
    facts = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and key in LAUNCHCTL_PRINT_FIELDS and key not in facts:
            facts[key] = value.strip()
    return facts


def _not_running(facts: dict[str, str]) -> list[str]:
    lines = [
        "The watcher was reloaded but is not running.",
        f"  launchd state: {facts.get('state', 'unknown')}",
    ]
    if "last exit code" in facts:
        lines.append(f"  last exit code: {facts['last exit code']}")
    program = facts.get("program")
    if program and not Path(program).exists():
        lines.append(f"  program: {program} — this file does not exist")
        lines.append(
            "The LaunchAgent names a program that has moved or been uninstalled. "
            "Reinstall github-orchestrator, then run its restart again."
        )
    elif program:
        lines.append(f"  program: {program}")
    return lines


class LaunchdService:
    def __init__(self, run: Run, sleep: Sleep, *, uid: int, label: str, plist: Path,
                 log: Path, definition: Callable[[], bytes]) -> None:
        self._run = run
        self._log = log
        self._sleep = sleep
        self._domain = f"gui/{uid}"
        self._target = f"gui/{uid}/{label}"
        self._plist = plist
        self._definition = definition

    def start(self, *, keep_old: bool = False) -> None:
        self._plist.parent.mkdir(parents=True, exist_ok=True)
        _written(self._plist, self._definition(), keep_old=keep_old)
        self._launchctl_or_exit(["launchctl", "bootout", self._target], ignore_failure=True)
        self._bootstrap()
        self._launchctl_or_exit(["launchctl", "kickstart", self._target])
        problems = self._confirm_started()
        if problems:
            for line in problems:
                print(line)
            sys.exit(1)

    def stop(self) -> None:
        if not self._loaded():
            print("The watcher was not running.")
            return
        self._launchctl_or_exit(["launchctl", "bootout", self._target])
        print("Stopped the watcher daemon.")

    def running(self) -> bool:
        return self._facts().get("state") == "running"

    def show_log(self, lines: int, *, following: bool = False) -> None:
        if following:
            follow(self._run, tail_command(self._log, lines))
        else:
            print_tail(self._log, lines)

    def remove(self) -> None:
        if self._loaded():
            self._launchctl_or_exit(["launchctl", "bootout", self._target], ignore_failure=True)
        if self._plist.exists():
            self._plist.unlink()
            print(f"Removed {self._plist}.")

    def check(self) -> ServiceCheck:
        if not self._plist.exists():
            return ServiceCheck([fail(f"no LaunchAgent at {self._plist}", START)], None, None)
        path = _plist_path(self._plist)
        printed = self._launchctl(["launchctl", "print", self._target])
        if printed.returncode != 0:
            return ServiceCheck([fail(f"the LaunchAgent at {self._plist} is not loaded", START)],
                                path, None)
        text = str(printed.stdout)
        facts = _parse_launchctl_print(text)
        program = facts.get("program", "")
        state = facts.get("state", "unknown")
        if program and not Path(program).exists():
            finding = fail(f"the LaunchAgent's program {program} does not exist", RESTART)
        elif "CODESIGNING" in text:
            finding = fail("launchd killed the watcher in a code-signing check, and keeps it "
                           "dead until it is reloaded", RESTART)
        elif state != "running":
            finding = fail(f"launchd state: {state}, last exit code "
                           f"{facts.get('last exit code', 'unknown')}", SHOWS_WHY)
        else:
            finding = ok(f"the LaunchAgent is running as pid {facts.get('pid', 'unknown')}")
        return ServiceCheck([finding], path, _pid(facts.get("pid", "")))

    def _launchctl(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return _ran(self._run, cmd)

    def _launchctl_or_exit(self, cmd: list[str], *, ignore_failure: bool = False) -> None:
        _ran_or_exit(self._run, cmd, ignore_failure=ignore_failure)

    def _bootstrap(self) -> None:
        cmd = ["launchctl", "bootstrap", self._domain, str(self._plist)]
        for _ in range(BOOTSTRAP_ATTEMPTS):
            done = self._launchctl(cmd)
            if done.returncode == 0:
                return
            self._sleep(1)
        print("launchctl bootstrap kept failing; the watcher is not loaded.")
        print(str(done.stderr).strip())
        sys.exit(1)

    def _loaded(self) -> bool:
        return self._launchctl(["launchctl", "print", self._target]).returncode == 0

    def _facts(self) -> dict[str, str]:
        return _parse_launchctl_print(str(self._launchctl(
            ["launchctl", "print", self._target]).stdout))

    def _confirm_started(self) -> list[str]:
        for attempt in range(START_ATTEMPTS):
            facts = self._facts()
            if facts.get("state") == "running":
                return []
            if attempt < START_ATTEMPTS - 1:
                self._sleep(0.5)
        return _not_running(facts)


def _noted[T](config: CliConfig, definition: T) -> T:
    if config.python_note is not None:
        print(config.python_note, flush=True)
    return definition


def service_for(config: CliConfig, run: Run, sleep: Sleep, log: Path) -> Service:
    if config.platform != "darwin":
        unit = SYSTEMD_UNIT if config.instance is None else f"{SYSTEMD_UNIT}-{config.instance}"
        description = "github-orchestrator watcher" + (
            "" if config.instance is None else f" ({config.instance})")
        return SystemdService(run, sleep, uid=config.uid, unit=f"{unit}.service",
                              unit_file=config.home / ".config" / "systemd" / "user" / f"{unit}.service",
                              definition=lambda: _noted(config, systemd_unit(
                                  description=description, python=config.python,
                                  path=config.shell_path, environment=config.child_environment)))
    label = launchd_label(config.instance)

    def definition() -> bytes:
        log.parent.mkdir(parents=True, exist_ok=True)
        return _noted(config, launchagent(label=label, python=config.python, path=config.shell_path,
                           environment=config.child_environment, log=log))

    return LaunchdService(run, sleep, uid=config.uid, label=label,
                          plist=config.home / "Library" / "LaunchAgents" / f"{label}.plist",
                          log=log,
                          definition=definition)



def _facts(shown: str) -> dict[str, str]:
    return dict(line.partition("=")[::2] for line in shown.splitlines())


def _looping(facts: dict[str, str]) -> bool:
    restarted = facts.get("NRestarts", "0").isdigit() and int(facts["NRestarts"]) > 0
    return (facts.get("Result") == "start-limit-hit" or facts.get("SubState") == "auto-restart"
            or (facts.get("ActiveState") == "failed" and restarted))


class SystemdService:
    def __init__(self, run: Run, sleep: Sleep, *, uid: int, unit: str, unit_file: Path,
                 definition: Callable[[], str]) -> None:
        self._run = run
        self._uid = uid
        self._sleep = sleep
        self._unit = unit
        self._unit_file = unit_file
        self._definition = definition

    def start(self, *, keep_old: bool = False) -> None:
        self._unit_file.parent.mkdir(parents=True, exist_ok=True)
        _written(self._unit_file, self._definition().encode(), keep_old=keep_old)
        reload = self._systemctl(["daemon-reload"])
        if reload.returncode != 0:
            print("systemctl --user cannot reach a user manager here, so the watcher cannot "
                  "run as a service:")
            print(f"  {str(reload.stderr).strip()}")
            print("Run github-orchestrator start --foreground to run it in this terminal instead.")
            sys.exit(1)
        self._systemctl_or_exit(["reset-failed", self._unit], ignore_failure=True)
        if self.running():
            self._systemctl_or_exit(["restart", self._unit])
        else:
            self._systemctl_or_exit(["enable", "--now", self._unit])
        for attempt in range(START_ATTEMPTS):
            if self.running():
                return
            if attempt < START_ATTEMPTS - 1:
                self._sleep(0.5)
        facts = self._facts()
        print("The watcher was started but is not running.")
        print(f"  systemd state: {facts.get('ActiveState', 'unknown')} "
              f"({facts.get('SubState', 'unknown')})")
        print(f"  last exit status: {facts.get('ExecMainStatus', 'unknown')}")
        print("github-orchestrator logs service shows why.")
        sys.exit(1)

    def stop(self) -> None:
        if not self.running():
            print("The watcher was not running.")
            return
        self._systemctl_or_exit(["stop", self._unit])
        print("Stopped the watcher daemon.")

    def running(self) -> bool:
        return str(self._systemctl(["is-active", self._unit]).stdout).strip() == "active"

    def show_log(self, lines: int, *, following: bool = False) -> None:
        if following:
            follow(self._run, ["journalctl", "--user", "-u", self._unit, "-n", str(lines), "-f",
                               "--no-pager"])
            return
        print(f"==> journalctl --user -u {self._unit} <==")
        journal = _ran(self._run, ["journalctl", "--user", "-u", self._unit, "-n", str(lines),
                                   "--no-pager"])
        for line in str(journal.stdout).splitlines():
            print(line)

    def remove(self) -> None:
        self._systemctl_or_exit(["disable", "--now", self._unit], ignore_failure=True)
        if self._unit_file.exists():
            self._unit_file.unlink()
            print(f"Removed {self._unit_file}.")
        self._systemctl_or_exit(["daemon-reload"], ignore_failure=True)

    def check(self) -> ServiceCheck:
        shown = self._show()
        if shown.returncode != 0:
            return ServiceCheck([fail(
                "systemctl --user cannot reach a user manager, so the watcher cannot run as a "
                f"service: {str(shown.stderr).strip()}",
                "github-orchestrator start --foreground"), self._lingering()], None, None)
        if not self._unit_file.exists():
            return ServiceCheck([fail(f"no systemd unit at {self._unit_file}", START),
                                 self._lingering()], None, None)
        facts = _facts(str(shown.stdout))
        found = re.search(r"path=(\S+)", facts.get("ExecStart", ""))
        program = found.group(1) if found else ""
        enabled = str(self._systemctl(["is-enabled", self._unit]).stdout).strip() or "not enabled"
        if enabled != "enabled":
            finding = fail(f"{self._unit} is {enabled}", START)
        elif program and not Path(program).exists():
            finding = fail(f"the unit's program {program} does not exist", RESTART)
        elif _looping(facts):
            finding = fail(f"{self._unit} is restarting in a loop "
                           f"({facts.get('NRestarts', '?')} restarts, last exit status "
                           f"{facts.get('ExecMainStatus', 'unknown')})",
                           f"{RESTART}; github-orchestrator logs service shows why it exits")
        elif facts.get("ActiveState") != "active":
            finding = fail(f"systemd state: {facts.get('ActiveState', 'unknown')} "
                           f"({facts.get('SubState', 'unknown')}), last exit status "
                           f"{facts.get('ExecMainStatus', 'unknown')}", SHOWS_WHY)
        else:
            finding = ok(f"{self._unit} is enabled and running as pid {facts.get('MainPID')}")
        return ServiceCheck([finding, self._lingering()], _unit_path(self._unit_file.read_text()),
                            _pid(facts.get("MainPID", "")))

    def _lingering(self) -> Finding:
        shown = _ran(self._run, ["loginctl", "show-user", str(self._uid), "-p", "Linger"])
        linger = _facts(str(shown.stdout)).get("Linger")
        if shown.returncode != 0 or linger is None:
            return warn(f"could not tell whether lingering is on: {str(shown.stderr).strip()}",
                        f"loginctl show-user {self._uid} -p Linger")
        if linger != "yes":
            return warn("lingering is off, so the watcher stops when you log out",
                        "loginctl enable-linger")
        return ok("lingering is on, so the watcher keeps running after you log out")

    def _show(self) -> subprocess.CompletedProcess[str]:
        return self._systemctl(["show", *(f"--property={name}" for name in SYSTEMD_FACTS),
                                self._unit])

    def _facts(self) -> dict[str, str]:
        return _facts(str(self._show().stdout))

    def _systemctl(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return _ran(self._run, ["systemctl", "--user", *args])

    def _systemctl_or_exit(self, args: list[str], *, ignore_failure: bool = False) -> None:
        _ran_or_exit(self._run, ["systemctl", "--user", *args], ignore_failure=ignore_failure)
