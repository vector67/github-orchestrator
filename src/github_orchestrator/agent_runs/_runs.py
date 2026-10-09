from __future__ import annotations

import codecs
import fcntl
import itertools
import json
import logging
import os
import select
import shlex
import subprocess
import threading
from collections.abc import Callable, Mapping, Sequence, Set
from datetime import datetime
from pathlib import Path
from typing import Any

from github_orchestrator.agent_runs._agents import Agent
from github_orchestrator.agent_runs._command_lines import CommandLines, command_lines_of
from github_orchestrator.agent_runs._ledger import (
    FINISHED_SCAN_BYTES,
    SEED_SCAN_BYTES,
    THREAD_EVENT_PREFIX,
    ended_now,
    finished_in,
    last_run_in,
    ledger_entry,
    local_midnight,
    outcome_after,
)
from github_orchestrator.agent_runs._pr_prompts import (
    fix_check_prompt,
    rebase_prompt,
    rereview_prompt,
    review_prompt,
)
from github_orchestrator.agent_runs._report_commands import ReportCommands
from github_orchestrator.agent_runs._summaries import Run, Summaries
from github_orchestrator.agent_runs._summary_prompts import (
    comment_gist_prompt,
    comments_prompt,
    fixes_prompt,
    gists_in,
    thread_gist_prompt,
    verdict_in,
    verdict_prompt,
)
from github_orchestrator.agent_runs._tail import iter_lines_reverse
from github_orchestrator.agent_runs._thread_prompts import (
    filing_prompt,
    fix_rebase_prompt,
    rework_prompt,
    thread_prompt,
)
from github_orchestrator.agent_runs._transcript import (
    last_thread_in,
    summarize_event,
    tail_display_lines,
)
from github_orchestrator.agent_runs.interface import (
    FinishedRun,
    FixComment,
    LastRun,
    Replied,
    RunDay,
    ThreadFix,
)
from github_orchestrator.domain import Monotonic, Pr, Repo
from github_orchestrator.pr_processes import PrProcesses

log = logging.getLogger(__name__)

def _repo_dir(base: Path, repo: Repo) -> Path:
    return Path(base) / repo.owner / repo.name

_TERMINATE_GRACE_SECONDS = 5.0
_DRAIN_BUFSIZE = 65536
_MAX_BUFFER_BYTES = 10 * 1024 * 1024
_MAX_LOGGED_LINE = 2000
NOTIFICATIONS = "notifications"
CARRY_ON = "manual-continue"
CARRY_ON_PROMPT = "Carry on where you left off."
WONT_START = "could not start the agent"

Popen = Callable[..., "subprocess.Popen[bytes]"]


def _is_setting(word: str) -> bool:
    return word.partition("=")[0].isidentifier() and "=" in word


def _filled_in(setting: str) -> str:
    name, _, value = setting.partition("=")
    return f"{name}={os.path.expanduser(value)}"


def command_program(command: str) -> str:
    return next((word for word in shlex.split(command) if not _is_setting(word)), command)


def command_argv(command: str) -> list[str]:
    words = shlex.split(command)
    settings = list(itertools.takewhile(_is_setting, words))
    if not settings:
        return words
    return ["env", *map(_filled_in, settings), *words[len(settings):]]


def open_session_in(pr_processes: PrProcesses, pr: Pr, worktree: str, command: list[str],
                    prompt: str) -> str | None:
    return pr_processes.split(pr, worktree, [*command, prompt])


class AgentRun:
    def __init__(
        self,
        *,
        proc: subprocess.Popen[bytes],
        pr: Pr,
        event_type: str,
        transcript_path: Path,
        runs_log: Path,
        clock: Monotonic,
        in_flight: Path | None = None,
    ) -> None:
        self.proc = proc
        self.pr = pr
        self.event_type = event_type
        self.transcript_path = transcript_path
        self.runs_log = runs_log
        self._clock = clock
        now = clock()
        self.started_at = now
        self.last_event_at = now
        self._outcome: dict[str, Any] = {}
        self.last_action: str | None = None
        self._stdout_buffer = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._end_recorded = False
        self._in_flight = in_flight
        self._interrupted = False
        if in_flight is not None:
            try:
                in_flight.parent.mkdir(parents=True, exist_ok=True)
                in_flight.write_text(event_type)
            except OSError as exc:
                log.warning("agent_run %s: could not mark the run in flight at %s: %s",
                            pr, in_flight, exc)

    def is_alive(self) -> bool:
        return self.proc.poll() is None

    @property
    def over(self) -> bool:
        return self._end_recorded

    def finished(self) -> LastRun:
        return LastRun(self.event_type, self.proc.returncode, ended_now())

    def _record_end(self) -> None:
        if self._end_recorded:
            return
        self._end_recorded = True
        if self._in_flight is not None and not self._interrupted:
            try:
                self._in_flight.unlink(missing_ok=True)
            except OSError as exc:
                log.warning("agent_run %s: could not clear %s: %s",
                            self.pr, self._in_flight, exc)
        entry = ledger_entry(self.pr, self.event_type, self.elapsed(),
                             self.proc.returncode, self._outcome)
        try:
            self.runs_log.parent.mkdir(parents=True, exist_ok=True)
            with self.runs_log.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as exc:
            log.warning("agent_run %s: could not record run in %s: %s",
                        self.pr, self.runs_log, exc)

    def elapsed(self) -> float:
        return self._clock() - self.started_at

    def silent_for(self) -> float:
        return self._clock() - self.last_event_at

    def pump(self) -> bool:
        self._drain_stdout()
        if self.proc.poll() is None:
            return True
        self._drain_stdout()
        self._record_end()
        return False

    def _drain_stdout(self) -> None:
        if self.proc.stdout is None:
            return
        while True:
            ready, _, _ = select.select([self.proc.stdout], [], [], 0)
            if not ready:
                return
            try:
                raw = self.proc.stdout.read(_DRAIN_BUFSIZE)
            except (OSError, ValueError):
                return
            if raw is None:
                return
            if not raw:
                trailing = self._decoder.decode(b"", final=True)
                self._stdout_buffer += trailing
                if self._stdout_buffer:
                    line = self._stdout_buffer.rstrip("\r")
                    self._stdout_buffer = ""
                    if line:
                        self._handle_line(line)
                self.proc.poll()
                return
            self._stdout_buffer += self._decoder.decode(raw)
            if len(self._stdout_buffer) > _MAX_BUFFER_BYTES:
                log.error(
                    "agent_run %s: stdout buffer exceeded %d bytes without newline; truncating",
                    self.pr, _MAX_BUFFER_BYTES,
                )
                self._stdout_buffer = ""
            while "\n" in self._stdout_buffer:
                line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
                line = line.rstrip("\r")
                if not line:
                    continue
                self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            log.warning("agent_run %s: non-JSON output: %s", self.pr,
                        line[:_MAX_LOGGED_LINE])
            return
        self.last_event_at = self._clock()
        try:
            self.transcript_path.parent.mkdir(parents=True, exist_ok=True)
            with self.transcript_path.open("a") as f:
                f.write(line + "\n")
        except OSError as exc:
            log.warning("agent_run %s: could not write the transcript to %s: %s",
                        self.pr, self.transcript_path, exc)
        lines = summarize_event(event)
        if lines:
            self.last_action = lines[-1]
        self._outcome = outcome_after(event, self._outcome)

    def interrupt(self) -> None:
        self._interrupted = not self._end_recorded
        self.terminate()

    def terminate(self) -> None:
        try:
            if self.proc.poll() is not None:
                return
            try:
                self.proc.terminate()
            except (ProcessLookupError, OSError):
                return
            deadline = self._clock() + _TERMINATE_GRACE_SECONDS
            while self._clock() < deadline:
                try:
                    self.proc.wait(timeout=0.1)
                    return
                except subprocess.TimeoutExpired:
                    pass
            try:
                self.proc.kill()
            except (ProcessLookupError, OSError):
                pass
        finally:
            self._record_end()


class AgentRuns:
    def __init__(self, popen: Popen, run: Run, clock: Monotonic, *,
                 pr_processes: PrProcesses, report_commands: ReportCommands, changes_file: str,
                 agent: Agent, command: str, model: str,
                 summary_model: str, pytest_workers: int, transcripts_dir: Path,
                 runs_log: Path) -> None:
        self._popen = popen
        self._command = command_argv(command)
        self._commands = report_commands
        self._changes_file = changes_file
        self._workers = pytest_workers
        self._clock = clock
        self._pr_processes = pr_processes
        self._model = model
        self._transcripts_dir = transcripts_dir
        self._runs_log = runs_log
        self._lines: CommandLines = command_lines_of(agent)
        self._summaries = Summaries(run, self._command, summary_model, self._lines)
        self._pr_runs: dict[Pr, AgentRun] = {}

    def _transcript(self, pr: Pr) -> Path:
        return _repo_dir(self._transcripts_dir, pr.repo) / f"{pr.number}.jsonl"

    def _in_flight(self, pr: Pr) -> Path:
        return _repo_dir(self._transcripts_dir, pr.repo) / f"{pr.number}.running"

    def _start(self, worktree: str, pr: Pr, event_type: str, prompt: str, *,
               continuing: bool = False, in_flight: Path | None = None) -> AgentRun | str:
        thread = last_thread_in(self._transcript(pr)) if continuing else None
        argv = [*self._command,
                *self._lines.headless(self._model, carrying_on=continuing, thread=thread)]

        try:
            proc = self._popen(
                argv,
                cwd=worktree,
                env=self._lines.env(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            refused = f"{WONT_START}: {exc}"
            log.error("agent_run %s: %s (event=%s)", pr, refused, event_type)
            return refused

        if proc.stdin is not None:
            stdin = proc.stdin

            def _write_prompt() -> None:
                try:
                    stdin.write(prompt.encode("utf-8"))
                    stdin.close()
                except (BrokenPipeError, OSError) as exc:
                    log.warning("agent_run %s: stdin write failed: %s", pr, exc)
            threading.Thread(target=_write_prompt, daemon=True).start()

        if proc.stdout is not None:
            flags = fcntl.fcntl(proc.stdout, fcntl.F_GETFL)
            fcntl.fcntl(proc.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        log.info("Spawned the agent for %s (event=%s, pid=%s)", pr, event_type, proc.pid)

        return AgentRun(
            proc=proc,
            pr=pr,
            event_type=event_type,
            transcript_path=self._transcript(pr),
            runs_log=self._runs_log,
            clock=self._clock,
            in_flight=in_flight,
        )

    def _pr_run(self, worktree: str, pr: Pr, event_type: str, prompt: str, *,
                continuing: bool = False) -> AgentRun | str:
        run = self._start(worktree, pr, event_type, prompt, continuing=continuing,
                          in_flight=self._in_flight(pr))
        if not isinstance(run, str):
            self._pr_runs[pr] = run
        return run

    def review(self, worktree: str, pr: Pr, event_type: str, *, title: str, url: str,
               branch: str, additions: int, deletions: int) -> AgentRun | str:
        return self._pr_run(worktree, pr, event_type, review_prompt(
            self._commands, self._changes_file, pr, title, url, branch, additions, deletions))

    def rereview(self, worktree: str, pr: Pr, event_type: str, *, title: str, url: str,
                 branch: str, verdict: str, said: FixComment | None, since: str | None,
                 commits: Sequence[str] | None, replied: Replied) -> AgentRun | str:
        return self._pr_run(worktree, pr, event_type, rereview_prompt(
            self._commands, self._changes_file, pr, title, url, branch, verdict=verdict,
            said=said, since=since, commits=commits, replied=replied))

    def fix_check(self, worktree: str, pr: Pr, event_type: str, *, check: str,
                  summary: str | None, push: bool) -> AgentRun | str:
        return self._pr_run(worktree, pr, event_type,
                            fix_check_prompt(self._changes_file, pr, check, summary, push,
                                             self._workers))

    def rebase(self, worktree: str, pr: Pr, event_type: str, *, reason: str) -> AgentRun | str:
        return self._pr_run(worktree, pr, event_type, rebase_prompt(pr, reason))

    def carry_on(self, worktree: str, pr: Pr) -> AgentRun | str:
        return self._pr_run(worktree, pr, CARRY_ON, CARRY_ON_PROMPT, continuing=True)

    def rebase_in_session(self, pr: Pr, worktree: str) -> str | None:
        return self._pr_processes.split(pr, worktree, [*self._command, *self._lines.rebase_session()])

    def _fix_thread(self, fix: ThreadFix, prompt: str) -> AgentRun | str:
        return self._start(fix.worktree, fix.pr, f"{THREAD_EVENT_PREFIX}{fix.key}", prompt)

    def fix(self, fix: ThreadFix) -> AgentRun | str:
        return self._fix_thread(fix, thread_prompt(self._commands, fix, self._workers))

    def rebase_fix(self, fix: ThreadFix, onto: str | None) -> AgentRun | str:
        return self._fix_thread(fix, fix_rebase_prompt(self._commands, fix, onto, self._workers))

    def rework(self, fix: ThreadFix) -> AgentRun | str:
        return self._fix_thread(fix, rework_prompt(self._commands, fix, None, self._workers))

    def file_ticket(self, fix: ThreadFix) -> AgentRun | str:
        return self._fix_thread(fix, filing_prompt(self._commands, fix))

    def open_session(self, fix: ThreadFix, steer: str | None) -> str | None:
        return open_session_in(self._pr_processes, fix.pr, fix.worktree, self._command,
                        rework_prompt(self._commands, fix, steer, self._workers))

    def last_run(self, pr: Pr) -> LastRun | None:
        return last_run_in(iter_lines_reverse(self._runs_log, max_bytes=SEED_SCAN_BYTES),
                           pr)

    def transcript_tail(self, pr: Pr, limit: int) -> list[tuple[str, bool]]:
        return tail_display_lines(self._transcript(pr), limit)

    def finished_since(self, when: datetime) -> list[FinishedRun]:
        return finished_in(iter_lines_reverse(self._runs_log, max_bytes=FINISHED_SCAN_BYTES),
                           when)

    def finished_today(self, now: datetime) -> RunDay:
        return RunDay(tuple(self.finished_since(local_midnight(now))))

    def live(self, pr: Pr) -> bool:
        run = self._pr_runs.get(pr)
        return run is not None and not run.over

    def interrupted(self, pr: Pr) -> str | None:
        marker = self._in_flight(pr)
        if self.live(pr) or not marker.exists():
            return None
        try:
            return marker.read_text()
        except OSError:
            return ""

    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]:
        archived: list[Path] = []
        if not self._transcripts_dir.exists():
            return archived
        for owner_dir in self._transcripts_dir.iterdir():
            if not owner_dir.is_dir():
                continue
            for repo_dir in list(owner_dir.iterdir()):
                if not repo_dir.is_dir():
                    continue
                if (owner_dir.name, repo_dir.name) in {(repo.owner, repo.name) for repo in keep}:
                    continue
                dest_parent = into / owner_dir.name
                dest_parent.mkdir(parents=True, exist_ok=True)
                dest = dest_parent / repo_dir.name
                repo_dir.rename(dest)
                archived.append(dest)
        return archived

    def summarize_comment(self, key: str, path: str | None, line: int | None, body: str,
                          done: Callable[[str], None], *, chars: int) -> None:
        self._summaries.summarize(comment_gist_prompt(body, path, line, chars), done, label=key)

    def summarize_thread(self, key: str, path: str | None, line: int | None,
                         comments: Sequence[tuple[str, str]], done: Callable[[str], None],
                         *, chars: int) -> None:
        self._summaries.summarize(thread_gist_prompt(comments, path, line, chars), done,
                                  label=key)

    def summarize_comments(self, bodies: Sequence[str],
                           done: Callable[[tuple[str, ...]], None], *, chars: int) -> None:
        self._summaries.summarize(comments_prompt(bodies, chars),
                                  lambda answer: done(gists_in(answer, len(bodies))),
                                  label=NOTIFICATIONS)

    def summarize_fixes(self, fixes: Sequence[tuple[Sequence[tuple[str, str]], str | None]],
                        done: Callable[[str], None], *, chars: int) -> None:
        self._summaries.summarize(fixes_prompt(fixes, chars), done, label=NOTIFICATIONS)

    def judge_thread(self, key: str, comments: Sequence[tuple[str, str, str]], *,
                     viewer: str, pr_author: str, spoke_last: str, viewer_commented: bool,
                     mentions_viewer: bool, kind: str, answers: Mapping[str, str],
                     done: Callable[[str], None]) -> None:
        def given(answer: str) -> None:
            word = verdict_in(answer, answers)
            if word is not None:
                done(word)

        self._summaries.summarize(
            verdict_prompt(comments, viewer=viewer, pr_author=pr_author, spoke_last=spoke_last,
                           viewer_commented=viewer_commented,
                           mentions_viewer=mentions_viewer, kind=kind, answers=answers),
            given, label=key)

    def drain_summaries(self, timeout: float) -> bool:
        return self._summaries.drain(timeout)
