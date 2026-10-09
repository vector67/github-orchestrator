import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from github_orchestrator.agent_runs.fake import FakeAgentRuns

_EMIT = """
[ "$1" = 1 ] && cat > /dev/null
[ "$2" = 1 ] && trap '' TERM
printf '%s' "$3"
[ "$4" = 1 ] || exec sleep 3600
[ "$5" -lt 0 ] && kill -"$((-$5))" $$
exit "$5"
"""


@dataclass(frozen=True)
class Spawned:
    argv: list[str]
    cwd: str
    env: dict[str, str]
    stdin: Any
    stderr: Any


@dataclass(frozen=True)
class Asked:
    argv: list[str]
    cwd: str
    env: dict[str, str]
    timeout: float
    cwd_existed: bool
    prompt: str


class _Prompt:
    def __init__(self, pipe: Any, record: Any) -> None:
        self._pipe = pipe
        self._record = record
        self._written = b""

    def write(self, data: bytes) -> int:
        self._written += data
        written: int = self._pipe.write(data)
        return written

    def close(self) -> None:
        self._record(self._written.decode("utf-8"))
        self._pipe.close()


class ScriptedClaude:
    def __init__(self, world: FakeAgentRuns, program: str = "claude") -> None:
        self.world = world
        self.program = program
        self.spawned: list[Spawned] = []
        self.prompts: list[str | None] = []
        self.asked: list[Asked] = []
        self.scripts: list[str] = []
        self.ignores_terminate = False
        self.summary_failure: BaseException | None = None
        self.children: list[subprocess.Popen[bytes]] = []

    def popen(self, argv: list[str], *, cwd: str, env: dict[str, str], stdin: Any,
              stdout: Any, stderr: Any) -> subprocess.Popen[bytes]:
        assert self.program in argv, argv
        outcome = self.world.next_outcome()
        if not outcome.starts:
            raise FileNotFoundError(2, "No such file or directory", self.program)
        self.spawned.append(Spawned(list(argv), cwd, dict(env), stdin, stderr))
        reads_prompt = stdin == subprocess.PIPE
        if self.scripts:
            command = [sys.executable, "-c", self.scripts.pop(0)]
        else:
            command = ["/bin/sh", "-c", _EMIT, self.program,
                       str(int(reads_prompt)), str(int(self.ignores_terminate)),
                       "".join(json.dumps(event) + "\n" for event in outcome.events),
                       str(int(outcome.finishes)), str(outcome.exit_code)]
        child = subprocess.Popen(command, cwd=cwd, stdin=stdin, stdout=stdout, stderr=stderr)
        self.children.append(child)
        if reads_prompt:
            setattr(child, "stdin", _Prompt(child.stdin, self.prompts.append))
        else:
            self.prompts.append(None)
        return child

    def run(self, argv: list[str], *, input: str, capture_output: bool, text: bool,
            timeout: float, env: dict[str, str], cwd: str) -> subprocess.CompletedProcess[str]:
        self.asked.append(Asked(list(argv), cwd, dict(env), timeout, os.path.isdir(cwd), input))
        if self.summary_failure is not None:
            raise self.summary_failure
        gist = self.world.next_gist()
        if gist is None:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="the model refused")
        assert isinstance(gist, str), "ScriptedClaude answers with the model's text; queue a string"
        return subprocess.CompletedProcess(argv, 0, stdout=gist, stderr="")

    def reap(self) -> None:
        for child in self.children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
