import dataclasses
import json
import time
from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from github_orchestrator.agent_runs._ledger import (
    THREAD_EVENT_PREFIX,
    ended_now,
    finished_in,
    last_run_in,
    ledger_entry,
    local_midnight,
    outcome_after,
)
from github_orchestrator.agent_runs._pr_prompts import REBASE_ON_MAIN
from github_orchestrator.agent_runs._runs import CARRY_ON, WONT_START, open_session_in
from github_orchestrator.agent_runs._summary_prompts import gists_in, verdict_in
from github_orchestrator.agent_runs._transcript import display_rows, summarize_event
from github_orchestrator.agent_runs.interface import (
    FinishedRun,
    FixComment,
    LastRun,
    Replied,
    RunDay,
    ThreadFix,
)
from github_orchestrator.domain import Pr, Repo
from github_orchestrator.pr_processes import PrProcesses

TERMINATED = -15


@dataclass(frozen=True)
class Outcome:
    events: tuple[dict[str, Any], ...] = ()
    exit_code: int = 0
    finishes: bool = True
    starts: bool = True


@dataclass(frozen=True)
class Reviewing:
    title: str
    url: str
    branch: str
    additions: int
    deletions: int


@dataclass(frozen=True)
class Rereviewing:
    title: str
    url: str
    branch: str
    verdict: str
    said: FixComment | None
    since: str | None
    commits: tuple[str, ...] | None
    replied: tuple[tuple[str | None, int | None, tuple[FixComment, ...]], ...]


@dataclass(frozen=True)
class FixingCheck:
    check: str
    summary: str | None
    push: bool


@dataclass(frozen=True)
class Rebasing:
    reason: str


@dataclass(frozen=True)
class CarryingOn:
    pass


@dataclass(frozen=True)
class FixingThread:
    fix: ThreadFix


@dataclass(frozen=True)
class RebasingFix:
    fix: ThreadFix
    onto: str | None


@dataclass(frozen=True)
class Reworking:
    fix: ThreadFix


@dataclass(frozen=True)
class FilingTicket:
    fix: ThreadFix


@dataclass(frozen=True)
class Session:
    fix: ThreadFix
    steer: str | None


Work = (Reviewing | Rereviewing | FixingCheck | Rebasing | CarryingOn | FixingThread | RebasingFix
        | Reworking | FilingTicket)


@dataclass(frozen=True)
class Started:
    worktree: str
    work: Work


@dataclass(frozen=True)
class CommentAsked:
    key: str
    path: str | None
    line: int | None
    body: str
    chars: int


@dataclass(frozen=True)
class ThreadAsked:
    key: str
    path: str | None
    line: int | None
    comments: tuple[tuple[str, str], ...]
    chars: int


@dataclass(frozen=True)
class CommentsAsked:
    bodies: tuple[str, ...]
    chars: int


@dataclass(frozen=True)
class FixesAsked:
    fixes: tuple[tuple[tuple[tuple[str, str], ...], str | None], ...]
    chars: int


@dataclass(frozen=True)
class VerdictAsked:
    key: str
    comments: tuple[tuple[str, str, str], ...]
    viewer: str
    pr_author: str
    spoke_last: str
    viewer_commented: bool
    mentions_viewer: bool
    kind: str


Asked = CommentAsked | ThreadAsked | CommentsAsked | FixesAsked | VerdictAsked


class FakeRun:
    def __init__(self, world: "FakeAgentRuns", pr: Pr, event_type: str,
                 outcome: Outcome, *, in_flight: bool = False) -> None:
        self.event_type = event_type
        self.last_action: str | None = None
        self._world = world
        self._pr = pr
        self._outcome = outcome
        self._started_at = world.clock()
        self._last_event_at = self._started_at
        self._emitted = False
        self._reported: dict[str, Any] = {}
        self._exit_code: int | None = None
        self._in_flight = in_flight
        self._interrupted = False
        if in_flight:
            world.in_flight[pr] = event_type

    def is_alive(self) -> bool:
        return self._exit_code is None

    @property
    def over(self) -> bool:
        return self._exit_code is not None

    def pump(self) -> bool:
        if self._exit_code is not None:
            return False
        if not self._emitted:
            self._emitted = True
            for event in self._outcome.events:
                self._write(event)
        if self._outcome.finishes:
            self._end(self._outcome.exit_code)
        return self._exit_code is None

    def interrupt(self) -> None:
        self._interrupted = self._exit_code is None
        self.terminate()

    def terminate(self) -> None:
        if self._exit_code is None:
            self._end(TERMINATED)

    def elapsed(self) -> float:
        return self._world.clock() - self._started_at

    def silent_for(self) -> float:
        return self._world.clock() - self._last_event_at

    def finished(self) -> LastRun:
        return LastRun(self.event_type, self._exit_code, ended_now())

    def _write(self, event: dict[str, Any]) -> None:
        self._last_event_at = self._world.clock()
        self._world.transcripts.setdefault(self._pr, []).append(json.dumps(event))
        lines = summarize_event(event)
        if lines:
            self.last_action = lines[-1]
        self._reported = outcome_after(event, self._reported)

    def _end(self, exit_code: int) -> None:
        self._exit_code = exit_code
        if self._in_flight and not self._interrupted:
            self._world.in_flight.pop(self._pr, None)
        self._world.ledger.append(ledger_entry(
            self._pr, self.event_type, self.elapsed(), exit_code, self._reported))


@dataclass
class FakeAgentRuns:
    pr_processes: PrProcesses
    clock: Callable[[], float] = time.monotonic
    outcomes: list[Outcome] = field(default_factory=list)
    started: list[Started] = field(default_factory=list)
    sessions: list[Session] = field(default_factory=list)
    pr_runs: dict[Pr, FakeRun] = field(default_factory=dict)
    gists: list[str | tuple[str, ...] | None] = field(default_factory=list)
    asked: list[Asked] = field(default_factory=list)
    ledger: list[dict[str, Any]] = field(default_factory=list)
    transcripts: dict[Pr, list[str]] = field(default_factory=dict)
    in_flight: dict[Pr, str] = field(default_factory=dict)

    def script(self, *outcomes: Outcome) -> "FakeAgentRuns":
        self.outcomes.extend(outcomes)
        return self

    def answer(self, *gists: str | tuple[str, ...] | None) -> "FakeAgentRuns":
        self.gists.extend(gists)
        return self

    def restarted(self) -> "FakeAgentRuns":
        return dataclasses.replace(self, pr_runs={})

    def next_outcome(self) -> Outcome:
        return self.outcomes.pop(0) if self.outcomes else Outcome()

    def next_gist(self) -> str | tuple[str, ...] | None:
        return self.gists.pop(0) if self.gists else None

    def _start(self, worktree: str, pr: Pr, event_type: str, work: Work, *,
               in_flight: bool = False) -> FakeRun | str:
        outcome = self.next_outcome()
        if not outcome.starts:
            return f"{WONT_START}: [Errno 2] No such file or directory: 'claude'"
        self.started.append(Started(worktree, work))
        return FakeRun(self, pr, event_type, outcome, in_flight=in_flight)

    def _pr_run(self, worktree: str, pr: Pr, event_type: str, work: Work) -> FakeRun | str:
        run = self._start(worktree, pr, event_type, work, in_flight=True)
        if not isinstance(run, str):
            self.pr_runs[pr] = run
        return run

    def review(self, worktree: str, pr: Pr, event_type: str, *, title: str, url: str,
               branch: str, additions: int, deletions: int) -> FakeRun | str:
        return self._pr_run(worktree, pr, event_type,
                            Reviewing(title, url, branch, additions, deletions))

    def rereview(self, worktree: str, pr: Pr, event_type: str, *, title: str, url: str,
                 branch: str, verdict: str, said: FixComment | None, since: str | None,
                 commits: Sequence[str] | None, replied: Replied) -> FakeRun | str:
        return self._pr_run(worktree, pr, event_type, Rereviewing(
            title, url, branch, verdict, said, since,
            None if commits is None else tuple(commits),
            tuple((path, line, tuple(comments)) for path, line, comments in replied)))

    def fix_check(self, worktree: str, pr: Pr, event_type: str, *, check: str,
                  summary: str | None, push: bool) -> FakeRun | str:
        return self._pr_run(worktree, pr, event_type, FixingCheck(check, summary, push))

    def rebase(self, worktree: str, pr: Pr, event_type: str, *, reason: str) -> FakeRun | str:
        return self._pr_run(worktree, pr, event_type, Rebasing(reason))

    def carry_on(self, worktree: str, pr: Pr) -> FakeRun | str:
        return self._pr_run(worktree, pr, CARRY_ON, CarryingOn())

    def ran(self, pr: Pr | None, event: str, elapsed_seconds: float, ended_at: datetime,
            cost_usd: float | None = None, exit_code: int = 0) -> "FakeAgentRuns":
        entry: dict[str, Any] = {
            "ended_at": ended_at.isoformat(), "repo": None if pr is None else str(pr.repo),
            "pr": None if pr is None else pr.number, "event": event,
            "elapsed_seconds": elapsed_seconds, "exit_code": exit_code}
        if cost_usd is not None:
            entry["total_cost_usd"] = cost_usd
        self.ledger.append(entry)
        return self

    def rebase_in_session(self, pr: Pr, worktree: str) -> str | None:
        return self.pr_processes.split(pr, worktree, ["claude", REBASE_ON_MAIN])

    def _fix_thread(self, fix: ThreadFix, work: Work) -> FakeRun | str:
        return self._start(fix.worktree, fix.pr, f"{THREAD_EVENT_PREFIX}{fix.key}", work)

    def fix(self, fix: ThreadFix) -> FakeRun | str:
        return self._fix_thread(fix, FixingThread(fix))

    def rebase_fix(self, fix: ThreadFix, onto: str | None) -> FakeRun | str:
        return self._fix_thread(fix, RebasingFix(fix, onto))

    def rework(self, fix: ThreadFix) -> FakeRun | str:
        return self._fix_thread(fix, Reworking(fix))

    def file_ticket(self, fix: ThreadFix) -> FakeRun | str:
        return self._fix_thread(fix, FilingTicket(fix))

    def open_session(self, fix: ThreadFix, steer: str | None) -> str | None:
        refused = open_session_in(self.pr_processes, fix.pr, fix.worktree, ["claude"],
                                  f"session on {fix.key}")
        if refused is None:
            self.sessions.append(Session(fix, steer))
        return refused

    def last_run(self, pr: Pr) -> LastRun | None:
        return last_run_in((json.dumps(entry) for entry in reversed(self.ledger)), pr)

    def transcript_tail(self, pr: Pr, limit: int) -> list[tuple[str, bool]]:
        return display_rows(reversed(self.transcripts.get(pr, [])), limit)

    def finished_since(self, when: datetime) -> list[FinishedRun]:
        return finished_in((json.dumps(entry) for entry in reversed(self.ledger)), when)

    def finished_today(self, now: datetime) -> RunDay:
        return RunDay(tuple(self.finished_since(local_midnight(now))))

    def live(self, pr: Pr) -> bool:
        run = self.pr_runs.get(pr)
        return run is not None and not run.over

    def interrupted(self, pr: Pr) -> str | None:
        return None if self.live(pr) else self.in_flight.get(pr)

    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]:
        others = sorted({pr.repo for pr in self.transcripts if pr.repo not in keep}, key=str)
        self.transcripts = {pr: lines for pr, lines in self.transcripts.items()
                            if pr.repo in keep}
        return [into / repo.owner / repo.name for repo in others]

    def _answered(self) -> str | tuple[str, ...] | None:
        answer = self.next_gist()
        if isinstance(answer, tuple):
            return answer
        return next((line.strip() for line in (answer or "").splitlines() if line.strip()),
                    None)

    def _said(self, done: Callable[[str], None]) -> None:
        answer = self._answered()
        if isinstance(answer, str):
            done(answer)

    def summarize_comment(self, key: str, path: str | None, line: int | None, body: str,
                          done: Callable[[str], None], *, chars: int) -> None:
        self.asked.append(CommentAsked(key, path, line, body, chars))
        self._said(done)

    def summarize_thread(self, key: str, path: str | None, line: int | None,
                         comments: Sequence[tuple[str, str]], done: Callable[[str], None],
                         *, chars: int) -> None:
        self.asked.append(ThreadAsked(key, path, line, tuple(comments), chars))
        self._said(done)

    def summarize_comments(self, bodies: Sequence[str],
                           done: Callable[[tuple[str, ...]], None], *, chars: int) -> None:
        self.asked.append(CommentsAsked(tuple(bodies), chars))
        answer = self._answered()
        if isinstance(answer, str):
            done(gists_in(answer, len(bodies)))
        elif answer is not None:
            done(answer if len(answer) == len(bodies) else ("",) * len(bodies))

    def summarize_fixes(self, fixes: Sequence[tuple[Sequence[tuple[str, str]], str | None]],
                        done: Callable[[str], None], *, chars: int) -> None:
        self.asked.append(FixesAsked(
            tuple((tuple(comments), summary) for comments, summary in fixes), chars))
        self._said(done)

    def judge_thread(self, key: str, comments: Sequence[tuple[str, str, str]], *,
                     viewer: str, pr_author: str, spoke_last: str, viewer_commented: bool,
                     mentions_viewer: bool, kind: str, answers: Mapping[str, str],
                     done: Callable[[str], None]) -> None:
        self.asked.append(VerdictAsked(key, tuple(comments), viewer, pr_author, spoke_last,
                                       viewer_commented, mentions_viewer, kind))
        answer = self._answered()
        word = verdict_in(answer, answers) if isinstance(answer, str) else None
        if word is not None:
            done(word)


@dataclass
class HeldVerdicts(FakeAgentRuns):
    held: list[tuple[str, Mapping[str, str], Callable[[str], None]]] = field(
        default_factory=list)

    def judge_thread(self, key: str, comments: Sequence[tuple[str, str, str]], *,
                     viewer: str, pr_author: str, spoke_last: str, viewer_commented: bool,
                     mentions_viewer: bool, kind: str, answers: Mapping[str, str],
                     done: Callable[[str], None]) -> None:
        self.asked.append(VerdictAsked(key, tuple(comments), viewer, pr_author, spoke_last,
                                       viewer_commented, mentions_viewer, kind))
        self.held.append((key, answers, done))

    def verdicts_asked(self) -> list[VerdictAsked]:
        return [asked for asked in self.asked if isinstance(asked, VerdictAsked)]

    def give(self, word: str, *, key: str | None = None, at: int = -1) -> None:
        waiting = [one for one in self.held if key is None or one[0] == key]
        asked_for, answers, done = waiting[at]
        self.held.remove((asked_for, answers, done))
        assert word in answers
        done(word)
