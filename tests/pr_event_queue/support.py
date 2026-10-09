from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from github_orchestrator.change_detection import (
    BecameMergeable,
    BecameUnmergeable,
    CiFailed,
    CiSucceeded,
    HeadChanged,
    PrClosed,
    PrEvent,
    PushedSinceReview,
    ReviewDecisionChanged,
    ReviewRequested,
)
from github_orchestrator.change_detection.fake import (
    MergeableReason,
    ReviewDecision,
    UnmergeableReason,
)
from github_orchestrator.conversation import ThreadActivity
from github_orchestrator.domain import Pr
from github_orchestrator.github import PullRequestState
from github_orchestrator.notifications import Settling
from github_orchestrator.pr_event_queue import Intake, Queues, Worklist
from github_orchestrator.pr_event_queue.fake import Queue
from github_orchestrator.wiring import (
    ChangeDetectionWiring,
    PrEventQueueWiring,
    WouldEnqueueWiring,
    wire,
)
from tests.builders import a_pr
from tests.change_detection.support import ACCOUNT
from tests.conftest import Fake, clocks_of
from tests.conversation.support import fake_conversation_managers, on_github, said

Queued = PrEvent | ThreadActivity


class PrEventQueue(Intake, Worklist, Queues, Protocol):
    pass


def disk_event_queue(queues_dir: Path) -> PrEventQueue:
    queue: PrEventQueue = wire(PrEventQueueWiring(queues_dir)).get(Intake)
    return queue


def would_intake(state_dir: Path, said: list[str], *, agents_enabled: bool = True) -> Intake:
    intake: Intake = wire(
        ChangeDetectionWiring(state_dir, ACCOUNT, 60),
        clocks_of(),
        WouldEnqueueWiring(said.append, agents_enabled),
    ).get(Intake)
    return intake


def event_queue_provider(instance: PrEventQueue) -> Fake:
    return Fake(instance, Intake, Worklist, Queues, Settling)


def queue_of(event_queue: PrEventQueue, pr: Pr) -> Queue:
    return next((listed for listed in event_queue.queues() if listed.pr == pr), Queue(pr, ()))


def pending_of(event_queue: PrEventQueue, pr: Pr) -> list[Queued]:
    return [entry.event for entry in queue_of(event_queue, pr).pending if entry.event is not None]


def in_flight_of(event_queue: PrEventQueue, pr: Pr) -> list[Queued]:
    return [entry.event for entry in queue_of(event_queue, pr).in_flight
            if entry.event is not None]


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def now() -> datetime:
    return datetime.now(timezone.utc)


def kinds(items: list[Queued]) -> list[str]:
    return [item.kind for item in items]


def ci_failed(check: str = "lint", summary: str | None = None, attempt: int = 0) -> CiFailed:
    return CiFailed(check=check, summary=summary, attempt=attempt)


def ci_succeeded(*checks: str) -> CiSucceeded:
    return CiSucceeded(checks=checks)


def unmergeable(reason: UnmergeableReason = UnmergeableReason.CONFLICTS) -> BecameUnmergeable:
    return BecameUnmergeable(reason)


def mergeable(reason: MergeableReason = MergeableReason.APPROVED) -> BecameMergeable:
    return BecameMergeable(reason)


def decision_changed(before: ReviewDecision | None = ReviewDecision.REVIEW_REQUIRED,
                     after: ReviewDecision | None = ReviewDecision.APPROVED,
                     reviewer: str | None = "alice") -> ReviewDecisionChanged:
    return ReviewDecisionChanged(before=before, after=after, reviewer=reviewer)


def pushed(commits: int = 1, force_push: bool = False) -> PushedSinceReview:
    return PushedSinceReview(commits=commits, force_push=force_push)


def head_moved(previous: str = "a", head: str = "b") -> HeadChanged:
    return HeadChanged(previous=previous, head=head, force_push=False, away_seconds=None)


def review_requested(title: str | None = "t", url: str | None = None) -> ReviewRequested:
    return ReviewRequested(title=title, url=url)


def closed(merged: bool = True, no_longer_relevant: bool = False) -> PrClosed:
    return PrClosed(merged=merged, no_longer_relevant=no_longer_relevant)


POLLED_PR = a_pr(1, "acme/widgets")
CUTOFF = "2026-09-24T10:00:00Z"


def activity(*keys: str, stale: tuple[str, ...] = (), cutoff: str = CUTOFF) -> ThreadActivity:
    moment = datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    conversation_managers = fake_conversation_managers(clock=lambda: moment + timedelta(seconds=5))
    conversations = conversation_managers.of(POLLED_PR)
    for key in stale:
        on_github(conversation_managers.github, key, said(1, "please fix"), pr=POLLED_PR)
    conversations.poll(PullRequestState()).commit()
    for key in stale:
        conversation_managers.github.resolve_thread(key)
    for key in keys:
        on_github(conversation_managers.github, key, said(1, "please fix"), pr=POLLED_PR)
    found = conversations.poll(PullRequestState()).activity
    assert found is not None
    return found
