import logging
from collections.abc import Callable

from github_orchestrator.change_detection import (
    BecameUnmergeable,
    CiFailed,
    PrClosed,
    ReviewRequested,
)
from github_orchestrator.conversation import ThreadActivity
from github_orchestrator.domain import Pr
from github_orchestrator.pr_event_queue.interface import (
    Launching,
    Queued,
    Response,
    Waiting,
)

log = logging.getLogger(__name__)

Pending = Callable[[], list[Queued]]

STOPPED_MID_RUN = "the agent manager stopped before the run ended"


def recovered(event: Queued) -> Queued:
    return event.retried(STOPPED_MID_RUN) if isinstance(event, CiFailed) else event


def waiting_of(pending: list[Queued], held: list[Queued]) -> Waiting:
    return Waiting(
        count=len(pending),
        closing=bool(pending) and isinstance(pending[0], PrClosed),
        failed_checks=frozenset(event.check for event in held
                                if isinstance(event, CiFailed) and event.check),
    )


def settling_of(held: list[Queued]) -> bool:
    return any(isinstance(event, ThreadActivity) for event in held)


def found_again(activity: ThreadActivity, held: list[Queued]) -> bool:
    return any(isinstance(event, ThreadActivity)
               and (event.threads, event.stale) == (activity.threads, activity.stale)
               for event in held)


def launch_of(event: Queued, is_author: bool) -> Launching | None:
    match event:
        case CiFailed() if is_author:
            return event
        case BecameUnmergeable() if is_author and event.rebase:
            return event
        case ReviewRequested():
            return event
    return None


def _launches(event: Queued, is_author: bool, agents_enabled: bool) -> bool:
    return agents_enabled and launch_of(event, is_author) is not None


def touches_the_run(event: Queued, is_author: bool, agents_enabled: bool) -> bool:
    return isinstance(event, PrClosed) or _launches(event, is_author, agents_enabled)


def respond(pr: Pr, event: Queued, *, is_author: bool, agents_enabled: bool,
            pending: Pending) -> Response:
    launch = launch_of(event, is_author)
    skipped = launch is not None and not agents_enabled
    if skipped:
        log.info("%s: agents disabled — skipping spawn for %s; draining event", pr, event.kind)
    return Response(
        event=event, launch=launch, skipped=skipped,
        more_failures_wait=isinstance(launch, CiFailed) and any(
            isinstance(waiting, CiFailed) for waiting in pending()))
