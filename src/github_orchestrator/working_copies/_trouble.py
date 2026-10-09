import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from github_orchestrator.domain import Pr
from github_orchestrator.notifications import Worktrees
from github_orchestrator.working_copies.interface import Verdict, WrongBranch

log = logging.getLogger(__name__)

SHARED_RETRY_SECONDS = 20 * 60
SHARED_NOTIFY_EVERY = 5


@dataclass(frozen=True)
class Grace:
    seconds: int
    run_idle_seconds: int


@dataclass(frozen=True)
class Mismatch:
    worktree: str
    actual_branch: str
    expected_branch: str
    since: float
    run_alive: bool = False
    last_output_at: float | None = None
    release_requested: bool = False


@dataclass(frozen=True)
class Conflict:
    worktree: str
    other_pr: int
    since: float
    checks: int


class Flags(Protocol):
    def mismatch(self, pr: Pr) -> Mismatch | None: ...

    def save_mismatch(self, pr: Pr, mismatch: Mismatch) -> None: ...

    def clear_mismatch(self, pr: Pr) -> None: ...

    def conflict(self, pr: Pr) -> Conflict | None: ...

    def save_conflict(self, pr: Pr, conflict: Conflict) -> None: ...

    def clear_conflict(self, pr: Pr) -> None: ...


def _judge(flag: Mismatch, *, now: float, manager_running: bool, grace: Grace) -> WrongBranch:
    grace_left = max(0.0, flag.since + grace.seconds - now)
    run_working = (manager_running and flag.run_alive and flag.last_output_at is not None
                   and now - flag.last_output_at < grace.run_idle_seconds)
    idle_left = (flag.last_output_at + grace.run_idle_seconds - now
                 if run_working and flag.last_output_at is not None else 0.0)
    hands_off = flag.release_requested or (grace_left <= 0 and not run_working)
    return WrongBranch(
        hands_off=hands_off,
        seconds_left=0.0 if hands_off else max(grace_left, idle_left),
        trouble=(f"{flag.worktree} has {flag.actual_branch}, expected "
                 f"{flag.expected_branch}"),
        run_working=run_working,
        release_requested=flag.release_requested,
        worktree=flag.worktree,
        here=flag.actual_branch,
        expected=flag.expected_branch,
    )


def _sharer(worktree: Path, others: Mapping[Pr, str]) -> Pr | None:
    try:
        target = worktree.resolve()
    except OSError:
        return None
    for other, path in others.items():
        try:
            if Path(path).resolve() == target:
                return other
        except OSError:
            continue
    return None


class BranchTrouble:
    def __init__(self, flags: Flags, grace: Grace, notifications: Worktrees,
                 current_branch: Callable[[str], str | None]) -> None:
        self._flags = flags
        self._grace = grace
        self._notifications = notifications
        self._current_branch = current_branch

    def forget(self, pr: Pr) -> None:
        self._flags.clear_mismatch(pr)
        self._flags.clear_conflict(pr)

    def report_branch(self, pr: Pr, worktree: str, expected: str | None, *,
                      now: float, run_output_at: float | None) -> WrongBranch | None:
        actual = self._current_branch(worktree)
        if not expected or actual is None or actual == expected:
            self._flags.clear_mismatch(pr)
            return None
        existing = self._flags.mismatch(pr)
        flag = Mismatch(
            worktree=worktree,
            actual_branch=actual,
            expected_branch=expected,
            since=existing.since if existing is not None else now,
            run_alive=run_output_at is not None,
            last_output_at=run_output_at,
            release_requested=existing is not None and existing.release_requested,
        )
        self._flags.save_mismatch(pr, flag)
        return _judge(flag, now=now, manager_running=True, grace=self._grace)

    def verdict(self, pr: Pr, worktree: Path | str | None, *, now: float,
                window_open: bool, manager_running: bool = False,
                expected: str | None = None,
                others: Mapping[Pr, str] | None = None) -> Verdict | None:
        if window_open:
            return self._wrong_branch(pr, None if worktree is None else str(worktree),
                                      expected, now=now, manager_running=manager_running)
        if worktree is None:
            return None
        return self._sharing(pr, Path(worktree), others or {}, now=now)

    def _wrong_branch(self, pr: Pr, pane: str | None, expected: str | None, *,
                      now: float, manager_running: bool) -> WrongBranch | None:
        flag = self._flags.mismatch(pr)
        if flag is None:
            flag = self._first_seen(pr, pane, expected, now=now,
                                    manager_running=manager_running)
        if flag is None:
            return None
        return _judge(flag, now=now, manager_running=manager_running, grace=self._grace)

    def _first_seen(self, pr: Pr, pane: str | None, expected: str | None, *,
                    now: float, manager_running: bool) -> Mismatch | None:
        if not manager_running or not expected or pane is None:
            return None
        actual = self._current_branch(pane)
        if actual is None or actual == expected:
            return None
        flag = Mismatch(worktree=pane, actual_branch=actual, expected_branch=expected,
                        since=now)
        self._flags.save_mismatch(pr, flag)
        log.error(
            "ensure_pr_window %s: pane 0 in %s has %s, expected %s — "
            "starting the grace period",
            pr, pane, actual, expected,
        )
        return flag

    def handed_off(self, pr: Pr, kept_as: str) -> None:
        self._flags.clear_mismatch(pr)
        self._notifications.wrong_branch(pr, kept_as)

    def wrong_branch(self, pr: Pr, *, now: float) -> WrongBranch | None:
        flag = self._flags.mismatch(pr)
        if flag is None:
            return None
        return _judge(flag, now=now, manager_running=True, grace=self._grace)

    def request_release(self, pr: Pr) -> bool:
        existing = self._flags.mismatch(pr)
        if existing is None:
            return False
        self._flags.save_mismatch(pr, replace(existing, release_requested=True))
        return True

    def _sharing(self, pr: Pr, worktree: Path, others: Mapping[Pr, str], *,
                 now: float) -> Verdict | None:
        other = _sharer(worktree, others)
        if other is None:
            self._flags.clear_conflict(pr)
            return None
        existing = self._flags.conflict(pr)
        if existing is not None and existing.worktree == str(worktree):
            flag = replace(existing, other_pr=other.number, checks=existing.checks + 1)
        else:
            flag = Conflict(worktree=str(worktree), other_pr=other.number, since=now, checks=1)
        self._flags.save_conflict(pr, flag)

        waited = now - flag.since
        trouble = f"{worktree} is PR {other.in_repo}'s working directory"
        if waited >= SHARED_RETRY_SECONDS:
            log.error(
                "%s: %s is still PR %s's working directory after %.0fs — "
                "opening the window there anyway",
                pr, worktree, other.in_repo, waited,
            )
            self._notifications.still_shared(pr, worktree, other,
                                             SHARED_RETRY_SECONDS // 60)
            self._flags.clear_conflict(pr)
            return Verdict(hands_off=True, seconds_left=0.0, trouble=trouble)

        log.warning(
            "%s: %s is already PR %s's working directory — skipping this cycle "
            "(check %d, waited %.0fs)",
            pr, worktree, other.in_repo, flag.checks, waited,
        )
        if flag.checks == 1 or flag.checks % SHARED_NOTIFY_EVERY == 0:
            self._notifications.shared(pr, worktree, other)
        return Verdict(hands_off=False, seconds_left=SHARED_RETRY_SECONDS - waited,
                       trouble=trouble)
