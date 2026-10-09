import itertools
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Process:
    command: str
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    output: str | None = None
    own_session: bool = False


class ScriptedProcesses:
    def __init__(self) -> None:
        self.table: dict[int, Process] = {}
        self.spawned: list[Process] = []
        self.calls: list[list[str]] = []
        self.signalled: list[int] = []
        self._pids = itertools.count(4000)

    def exit(self, pid: int) -> None:
        del self.table[pid]

    def reuse(self, pid: int, command: str) -> None:
        self.table[pid] = Process(command)

    def pid_of(self, command: str) -> int:
        [pid] = [pid for pid, process in self.table.items() if process.command == command]
        return pid

    def __call__(self, argv: list[str], *, check: bool = False, capture_output: bool = False,
                 text: bool = False, cwd: str | None = None,
                 env: Mapping[str, str] | None = None, start_new_session: bool = False,
                 **_: Any) -> subprocess.CompletedProcess[Any]:
        self.calls.append(list(argv))
        program = argv[0]
        if program == "sh":
            return self._spawn(argv, cwd, env, start_new_session)
        if program == "ps":
            return self._ps(argv)
        if program == "kill":
            return self._kill(argv, check)
        raise AssertionError(f"the process stand-in does not know {argv!r}")

    def _spawn(self, argv: list[str], cwd: str | None, env: Mapping[str, str] | None,
               own_session: bool) -> subprocess.CompletedProcess[Any]:
        assert argv[1] == "-c" and argv[3] == "sh", argv
        assert "&" in argv[2] and "echo $!" in argv[2], argv
        process = Process(" ".join(argv[5:]), cwd, dict(env or {}), argv[4], own_session)
        pid = next(self._pids)
        self.table[pid] = process
        self.spawned.append(process)
        return subprocess.CompletedProcess(argv, 0, f"{pid}\n", "")

    def _ps(self, argv: list[str]) -> subprocess.CompletedProcess[Any]:
        assert argv[1:4] == ["-o", "command=", "-p"], argv
        process = self.table.get(int(argv[4]))
        if process is None:
            return subprocess.CompletedProcess(argv, 1, "", "")
        return subprocess.CompletedProcess(argv, 0, f"{process.command}\n", "")

    def _kill(self, argv: list[str], check: bool) -> subprocess.CompletedProcess[Any]:
        assert argv[1] == "-TERM", argv
        pid = int(argv[2])
        if pid not in self.table:
            stderr = f"kill: {pid}: No such process\n"
            if check:
                raise subprocess.CalledProcessError(1, argv, "", stderr)
            return subprocess.CompletedProcess(argv, 1, "", stderr)
        self.signalled.append(pid)
        del self.table[pid]
        return subprocess.CompletedProcess(argv, 0, "", "")
