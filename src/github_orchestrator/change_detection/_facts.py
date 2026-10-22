from typing import Any

from github_orchestrator.change_detection._rules import is_closing
from github_orchestrator.change_detection._stored import Words, mentions_of, words_of
from github_orchestrator.change_detection._unmergeable import REBASE_STATES
from github_orchestrator.change_detection.interface import (
    Facts,
    Mergeability,
    ReviewerStatus,
    SinceReview,
)
from github_orchestrator.domain import CiCheck


def _reviewers_who(words: Words, status: ReviewerStatus) -> tuple[str, ...]:
    return tuple(login for login, given in words.reviewers.items() if given is status)


def _pending_reviewers(snapshot: dict[str, Any]) -> list[str]:
    return list(snapshot.get("pending_reviewers", []))


def _unresolved_threads(snapshot: dict[str, Any]) -> int | None:
    count = snapshot.get("unresolved_thread_count")
    return count if isinstance(count, int) else None


def _since_review(snapshot: dict[str, Any]) -> SinceReview | None:
    if not snapshot.get("review_anchor_at"):
        return None
    return SinceReview(
        sha=_text(snapshot, "review_anchor_sha"),
        commits=snapshot.get("since_anchor_commits", 0),
        force_push=bool(snapshot.get("since_anchor_force_push")),
        reviews=snapshot.get("since_anchor_reviews", 0),
        comments=snapshot.get("since_anchor_comments", 0),
        resolved=snapshot.get("since_anchor_resolved", 0),
    )


def _check(check: dict[str, Any]) -> CiCheck:
    return CiCheck(name=check["name"], passed=bool(check.get("passed")),
                   failed=bool(check.get("failed")), done=bool(check.get("done")),
                   url=check.get("html_url"), summary=check.get("summary"))


def _text(snapshot: dict[str, Any], key: str) -> str | None:
    value = snapshot.get(key)
    return value if isinstance(value, str) else None


def _role(snapshot: dict[str, Any]) -> bool | None:
    said = snapshot.get("is_author")
    return said if isinstance(said, bool) else None


def _requested(snapshot: dict[str, Any], account: str) -> bool:
    return account in _pending_reviewers(snapshot) or snapshot.get("review_requested") is True


def _mergeable(snapshot: dict[str, Any], words: Words) -> bool | None:
    if "mergeable" not in snapshot or words.mergeability is Mergeability.UNKNOWN:
        return None
    return bool(snapshot["mergeable"])


def facts_of(snapshot: dict[str, Any], account: str) -> Facts:
    checks = snapshot.get("checks", [])
    words = words_of(snapshot)
    return Facts(
        title=_text(snapshot, "title"),
        url=_text(snapshot, "url"),
        author=_text(snapshot, "pr_author"),
        branch=_text(snapshot, "branch"),
        base_branch=_text(snapshot, "base_branch"),
        head_sha=_text(snapshot, "head_sha"),
        is_author=_role(snapshot),
        changed_files=snapshot.get("changed_files", 0),
        additions=snapshot.get("additions") or 0,
        deletions=snapshot.get("deletions") or 0,
        commits=snapshot.get("commits"),
        created_at=_text(snapshot, "created_at"),
        ci_status=words.ci,
        mergeable=_mergeable(snapshot, words),
        needs_rebase=words.mergeability in REBASE_STATES,
        review_decision=words.decision,
        checks=tuple(_check(c) for c in checks),
        approved_by=_reviewers_who(words, ReviewerStatus.APPROVED),
        changes_requested_by=_reviewers_who(words, ReviewerStatus.CHANGES_REQUESTED),
        pending_reviewers=tuple(_pending_reviewers(snapshot)),
        unresolved_threads=_unresolved_threads(snapshot),
        my_review=words.reviewers.get(account),
        detailed_reviewer=_text(snapshot, "detailed_reviewer"),
        is_detailed_reviewer=bool(snapshot.get("is_detailed_reviewer", False)),
        last_event_at=_text(snapshot, "last_event_at"),
        review_ready_at=_text(snapshot, "review_ready_at"),
        since_review=_since_review(snapshot),
        draft=bool(snapshot.get("draft", False)),
        merge_state=words.mergeability,
        viewer_requested=_requested(snapshot, account),
        ended=is_closing(snapshot),
        mentions=mentions_of(snapshot),
        mentioned=snapshot.get("mentioned") is True,
        my_review_at=_text(snapshot, "my_review_at"),
        my_review_sha=_text(snapshot, "my_review_sha"),
        force_pushed_at=_text(snapshot, "force_pushed_at"),
        polled_at=_text(snapshot, "last_poll_timestamp"),
    )

