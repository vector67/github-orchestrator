import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

LABEL = "com.github-orchestrator.watcher"
WATCHER_PID = 4242


@dataclass
class Job:
    state: str = "running"
    program: str = "/opt/homebrew/bin/uv"
    last_exit: str = "(never exited)"
    last_exit_reason: str | None = None


@dataclass(frozen=True)
class Call:
    cmd: list[str]
    env: object = None


@dataclass
class ScriptedSystem:
    uid: int = 501
    jobs: dict[str, Job | None] = field(default_factory=dict)
    loaded_plist: str | None = None
    starts_as: Job = field(default_factory=Job)
    starting_reads: int = 0
    bootout_exit: int = 0
    bootstrap_refusals: int = 0
    refusal: str = "Bootstrap failed: 5: Input/output error\n"
    kickstart_refusal: str | None = None
    hangs: set[str] = field(default_factory=set)
    calls: list[Call] = field(default_factory=list)
    on_kickstart: Callable[[], None] = lambda: None
    mcp_list: str = ""
    mcp_list_exit: int = 0
    login_status: str = "Logged in using ChatGPT\n"
    login_status_exit: int = 0
    units: dict[str, str] = field(default_factory=dict)
    unit_starts_as: str = "active"
    user_manager: bool = True
    exit_status: str = "0"
    journal: dict[str, list[str]] = field(default_factory=dict)
    watcher_exit: int = 0
    watcher_interrupted: bool = False
    gh_version: str = "gh version 2.81.0 (2025-10-01)\n"
    disabled: set[str] = field(default_factory=set)
    exec_program: str = "/tools/github-orchestrator/bin/python"
    restarts: int = 0
    result: str = "success"
    linger: bool = True
    remotes: dict[str, str | None] = field(default_factory=dict)
    tmux_sessions: dict[str, dict[str, list[str]]] | None = None
    follow_interrupted: bool = False
    crontab: str | None = None
    installed_wheels: list[bytes] = field(default_factory=list)
    uv_install_error: str | None = None
    reran: int = 0

    @property
    def job(self) -> Job | None:
        return self.jobs.get(LABEL)

    @job.setter
    def job(self, job: Job | None) -> None:
        self.jobs[LABEL] = job

    def __call__(self, cmd: list[str], *args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        program, *rest = cmd
        self.calls.append(Call(cmd, kwargs.get("env")))
        if cmd[1:] == ["-m", "github_orchestrator.watcher", "--loop"]:
            if self.watcher_interrupted:
                raise KeyboardInterrupt
            return self._done(cmd, self.watcher_exit)
        if program == "launchctl":
            return self._launchctl(cmd, rest[0], rest[1:])
        if program == "systemctl" and rest[0] == "--user":
            return self._systemctl(cmd, rest[1], rest[2:])
        if program == "git" and rest[0] == "-C" and rest[2:] == ["remote", "get-url", "origin"]:
            return self._remote(cmd, rest[1])
        if cmd[:2] == ["loginctl", "show-user"]:
            return self._done(cmd, stdout=f"Linger={'yes' if self.linger else 'no'}\n")
        if program == "crontab":
            return self._crontab(cmd, rest, kwargs.get("input"))
        if cmd[1:3] == ["-m", "github_orchestrator.cli"]:
            self.reran += 1
            return self._done(cmd)
        if program == "tail" or (program == "journalctl" and "-f" in rest):
            if self.follow_interrupted:
                raise KeyboardInterrupt
            return self._done(cmd)
        if program == "journalctl":
            return self._journalctl(cmd, rest)
        if Path(program).name == "gh" and rest == ["--version"]:
            return self._done(cmd, stdout=self.gh_version)
        if program == "tmux":
            return self._tmux(cmd, rest)
        if Path(program).name == "uv" and rest[:2] == ["tool", "install"]:
            if self.uv_install_error is not None:
                return self._done(cmd, 2, stderr=f"{self.uv_install_error}\n")
            self.installed_wheels.append(Path(rest[-1]).read_bytes())
            return self._done(cmd)
        if Path(program).name == "uv" and rest[:2] == ["tool", "uninstall"]:
            return self._done(cmd, stderr=f"Uninstalled 1 executable: {rest[2]}\n")
        if program == "pkill":
            return self._pkill(cmd, rest)
        if cmd[-2:] == ["login", "status"]:
            return self._done(cmd, self.login_status_exit, stderr=self.login_status)
        if cmd[-2:] == ["mcp", "list"]:
            return self._done(cmd, self.mcp_list_exit, stdout=self.mcp_list)
        raise AssertionError(f"the CLI ran something this machine does not answer: {cmd!r}")

    def _crontab(self, cmd: list[str], rest: list[str],
                 given: object) -> subprocess.CompletedProcess[str]:
        if rest == ["-l"]:
            if self.crontab is None:
                return self._done(cmd, 1, stderr="crontab: no crontab for runner\n")
            return self._done(cmd, stdout=self.crontab)
        assert rest == ["-"] and isinstance(given, str), cmd
        self.crontab = given
        return self._done(cmd)

    def _tmux(self, cmd: list[str], rest: list[str]) -> subprocess.CompletedProcess[str]:
        if self.tmux_sessions is None:
            raise FileNotFoundError(2, "No such file or directory", "tmux")
        assert rest[:3] == ["list-panes", "-s", "-t"] and rest[4:] == ["-F", "#{pane_pid}"], cmd
        target = rest[3]
        assert target.startswith("="), cmd
        panes = self.tmux_sessions.get(target[1:])
        if panes is None:
            return self._done(cmd, 1, stderr=f"can't find session: {target[1:]}\n")
        return self._done(cmd, stdout="".join(f"{pane}\n" for pane in panes))

    def _pkill(self, cmd: list[str], rest: list[str]) -> subprocess.CompletedProcess[str]:
        assert rest[:2] == ["-TERM", "-P"] and rest[3] == "-f", cmd
        parent, pattern = rest[2], rest[4]
        killed = False
        for panes in (self.tmux_sessions or {}).values():
            children = panes.get(parent, [])
            kept = [child for child in children if not re.search(pattern, child)]
            killed = killed or len(kept) < len(children)
            if parent in panes:
                panes[parent] = kept
        return self._done(cmd, 0 if killed else 1)

    def _done(self, cmd: list[str], code: int = 0, stdout: str = "",
              stderr: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, code, stdout, stderr)

    def _domain(self) -> str:
        return f"gui/{self.uid}"

    def _label(self, target: str) -> str | None:
        domain, _, label = target.rpartition("/")
        return label if domain == self._domain() and label.startswith(LABEL) else None

    def _launchctl(self, cmd: list[str], verb: str, operands: list[str]) -> subprocess.CompletedProcess[str]:
        if verb in self.hangs:
            raise subprocess.TimeoutExpired(cmd, 30)
        if verb == "bootout":
            label = self._label(operands[0])
            if label is not None:
                self.jobs[label] = None
            return self._done(cmd, self.bootout_exit, stderr="Boot-out failed\n" if self.bootout_exit else "")
        if verb == "bootstrap":
            if self.bootstrap_refusals:
                self.bootstrap_refusals -= 1
                return self._done(cmd, 5, stderr=self.refusal)
            if operands[0] != self._domain():
                return self._done(cmd, 5, stderr=f"unknown domain {operands[0]}\n")
            self.loaded_plist = operands[1]
            self.jobs[Path(operands[1]).stem] = Job(
                "spawn scheduled", self.starts_as.program, self.starts_as.last_exit)
            return self._done(cmd)
        if verb == "kickstart":
            if self.kickstart_refusal is not None:
                return self._done(cmd, 3, stderr=self.kickstart_refusal)
            label = self._label(operands[0]) if len(operands) == 1 else None
            if label is None or self.jobs.get(label) is None:
                return self._done(cmd, 113, stderr="Could not find service in domain\n")
            self.on_kickstart()
            return self._done(cmd)
        if verb == "print":
            return self._print(cmd, operands[0])
        raise AssertionError(f"launchctl {verb} is not scripted")

    def _systemctl(self, cmd: list[str], verb: str, operands: list[str]) -> subprocess.CompletedProcess[str]:
        if verb in self.hangs:
            raise subprocess.TimeoutExpired(cmd, 30)
        if not self.user_manager:
            return self._done(cmd, 1, stderr="Failed to connect to bus: No medium found\n")
        if verb == "daemon-reload":
            return self._done(cmd)
        unit = operands[-1]
        if verb == "reset-failed":
            if unit not in self.units:
                return self._done(cmd, 1, stderr=f"Failed to reset failed state of unit {unit}: "
                                                 f"Unit {unit} not loaded.\n")
            if self.units[unit] == "failed":
                self.units[unit] = "inactive"
            return self._done(cmd)
        if verb == "is-enabled":
            enabled = unit in self.units and unit not in self.disabled
            return self._done(cmd, 0 if enabled else 1,
                              stdout="enabled\n" if enabled else "disabled\n")
        if verb == "is-active":
            state = self.units.get(unit, "inactive")
            return self._done(cmd, 0 if state == "active" else 3, stdout=f"{state}\n")
        if verb == "disable":
            self.units.pop(unit, None)
            return self._done(cmd)
        if verb in ("enable", "restart"):
            self.units[unit] = self.unit_starts_as
            return self._done(cmd)
        if verb == "stop":
            self.units[unit] = "inactive"
            return self._done(cmd)
        if verb == "show":
            state = self.units.get(unit, "inactive")
            return self._done(cmd, stdout=(
                f"ActiveState={state}\nSubState={'auto-restart' if state == 'activating' else state}\n"
                f"ExecMainStatus={self.exit_status}\n"
                f"MainPID={WATCHER_PID if state == 'active' else 0}\n"
                f"NRestarts={self.restarts}\n"
                f"Result={self.result}\n"
                f"ExecStart={{ path={self.exec_program} ; argv[]={self.exec_program} -m "
                "github_orchestrator.watcher --loop ; ignore_errors=no ; start_time=[n/a] ; "
                "stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }\n"))
        raise AssertionError(f"systemctl --user {verb} is not scripted")

    def _remote(self, cmd: list[str], clone: str) -> subprocess.CompletedProcess[str]:
        if clone not in self.remotes:
            return self._done(cmd, 128, stderr="fatal: not a git repository (or any of the parent "
                                               "directories): .git\n")
        url = self.remotes[clone]
        if url is None:
            return self._done(cmd, 2, stderr="error: No such remote 'origin'\n")
        return self._done(cmd, stdout=f"{url}\n")

    def _journalctl(self, cmd: list[str], operands: list[str]) -> subprocess.CompletedProcess[str]:
        unit = operands[operands.index("-u") + 1]
        lines = int(operands[operands.index("-n") + 1])
        return self._done(cmd, stdout="".join(
            f"{line}\n" for line in self.journal.get(unit, [])[-lines:]))

    def _print(self, cmd: list[str], target: str) -> subprocess.CompletedProcess[str]:
        label = self._label(target)
        job = self.jobs.get(label) if label is not None else None
        if label is None or job is None:
            return self._done(cmd, 113, stderr="Could not find service\n")
        if job.state == "spawn scheduled":
            if self.starting_reads:
                self.starting_reads -= 1
            else:
                job = self.jobs[label] = self.starts_as
        pid = f"\tpid = {WATCHER_PID}\n" if job.state == "running" else ""
        return self._done(cmd, stdout=(
            f"{target} = {{\n"
            f"\tactive count = {1 if job.state == 'running' else 0}\n"
            f"\tstate = {job.state}\n\n"
            f"\tprogram = {job.program}\n"
            f"{pid}"
            f"\tlast exit code = {job.last_exit}\n"
            + ("" if job.last_exit_reason is None
               else f"\tlast exit reason = {job.last_exit_reason}\n") +
            "}\n"
        ))
