import json

import pytest

from github_orchestrator.change_detection.fake import ReviewDecision
from github_orchestrator.conversation import (
    ReviewState,
    ThreadActivity,
)
from github_orchestrator.domain import Side
from tests.builders import a_pr
from tests.pr_event_queue.support import (
    ci_failed,
    ci_succeeded,
    closed,
    decision_changed,
    disk_event_queue,
    pending_of,
)

THE_PR = a_pr(86, "acme/widgets")


def _queued_before(tmp_path, event_type, payload):
    directory = tmp_path / "queues" / "acme" / "widgets" / "86"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"1786380320406948000-17976-117-{event_type}.json").write_text(json.dumps(
        {"type": event_type, "repo": "acme/widgets", "pr": 86, "payload": payload}))
    [read] = pending_of(disk_event_queue(tmp_path / "queues"), THE_PR)
    return read


@pytest.mark.parametrize("event_type, payload, read", [
    ("ci-failed", {"check": "Run the pipeline and reconcile its results", "summary": None,
                   "html_url": "https://github.com/acme/widgets/actions/runs/1/job/2"},
     ci_failed("Run the pipeline and reconcile its results", None)),
    ("review-decision-changed", {"from": "REVIEW_REQUIRED", "to": None, "reviewer": None},
     decision_changed(ReviewDecision.REVIEW_REQUIRED, None, None)),
    ("review-decision-changed", {"from": "review-required", "to": "approved", "reviewer": "bob"},
     decision_changed(ReviewDecision.REVIEW_REQUIRED, ReviewDecision.APPROVED, "bob")),
    ("ci-succeeded", {"ci_status": "passing", "checks": [{"name": "lint", "passed": True},
                                                         {"name": "unit", "passed": True}]},
     ci_succeeded("lint", "unit")),
    ("pr-closed", {"merged": True}, closed(merged=True)),
    ("pr-closed", {"merged": False, "reason": "no-longer-relevant"},
     closed(merged=False, no_longer_relevant=True)),
])
def test_an_event_queued_before_the_typed_events_still_reads(tmp_path, event_type, payload,
                                                             read):
    assert _queued_before(tmp_path, event_type, payload) == read


def _thread_queued_before(tmp_path, thread):
    read = _queued_before(tmp_path, "thread-activity", {"threads": [thread]})
    assert isinstance(read, ThreadActivity)
    [found] = read.threads
    return found


def test_thread_activity_queued_before_the_typed_value_still_reads(tmp_path):
    found = _thread_queued_before(tmp_path, {
        "key": "PRRT_one", "kind": "review", "is_resolved": False,
        "resolved_by": None, "is_outdated": True, "path": "src/app.py",
        "line": None, "start_line": None, "original_line": 165,
        "original_start_line": None, "original_commit": "3f6f22a",
        "diff_side": "RIGHT", "subject_type": "LINE",
        "created_at": "2026-09-01T10:00:00Z",
        "comments": [{"id": 1, "author": "reviewer", "commit": "f" * 40,
                      "body": "please fix",
                      "created_at": "2026-09-01T10:00:00Z",
                      "updated_at": "2026-09-01T10:00:00Z"}],
        "new_comments": [{"id": 1}],
    })

    assert (found.key, found.kind, found.path, found.line, found.is_resolved) == (
        "PRRT_one", "review", "src/app.py", None, False)
    anchor = found.anchor
    assert (anchor.is_outdated, anchor.side, anchor.start_line, anchor.original_line,
            anchor.original_start_line, anchor.original_commit) == (
        True, Side.AFTER, None, 165, None, "3f6f22a")
    assert [(c.id, c.author, c.body, c.created_at, c.updated_at) for c in found.comments] == [
        (1, "reviewer", "please fix", "2026-09-01T10:00:00Z", "2026-09-01T10:00:00Z")]


def test_thread_activity_queued_before_with_no_cutoff_or_stale_threads_reads_without(tmp_path):
    read = _queued_before(tmp_path, "thread-activity", {"threads": []})

    assert read == ThreadActivity(threads=(), stale=(), cutoff=None)


def test_a_thread_queued_before_that_names_no_anchor_leaves_the_anchor_unsaid(tmp_path):
    found = _thread_queued_before(tmp_path, {"key": "PRRT_one", "kind": "review",
                                             "comments": []})

    assert found.anchor is None


def test_a_thread_queued_before_in_githubs_review_words_still_reads(tmp_path):
    found = _thread_queued_before(tmp_path, {
        "key": "PRRT_one", "kind": "review", "path": "src/app.py", "line": 12,
        "state": "COMMENTED",
        "comments": [{"id": 1, "author": "anna", "author_name": "Anna Example",
                      "review_state": "CHANGES_REQUESTED", "body": "please fix"}],
    })

    assert found.state is ReviewState.COMMENTED
    assert [c.review_state for c in found.comments] == [ReviewState.CHANGES_REQUESTED]


def test_a_thread_queued_before_in_the_kernels_and_conversation_words_still_reads(tmp_path):
    found = _thread_queued_before(tmp_path, {
        "key": "PRR_one", "kind": "review-summary", "state": "changes-requested",
        "is_outdated": False, "diff_side": "before",
        "comments": [{"id": 1, "author": "anna", "review_state": "changes-requested",
                      "body": "no"}],
    })

    assert (found.state, found.anchor.side, found.comments[0].review_state) == (
        ReviewState.CHANGES_REQUESTED, Side.BEFORE, ReviewState.CHANGES_REQUESTED)
