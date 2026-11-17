from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from github_orchestrator.board_api import _contract as contract
from github_orchestrator.board_api._pages import pr_page
from github_orchestrator.board_api.interface import (
    FinishedRun,
    Pulse,
    RunDay,
    RunLedger,
    WatcherPulse,
)
from github_orchestrator.domain import Pr

LISTED_FOR = timedelta(days=7)


def watcher_read(pulse: Pulse) -> contract.WatcherHealth:
    polled, next_at = pulse.polled_at, pulse.next_poll_at
    return contract.WatcherHealth(
        polled_at=None if polled is None else polled.isoformat(),
        next_poll_at=None if next_at is None else next_at.isoformat(),
        overdue=pulse.overdue, last_error=pulse.last_error,
        mentions_error=pulse.mentions_error, last_error_cause=pulse.last_error_cause,
        mentions_error_cause=pulse.mentions_error_cause,
        last_error_fault=pulse.last_error_fault, mentions_error_fault=pulse.mentions_error_fault,
        hidden_repo=None if pulse.hidden_repo is None else str(pulse.hidden_repo),
        account=pulse.account, config_path=pulse.config_path)


def _today(day: RunDay) -> contract.RunsToday:
    return contract.RunsToday(runs=len(day.finished), cost_usd=day.cost_usd,
                              unpriced=day.unpriced)


def _run(run: FinishedRun, held: Sequence[Pr]) -> contract.FinishedRun:
    pr = run.pr
    return contract.FinishedRun(
        ended_at=run.ended_at.astimezone(timezone.utc).isoformat(), repo=None if pr is None else str(pr.repo),
        number=None if pr is None else pr.number, event=run.event,
        elapsed_seconds=run.elapsed_seconds, exit_code=run.exit_code, cost_usd=run.cost_usd,
        failed=run.failed,
        board_url=pr_page(pr) if pr is not None and pr in held else None)


def ledger_read(ledger: RunLedger, pulse: WatcherPulse, held: Sequence[Pr],
                now: datetime) -> contract.RunLedger:
    finished = ledger.finished_since(now - LISTED_FOR)
    return contract.RunLedger(
        watcher=watcher_read(pulse.health()), today=_today(ledger.finished_today(now)),
        runs=[_run(run, held) for run in reversed(finished)])
