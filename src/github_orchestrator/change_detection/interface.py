import re
from collections.abc import Set
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import ClassVar, Protocol

from github_orchestrator.domain import Mention, Pr, Repo
from github_orchestrator.github import PullRequestState


@dataclass(frozen=True)
class Poll:
    state: PullRequestState
    polled_at: str
    my_last_comment_at: str | None = None
    comments_by_others: int = 0
    unresolved_thread_count: int | None = None
    review_requested: bool = False
    mentions: tuple[Mention, ...] | None = None
    mentioned: bool = False


class CiStatus(Enum):
    PASSING = "passing"
    FAILING = "failing"
    PENDING = "pending"


class ReviewDecision(Enum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes-requested"
    REVIEW_REQUIRED = "review-required"


class ReviewerStatus(Enum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes-requested"
    COMMENTED = "commented"
    DISMISSED = "dismissed"
    PENDING = "pending"


class Mergeability(Enum):
    CLEAN = "clean"
    CONFLICTS = "conflicts"
    BEHIND = "behind"
    BLOCKED = "blocked"
    CHECKS_FAILING = "checks-failing"
    UNKNOWN = "unknown"
    OTHER = "other"


class UnmergeableReason(Enum):
    CONFLICTS = "conflicts"
    BASE_UPDATED = "base-updated"
    BLOCKED = "blocked"


class MergeableReason(Enum):
    CONFLICTS_RESOLVED = "conflicts-resolved"
    APPROVED = "approved"
    CI_PASSED = "ci-passed"
    STATUS_RESOLVED = "status-resolved"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class _Event:
    kind: ClassVar[str]
    moves_head: ClassVar[bool] = False


@dataclass(frozen=True)
class CiSucceeded(_Event):
    checks: tuple[str, ...]
    kind: ClassVar[str] = "ci-succeeded"


@dataclass(frozen=True)
class CiFailed(_Event):
    check: str
    summary: str | None
    attempt: int = 0
    retry_reason: str | None = None
    kind: ClassVar[str] = "ci-failed"

    def retried(self, reason: str) -> "CiFailed":
        return CiFailed(check=self.check, summary=self.summary, attempt=self.attempt + 1,
                        retry_reason=reason)


@dataclass(frozen=True)
class BecameUnmergeable(_Event):
    reason: UnmergeableReason
    kind: ClassVar[str] = "became-unmergeable"

    @property
    def rebase(self) -> bool:
        return self.reason in (UnmergeableReason.CONFLICTS, UnmergeableReason.BASE_UPDATED)


@dataclass(frozen=True)
class BecameMergeable(_Event):
    reason: MergeableReason
    kind: ClassVar[str] = "became-mergeable"


@dataclass(frozen=True)
class ReviewDecisionChanged(_Event):
    before: ReviewDecision | None
    after: ReviewDecision | None
    reviewer: str | None
    kind: ClassVar[str] = "review-decision-changed"


@dataclass(frozen=True)
class PushedSinceReview(_Event):
    commits: int
    force_push: bool
    kind: ClassVar[str] = "pushed-since-review"

    @property
    def pushes(self) -> str:
        if self.force_push:
            return "Author force-pushed since your review"
        noun = "commit" if self.commits == 1 else "commits"
        return f"Author pushed {self.commits} {noun} since your review"


@dataclass(frozen=True)
class HeadChanged(_Event):
    previous: str
    head: str
    force_push: bool
    away_seconds: int | None
    kind: ClassVar[str] = "head-changed"
    moves_head: ClassVar[bool] = True


@dataclass(frozen=True)
class ReviewRequested(_Event):
    title: str | None
    url: str | None
    kind: ClassVar[str] = "review-requested"


@dataclass(frozen=True)
class PrClosed(_Event):
    merged: bool
    no_longer_relevant: bool = False
    kind: ClassVar[str] = "pr-closed"


PrEvent = (CiSucceeded | CiFailed | BecameUnmergeable | BecameMergeable
           | ReviewDecisionChanged | PushedSinceReview | HeadChanged | ReviewRequested
           | PrClosed)


@dataclass(frozen=True)
class SinceReview:
    sha: str | None
    commits: int
    force_push: bool
    reviews: int
    comments: int
    resolved: int


@dataclass(frozen=True)
class Facts:
    title: str | None
    url: str | None
    author: str | None
    branch: str | None
    base_branch: str | None
    head_sha: str | None
    is_author: bool | None
    changed_files: int | None
    additions: int
    deletions: int
    ci_status: CiStatus | None
    mergeable: bool | None
    needs_rebase: bool
    review_decision: ReviewDecision | None
    failed_checks: tuple[str, ...]
    checks_done: int
    checks_total: int
    approved_by: tuple[str, ...]
    changes_requested_by: tuple[str, ...]
    pending_reviewers: tuple[str, ...]
    unresolved_threads: int | None
    my_review: ReviewerStatus | None
    detailed_reviewer: str | None
    is_detailed_reviewer: bool
    last_event_at: str | None
    review_ready_at: str | None
    since_review: SinceReview | None
    draft: bool
    merge_state: Mergeability | None
    viewer_requested: bool
    ended: bool
    mentions: tuple[Mention, ...]
    mentioned: bool
    my_review_at: str | None
    polled_at: str | None

    @property
    def ci_passed(self) -> bool:
        return self.ci_status is CiStatus.PASSING

    @property
    def ticket(self) -> str | None:
        match = re.search(r"[A-Za-z]+-[0-9]+", self.branch or "")
        return match.group(0) if match else None


@dataclass(frozen=True)
class Stored:
    pr: Pr
    facts: Facts | None
    problem: str | None


class ChangeDetection(Protocol):
    def advance(self, pr: Pr, poll: Poll, pending_ci_checks: set[str]) -> list[PrEvent]: ...

    def ended(self, *, still_open: bool, merged: bool) -> PrClosed: ...

    def facts(self, pr: Pr) -> Facts | None: ...

    def tracked(self) -> list[Pr]: ...

    def stored(self) -> list[Stored]: ...

    def closing(self, pr: Pr) -> bool: ...

    def close(self, pr: Pr) -> None: ...

    def forget(self, pr: Pr) -> bool: ...

    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]: ...
