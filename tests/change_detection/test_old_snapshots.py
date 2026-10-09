from github_orchestrator.change_detection import (
    CiStatus,
    ReviewerStatus,
    SinceReview,
)
from github_orchestrator.change_detection.fake import ReviewDecision
from tests.builders import a_pr
from tests.change_detection.support import (
    PR,
    REPO,
    disk_change_detection,
    poll,
    pr_state,
    remember,
)

THE_PR = a_pr(PR, REPO)

WRITTEN_BY_THE_LAST_RELEASE = {
    "repo": REPO, "pr": PR, "title": "Add widgets", "url": "https://github.com/acme/widgets/pull/7",
    "branch": "PROJ-7-widgets", "base_branch": "main", "pr_author": "alice",
    "changed_files": 4, "additions": 12, "deletions": 3, "head_sha": "sha2",
    "mergeable": True, "mergeable_state": "blocked", "draft": False,
    "last_poll_timestamp": "2026-09-23T11:00:00Z", "ci_status": "pending",
    "review_ready_at": "2026-09-20T08:00:00Z",
    "checks": [
        {"name": "tests", "conclusion": "failure", "status": "completed",
         "html_url": "https://ci/tests", "summary": "1 failed"},
        {"name": "e2e", "conclusion": None, "status": "queued", "html_url": None, "summary": None},
    ],
    "review_decision": "REVIEW_REQUIRED", "latest_reviewer": "octocat",
    "reviewer_status": {"octocat": "APPROVED", "bob": "CHANGES_REQUESTED"},
    "pending_reviewers": ["erin"], "unresolved_thread_count": 2, "is_author": False,
    "review_anchor_at": "2026-09-21T00:00:00Z", "review_anchor_sha": "sha1",
    "since_anchor_commits": 2, "since_anchor_force_push": False, "since_anchor_comments": 5,
    "since_anchor_reviews": 1, "since_anchor_resolved": 1,
    "detailed_reviewer": "octocat", "is_detailed_reviewer": True,
    "thread_snapshot": {"PRRT_one": {"comments": [1, 2]}},
    "ci_failure_handled": {"tests": "sha2"}, "last_event_at": "2026-09-23T10:00:00Z",
}


def test_a_snapshot_the_last_release_wrote_reads_as_the_same_facts(tmp_path):
    remember(tmp_path, THE_PR, WRITTEN_BY_THE_LAST_RELEASE)

    facts = disk_change_detection(tmp_path).facts(THE_PR)

    assert facts is not None
    assert (facts.title, facts.author, facts.branch, facts.base_branch, facts.head_sha) == (
        "Add widgets", "alice", "PROJ-7-widgets", "main", "sha2")
    assert (facts.changed_files, facts.additions, facts.deletions) == (4, 12, 3)
    assert (facts.ci_status, facts.mergeable, facts.review_decision) == (
        CiStatus.PENDING, True, ReviewDecision.REVIEW_REQUIRED)
    assert facts.failed_checks == ("tests",)
    assert (facts.checks_done, facts.checks_total) == (1, 2)
    assert (facts.approved_by, facts.changes_requested_by, facts.pending_reviewers) == (
        ("octocat",), ("bob",), ("erin",))
    assert (facts.unresolved_threads, facts.my_review, facts.is_author) == (2, ReviewerStatus.APPROVED, False)
    assert (facts.detailed_reviewer, facts.is_detailed_reviewer) == ("octocat", True)
    assert (facts.last_event_at, facts.review_ready_at) == (
        "2026-09-23T10:00:00Z", "2026-09-20T08:00:00Z")
    assert facts.since_review == SinceReview(sha="sha1", commits=2, force_push=False, reviews=1,
                                             comments=5, resolved=1)
    assert (facts.draft, facts.merge_state.value, facts.viewer_requested, facts.ended) == (
        False, "blocked", False, False)
    assert facts.polled_at == "2026-09-23T11:00:00Z"


def test_a_conflict_the_last_release_wrote_in_githubs_words_still_reads_as_a_conflict(tmp_path):
    remember(tmp_path, THE_PR, {**WRITTEN_BY_THE_LAST_RELEASE, "mergeable_state": "dirty",
                                "ci_status": "success", "review_decision": "APPROVED"})
    detection = disk_change_detection(tmp_path)

    facts = detection.facts(THE_PR)
    events = detection.advance(THE_PR, poll(pr_state(
        author="alice", head_sha="sha2", mergeable_state="clean",
        review_decision="APPROVED")), set())

    assert (facts.merge_state.value, facts.ci_status, facts.review_decision) == (
        "conflicts", CiStatus.PASSING, ReviewDecision.APPROVED)
    assert [event.reason.value for event in events
            if event.kind == "became-mergeable"] == ["conflicts-resolved"]
    assert "review-decision-changed" not in [event.kind for event in events]


def test_a_snapshot_from_before_most_fields_existed_reads_with_their_defaults(tmp_path):
    remember(tmp_path, THE_PR, {"title": "Old", "branch": "fix-it", "ci_status": "pending"})

    facts = disk_change_detection(tmp_path).facts(THE_PR)

    assert (facts.title, facts.branch, facts.url, facts.head_sha) == ("Old", "fix-it", None, None)
    assert (facts.additions, facts.deletions, facts.changed_files) == (0, 0, 0)
    assert (facts.mergeable, facts.review_decision, facts.unresolved_threads) == (None, None, None)
    assert (facts.failed_checks, facts.checks_done, facts.checks_total) == ((), 0, 0)
    assert facts.is_author is None
    assert facts.since_review is None
    assert (facts.ci_status, facts.draft, facts.merge_state, facts.viewer_requested) == (
        CiStatus.PENDING, False, None, False)
    assert facts.polled_at is None


def test_a_snapshot_from_before_mentions_were_kept_reads_as_never_mentioned(tmp_path):
    remember(tmp_path, THE_PR, WRITTEN_BY_THE_LAST_RELEASE)

    facts = disk_change_detection(tmp_path).facts(THE_PR)

    assert (facts.mentions, facts.mentioned, facts.my_review_at) == ((), False, None)


def test_a_closing_mark_on_a_pr_never_polled_still_reads_as_known(tmp_path):
    remember(tmp_path, THE_PR, {"pending_teardown": True})

    detection = disk_change_detection(tmp_path)

    assert detection.facts(THE_PR) is not None
    assert detection.closing(THE_PR) is True


def test_a_snapshot_from_before_the_review_request_was_kept_asks_for_no_review(tmp_path):
    remember(tmp_path, THE_PR, WRITTEN_BY_THE_LAST_RELEASE)

    events = disk_change_detection(tmp_path).advance(THE_PR, poll(pr_state(
        author="alice", head_sha="sha2", mergeable_state="blocked"), review_requested=True), set())

    assert "review-requested" not in [event.kind for event in events]
