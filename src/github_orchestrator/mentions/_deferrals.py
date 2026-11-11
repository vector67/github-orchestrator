from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime

from github_orchestrator.board_api.interface import MentionDeferral, PrMilestone
from github_orchestrator.domain import Pr
from github_orchestrator.mentions.interface import PrNow


def lapsed(deferral: MentionDeferral, now: datetime) -> bool:
    return deferral.until_at is not None and now >= _moment(deferral.until_at)


def over(deferral: MentionDeferral, *, now: datetime, prs: Mapping[Pr, PrNow],
         thread_spoken: Iterable[str], pr_spoken: Iterable[str]) -> bool:
    if _since(deferral, thread_spoken):
        return True
    if deferral.until_pr is None:
        return lapsed(deferral, now)
    awaited = prs.get(deferral.until_pr.pr)
    if awaited is None:
        return False
    match deferral.until_pr.state:
        case PrMilestone.APPROVED:
            return awaited.approved and not awaited.closed
        case PrMilestone.NEW_COMMIT:
            return (not awaited.closed and deferral.head_sha is not None
                    and awaited.head_sha != deferral.head_sha)
        case PrMilestone.MERGED:
            return awaited.merged
        case PrMilestone.CLOSED:
            return awaited.closed and not awaited.merged
        case PrMilestone.ANY_ACTIVITY:
            return awaited.closed or _since(
                deferral, [*pr_spoken, *filter(None, [awaited.last_event_at])])
        case _:
            return False


def seen(deferral: MentionDeferral, prs: Mapping[Pr, PrNow]) -> MentionDeferral:
    if deferral.until_pr is None or deferral.head_sha is not None:
        return deferral
    awaited = prs.get(deferral.until_pr.pr)
    if awaited is None or deferral.until_pr.state is not PrMilestone.NEW_COMMIT:
        return deferral
    return replace(deferral, head_sha=awaited.head_sha)


def _since(deferral: MentionDeferral, moments: Iterable[str]) -> bool:
    deferred_at = _moment(deferral.deferred_at)
    return any(_moment(moment) > deferred_at for moment in moments)


def _moment(iso: str) -> datetime:
    moment = datetime.fromisoformat(iso)
    return moment.astimezone() if moment.tzinfo is None else moment
