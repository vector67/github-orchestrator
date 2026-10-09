from dataclasses import dataclass
from enum import Enum

from github_orchestrator.conversation._domain.conversation import (
    IN_FLIGHT,
    OperationState,
    ReasonCode,
)


class Verdict(Enum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request-changes"
    COMMENT = "comment"


@dataclass(frozen=True)
class Review:
    """One review sent to GitHub, or on its way: the pull request's own
    operation, where every other operation belongs to a thread.

    `drafts` are the threads it carried, in the order they were sent, and
    `posted_review` is GitHub's id for it once it was taken.
    """

    id: str
    verdict: Verdict
    body: str | None = None
    state: OperationState = OperationState.PENDING
    requested_at: str | None = None
    settled_at: str | None = None
    reason: str | None = None
    reason_code: ReasonCode | None = None
    drafts: tuple[str, ...] = ()
    posted_review: int | None = None

    @property
    def in_flight(self) -> bool:
        return self.state in IN_FLIGHT

