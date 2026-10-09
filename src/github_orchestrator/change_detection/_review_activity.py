from typing import Any

from github_orchestrator.github import PullRequestState

_EMPTY = {
    "review_anchor_at": None,
    "review_anchor_sha": None,
    "since_anchor_commits": 0,
    "since_anchor_force_push": False,
    "since_anchor_comments": 0,
    "since_anchor_reviews": 0,
    "since_anchor_resolved": 0,
}


def compute_review_activity(
    *,
    account: str,
    is_author: bool,
    state: PullRequestState,
    my_last_comment_at: str | None,
    comments_by_others: int,
    unresolved_thread_count: int | None,
    old_state: dict[str, Any] | None,
) -> dict[str, Any]:
    if is_author:
        return dict(_EMPTY)

    old = old_state or {}
    prev_at = old.get("review_anchor_at")
    prev_sha = old.get("review_anchor_sha")

    threads: list[tuple[str, str | None]] = []
    if prev_at:
        threads.append((prev_at, prev_sha))
    for r in state.reviews:
        if r.author == account and r.submitted_at:
            threads.append((r.submitted_at, r.commit_id))
    if my_last_comment_at:
        threads.append((my_last_comment_at, state.head_sha))

    if not threads:
        return dict(_EMPTY)

    anchor_at, anchor_sha = max(threads, key=lambda t: t[0] or "")
    acted_this_poll = prev_at is None or anchor_at > prev_at

    commits = 0
    force_push = False
    for ev in state.push_events:
        at = ev.at or ""
        if at <= anchor_at:
            continue
        if ev.is_force_push:
            force_push = True
        elif ev.is_commit:
            commits += 1

    reviews_since = sum(
        1 for r in state.reviews
        if r.author and r.author != account
        and (r.approves or r.requests_changes)
        and (r.submitted_at or "") > anchor_at
    )

    if acted_this_poll:
        comments_since = 0
        resolved_since = 0
    else:
        comments_since = old.get("since_anchor_comments", 0) + comments_by_others
        resolved_since = old.get("since_anchor_resolved", 0)
        prev_unresolved = old.get("unresolved_thread_count")
        if (
            prev_unresolved is not None
            and unresolved_thread_count is not None
            and unresolved_thread_count < prev_unresolved
        ):
            resolved_since += prev_unresolved - unresolved_thread_count

    return {
        "review_anchor_at": anchor_at,
        "review_anchor_sha": anchor_sha,
        "since_anchor_commits": commits,
        "since_anchor_force_push": force_push,
        "since_anchor_comments": comments_since,
        "since_anchor_reviews": reviews_since,
        "since_anchor_resolved": resolved_since,
    }
