from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, Protocol

from github_orchestrator.domain import Location, Pr, Repo, Side

_PASSED = frozenset({"success", "skipped", "neutral"})
_FAILED = frozenset({"failure", "cancelled", "timed_out", "action_required", "stale"})


class GhError(RuntimeError):
    pass


Whose = Literal["author", "review-requested", "mentions"]


class ReviewState(Enum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    COMMENTED = "COMMENTED"
    DISMISSED = "DISMISSED"
    PENDING = "PENDING"


def review_state_of(word: object) -> ReviewState | None:
    return next((state for state in ReviewState if state.value == word), None)


class CommentKind(Enum):
    REVIEW = "review"
    ISSUE = "issue"
    REVIEW_SUMMARY = "review-summary"


class Verdict(Enum):
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    COMMENT = "COMMENT"

    def takes(self, body: str | None) -> bool:
        return self is Verdict.APPROVE or bool((body or "").strip())


@dataclass(frozen=True)
class Check:
    name: str
    status: str | None = None
    conclusion: str | None = None
    html_url: str | None = None
    summary: str | None = None

    @property
    def done(self) -> bool:
        return self.status == "completed"

    @property
    def passed(self) -> bool:
        return self.conclusion in _PASSED

    @property
    def failed(self) -> bool:
        return self.conclusion in _FAILED


@dataclass(frozen=True)
class Review:
    author: str | None
    state: ReviewState | None
    submitted_at: str | None = None
    commit_id: str | None = None

    @property
    def approves(self) -> bool:
        return self.state is ReviewState.APPROVED

    @property
    def requests_changes(self) -> bool:
        return self.state is ReviewState.CHANGES_REQUESTED


@dataclass(frozen=True)
class PushEvent:
    event: str
    at: str

    @property
    def is_force_push(self) -> bool:
        return self.event == "head_ref_force_pushed"

    @property
    def is_commit(self) -> bool:
        return self.event == "committed"


@dataclass(frozen=True)
class PullRequestState:
    title: str | None = None
    url: str | None = None
    author: str | None = None
    branch: str | None = None
    base_branch: str | None = None
    head_sha: str | None = None
    body: str = ""
    draft: bool = False
    changed_files: int | None = None
    additions: int | None = None
    deletions: int | None = None
    mergeable: bool = False
    mergeable_state: str = "unknown"
    checks: tuple[Check, ...] = ()
    reviews: tuple[Review, ...] = ()
    review_decision: str | None = None
    pending_reviewers: tuple[str, ...] = ()
    ready_for_review_at: str | None = None
    push_events: tuple[PushEvent, ...] = ()

    @property
    def conflicts(self) -> bool:
        return self.mergeable_state == "dirty"

    @property
    def behind_base(self) -> bool:
        return self.mergeable_state == "behind"

    @property
    def blocked(self) -> bool:
        return self.mergeable_state == "blocked"

    @property
    def checks_failing(self) -> bool:
        return self.mergeable_state == "unstable"

    @property
    def merges_cleanly(self) -> bool:
        return self.mergeable_state == "clean"

    @property
    def mergeability_known(self) -> bool:
        return self.mergeable_state != "unknown"

    @property
    def approved(self) -> bool:
        return self.review_decision == "APPROVED"

    @property
    def changes_requested(self) -> bool:
        return self.review_decision == "CHANGES_REQUESTED"

    @property
    def review_required(self) -> bool:
        return self.review_decision == "REVIEW_REQUIRED"


@dataclass(frozen=True)
class Relevance:
    state: str | None
    viewer_did_author: bool
    viewer_reviewed: bool

    @property
    def is_open(self) -> bool:
        return self.state == "OPEN"

    @property
    def merged(self) -> bool:
        return self.state == "MERGED"


@dataclass(frozen=True)
class ThreadComment:
    id: int | None = None
    author: str = ""
    body: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    author_name: str = ""
    review_state: ReviewState | None = None


@dataclass(frozen=True)
class ThreadAnchor:
    is_outdated: bool = False
    side: Side | None = None
    start_line: int | None = None
    start_side: Side | None = None
    original_line: int | None = None
    original_start_line: int | None = None
    original_commit: str | None = None


@dataclass(frozen=True)
class Thread:
    key: str
    kind: CommentKind
    comments: tuple[ThreadComment, ...] = ()
    anchor: ThreadAnchor | None = None
    path: str | None = None
    line: int | None = None
    is_resolved: bool | None = None
    resolved_by: str | None = None
    state: ReviewState | None = None

    @property
    def is_review_summary(self) -> bool:
        return self.kind is CommentKind.REVIEW_SUMMARY


@dataclass(frozen=True)
class PostedComment:
    comment: ThreadComment
    key: str | None


@dataclass(frozen=True)
class ReviewComment:
    path: str | None
    comment: ThreadComment


@dataclass(frozen=True)
class SentReview:
    id: int | None
    comments: tuple[ReviewComment, ...]


class PullRequests(Protocol):
    def search(self, repos: Collection[Repo], whose: Whose) -> list[Pr]: ...

    def prefetch(self, prs: Sequence[Pr]) -> None: ...

    def pr_state(self, pr: Pr) -> PullRequestState: ...

    def head_branch(self, pr: Pr) -> str | None: ...

    def is_closed(self, pr: Pr) -> bool | None: ...

    def close(self, pr: Pr) -> str | None: ...

    def relevance(self, pr: Pr) -> Relevance | None: ...

    def url(self, pr: Pr) -> str: ...

    def commit_url(self, repo: Repo, sha: str) -> str: ...


class Threads(Protocol):
    def threads(self, pr: Pr) -> list[Thread]: ...

    def reply_to_thread(self, key: str, body: str) -> ThreadComment | None: ...

    def comment_on_pr(self, pr: Pr, body: str) -> PostedComment: ...

    def resolve_thread(self, key: str) -> None: ...

    def unresolve_thread(self, key: str) -> None: ...

    def react(self, repo: Repo, comment_id: int) -> None: ...

    def delete_comment(self, pr: Pr, kind: CommentKind,
                       comment_id: int) -> None: ...

    def comment_exists(self, pr: Pr, kind: CommentKind,
                       comment_id: int) -> bool | None: ...

    def comment_url(self, pr: Pr, kind: CommentKind, comment_id: int) -> str: ...

    def too_long(self, body: str) -> str | None: ...


class Reviews(Protocol):
    def post_review_comment(self, pr: Pr, head: str, location: Location,
                            body: str) -> ThreadComment: ...

    def post_review(self, pr: Pr, head: str, verdict: Verdict, body: str | None,
                    comments: Sequence[tuple[Location, str]]) -> SentReview: ...


@dataclass(frozen=True)
class Listed:
    repo: Repo
    can_push: bool
    has_my_prs: bool
    default_branch: str


class Access(Protocol):
    def active_account(self) -> str | None: ...

    def check_login(self, account: str) -> str | None: ...

    def scopes(self, account: str) -> tuple[str, ...]: ...

    def repos_of(self, account: str) -> list[Listed] | str: ...

    def repo_of(self, account: str, repo: Repo) -> Listed | str: ...

    def check_access(self, account: str, repo: Repo) -> str | None: ...

    def clone(self, repo: Repo, into: Path) -> str | None: ...
