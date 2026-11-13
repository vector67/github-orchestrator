from collections.abc import Mapping, Set
from datetime import datetime

from github_orchestrator.domain import Pr
from github_orchestrator.pr_summaries.interface import Summary

ASKED_BY_HAND, WANTED = 0, 1


def _wanted_since_answered(summary: Summary) -> datetime | None:
    if summary.wanted is None:
        return None
    if summary.answered is not None and summary.wanted <= summary.answered:
        return None
    return summary.wanted


def _place_in_line(summary: Summary) -> tuple[int, datetime] | None:
    if summary.asked is not None:
        return ASKED_BY_HAND, summary.asked
    wanted = _wanted_since_answered(summary)
    return None if wanted is None else (WANTED, wanted)


def due(summaries: Mapping[Pr, Summary], in_flight: Set[Pr]) -> list[Pr]:
    waiting = [(place, pr) for pr, summary in summaries.items()
               if (place := _place_in_line(summary)) is not None
               and pr not in in_flight]
    return [pr for _, pr in sorted(waiting, key=lambda waiting_pr: waiting_pr[0])]
