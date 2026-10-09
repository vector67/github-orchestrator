import logging
from contextlib import ExitStack
from dataclasses import replace

from github_orchestrator.conversation._application.ports import Ports, Update
from github_orchestrator.conversation._domain.apply import apply
from github_orchestrator.conversation._domain.conversation import (
    ENROLLED,
    OperationState,
    ReasonCode,
)
from github_orchestrator.conversation._domain.events import Posted
from github_orchestrator.conversation._domain.review import Review
from github_orchestrator.domain import Pr

log = logging.getLogger(__name__)


def send_reviews(pr: Pr, ports: Ports) -> None:
    for review in ports.records.reviews():
        if review.state != OperationState.PENDING:
            continue
        try:
            sent = _sent(ports, review)
            with ports.records.update_reviews() as held:
                held.save(sent)
        except Exception:
            log.exception("The review %s for %s failed; it will be retried "
                          "on the next drain", review.id, pr)


def _refused(review: Review, reason: str, drafts: tuple[str, ...],
             at: str) -> Review:
    return replace(review, state=OperationState.REFUSED, settled_at=at, reason=reason,
                   reason_code=ReasonCode.GITHUB_REJECTED, drafts=drafts)


def _sent(ports: Ports, review: Review) -> Review:
    """Every enrolled draft as one GitHub review, each one's lock held from
    the moment it is read until its `posted` is written, so nothing moves a
    draft between going out and being marked as gone."""
    enrolled = [conversation.key for conversation in ports.records.list()
                if conversation.state == ENROLLED]
    with ExitStack() as stack:
        updates: list[Update] = []
        for key in enrolled:
            update = stack.enter_context(ports.records.update(key))
            if (update.conversation is not None
                    and update.conversation.state == ENROLLED):
                updates.append(update)
        drafts = [update.conversation for update in updates
                  if update.conversation is not None]
        keys = tuple(draft.key for draft in drafts)
        at = ports.clock.now()
        head = ports.pull_requests.head_sha()
        if head is None:
            return _refused(review, "the pull request has no head to post "
                                    "against", keys, at)
        try:
            posted = ports.github.post_review(review.verdict, review.body,
                                              drafts, head)
        except Exception as exc:
            return _refused(review, str(exc) or type(exc).__name__, keys, at)
        for update, draft, one in zip(updates, drafts, posted.drafts,
                                      strict=True):
            update.conversation = apply(
                draft, Posted(comment=one.comment, github_node_id=one.key,
                              review=review.id), at).conversation
        return replace(review, state=OperationState.APPLIED, settled_at=at, drafts=keys,
                       posted_review=posted.id)
