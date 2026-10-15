from collections.abc import Mapping, Set
from datetime import datetime

from github_orchestrator.domain import Pr
from github_orchestrator.pr_summaries.interface import Summary


def _wanted_since_answered(summary: Summary) -> datetime | None:
    if summary.wanted is None:
        return None
    if summary.answered is not None and summary.wanted <= summary.answered:
        return None
    return summary.wanted


def due(summaries: Mapping[Pr, Summary], in_flight: Set[Pr]) -> list[Pr]:
    waiting = [(wanted, pr) for pr, summary in summaries.items()
               if (wanted := _wanted_since_answered(summary)) is not None
               and pr not in in_flight]
    return [pr for _, pr in sorted(waiting, key=lambda waiting_pr: waiting_pr[0])]
