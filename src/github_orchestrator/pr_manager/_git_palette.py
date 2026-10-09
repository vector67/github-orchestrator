import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from github_orchestrator.agent_runs import PrWork
from github_orchestrator.domain import Pr
from github_orchestrator.pr_processes import PrProcesses

_DIGITS = "0123456789"

CAPTURED_TIMEOUT = 60

SHELL = "new"

Run = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class GitCommand:
    keys: str
    mode: str
    display: str
    argv: list[str]
    takes_number: bool = False


GIT_COMMANDS: list[GitCommand] = [
    GitCommand("f", "captured", "git push --force-with-lease",
               ["git", "push", "--force-with-lease"]),
    GitCommand("p", "captured", "git push", ["git", "push"]),
    GitCommand("pra", "captured", "git pull --rebase --autostash",
               ["git", "pull", "--rebase", "--autostash"]),
    GitCommand("s", "captured", "git status", ["git", "status"]),
    GitCommand("l", "split", "git log", ["git", "log"]),
    GitCommand("d", "split", "git diff HEAD", ["git", "diff", "HEAD"]),
    GitCommand("a", "split", "git add -p", ["git", "add", "-p"]),
    GitCommand("c", "split", "git commit", ["git", "commit"]),
    GitCommand("i", "split", "git rebase -i HEAD~<N>",
               ["git", "rebase", "-i", "HEAD~{n}"], takes_number=True),
    GitCommand("r", "agent", "rebase-on-main in an agent session", []),
]


def _number_part(command: GitCommand, buffer: str) -> str | None:
    if not command.takes_number or not buffer.startswith(command.keys):
        return None
    digits = buffer[len(command.keys):]
    if digits and all(char in _DIGITS for char in digits):
        return digits
    return None


def resolve(buffer: str) -> GitCommand | None:
    for command in GIT_COMMANDS:
        if command.takes_number:
            if _number_part(command, buffer) is not None:
                return command
        elif buffer == command.keys:
            return command
    return None


def argv_for(command: GitCommand, buffer: str) -> list[str]:
    digits = _number_part(command, buffer)
    if digits is None:
        return list(command.argv)
    return [part.replace("{n}", digits) for part in command.argv]


def shell_argv() -> list[str]:
    return [os.environ.get("SHELL") or "/bin/sh", "-l"]


def open_in_terminal(command: GitCommand, argv: list[str], pr: Pr, worktree: str,
                     pr_processes: PrProcesses, pr_work: PrWork) -> str | None:
    if command.mode == "agent":
        return pr_work.rebase_in_session(pr, worktree)
    return pr_processes.split(pr, worktree, argv)


@dataclass
class GitResult:
    exit_code: int
    lines: list[str]
    duration: float


def _output_lines(text: str) -> list[str]:
    lines = text.split("\n")
    while lines and not lines[-1]:
        lines.pop()
    return lines


def run_captured(command: GitCommand, argv: list[str], worktree: str, run: Run,
                 monotonic: Callable[[], float]) -> GitResult:
    started = monotonic()
    try:
        completed = run(
            argv, cwd=worktree, capture_output=True, text=True,
            timeout=CAPTURED_TIMEOUT, stdin=subprocess.DEVNULL,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired:
        return GitResult(
            -1, [f"timed out after {CAPTURED_TIMEOUT}s"],
            monotonic() - started,
        )
    return GitResult(
        completed.returncode,
        _output_lines(completed.stdout) + _output_lines(completed.stderr),
        monotonic() - started,
    )
