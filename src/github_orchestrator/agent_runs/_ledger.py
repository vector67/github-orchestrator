import json
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from github_orchestrator.agent_runs.interface import FinishedRun, LastRun
from github_orchestrator.domain import Pr, Repo

THREAD_EVENT_PREFIX = "thread-fix-"
LEDGER_KEYS = ("total_cost_usd", "num_turns", "is_error")

SEED_SCAN_BYTES = 256 * 1024
FINISHED_SCAN_BYTES = 4 * 1024 * 1024


def ended_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ledger_entry(pr: Pr, event_type: str, elapsed: float,
                 exit_code: int | None, outcome: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "ended_at": ended_now(),
        "repo": str(pr.repo),
        "pr": pr.number,
        "event": event_type,
        "elapsed_seconds": round(elapsed, 1),
        "exit_code": exit_code,
    }
    for key in LEDGER_KEYS:
        if key in outcome:
            entry[key] = outcome[key]
    return entry


def outcome_after(event: dict[str, Any], so_far: dict[str, Any]) -> dict[str, Any]:
    event_type = event.get("type")
    if event_type == "result":
        return {key: event[key] for key in LEDGER_KEYS if key in event}
    turns = int(so_far.get("num_turns", 0))
    if event_type == "turn.completed":
        return {**so_far, "num_turns": turns + 1}
    if event_type == "turn.failed":
        return {**so_far, "num_turns": turns + 1, "is_error": True}
    if event_type == "error":
        return {**so_far, "is_error": True}
    return so_far


def last_run_in(newest_first: Iterable[str], pr: Pr) -> LastRun | None:
    for line in newest_first:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("repo") != str(pr.repo) or entry.get("pr") != pr.number:
            continue
        if str(entry.get("event", "")).startswith(THREAD_EVENT_PREFIX):
            continue
        exit_code = entry.get("exit_code")
        return LastRun(
            event_type=str(entry.get("event", "?")),
            exit_code=exit_code if isinstance(exit_code, int) else None,
            ended_at=str(entry.get("ended_at") or ""),
        )
    return None


def _seconds(entry: dict[str, Any]) -> float:
    value = entry.get("elapsed_seconds")
    return value if isinstance(value, (int, float)) else 0


def _cost(entry: dict[str, Any]) -> float | None:
    value = entry.get("total_cost_usd")
    return value if isinstance(value, (int, float)) else None


def _exit_code(entry: dict[str, Any]) -> int | None:
    value = entry.get("exit_code")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _pr_of(entry: dict[str, Any]) -> Pr | None:
    repo, number = entry.get("repo"), entry.get("pr")
    if not isinstance(repo, str) or not isinstance(number, int) or isinstance(number, bool):
        return None
    try:
        return Pr(Repo.parse(repo), number)
    except ValueError:
        return None


def local_midnight(now: datetime) -> datetime:
    return now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)


def finished_in(newest_first: Iterable[str], since: datetime) -> list[FinishedRun]:
    finished = []
    for line in newest_first:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            ended = datetime.fromisoformat(entry["ended_at"]).astimezone()
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        if ended < since:
            continue
        exit_code = _exit_code(entry)
        finished.append(FinishedRun(pr=_pr_of(entry), event=str(entry.get("event", "?")),
                                    elapsed_seconds=_seconds(entry), cost_usd=_cost(entry),
                                    ended_at=ended, exit_code=exit_code,
                                    failed=exit_code not in (0, None)
                                    or entry.get("is_error") is True))
    finished.reverse()
    return finished
