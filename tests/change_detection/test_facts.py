from github_orchestrator.change_detection import (
    CiStatus,
    ReviewerStatus,
    SinceReview,
)
from github_orchestrator.change_detection.fake import ReviewDecision
from github_orchestrator.domain import Mention
from github_orchestrator.github import ReviewState
from github_orchestrator.github.fake import Check, PushEvent, Review
from tests.builders import a_pr
from tests.change_detection.support import (
    ACCOUNT,
    PR,
    REPO,
    failing,
    passing,
    poll,
    pr_state,
)

THE_PR = a_pr(PR, REPO)

ASKED = Mention(author="anna", at="2026-09-20T00:00:00Z", kind="issue", thread="IC_1",
                comment_id=11, body="@octocat?", answered=False)


def test_a_polled_pr_says_what_github_said_of_it(detection):
    detection.advance(THE_PR, poll(pr_state(changed_files=3, additions=40, deletions=7)), set())

    facts = detection.facts(THE_PR)

    assert facts is not None
    assert (facts.title, facts.url, facts.author) == (
        "Add widgets", "https://github.com/acme/widgets/pull/7", ACCOUNT)
    assert (facts.branch, facts.base_branch, facts.head_sha) == ("PROJ-7-widgets", "main", "sha0")
    assert (facts.changed_files, facts.additions, facts.deletions) == (3, 40, 7)
    assert (facts.ci_status, facts.mergeable, facts.review_decision) == (
        CiStatus.PASSING, True, ReviewDecision.REVIEW_REQUIRED)
    assert facts.is_author is True


def test_the_checks_are_summed_up_as_failed_names_and_how_many_are_done(detection):
    running = Check("e2e", "in_progress", None, None, None)
    detection.advance(THE_PR, poll(pr_state(
        checks=(failing("tests"), passing("lint"), failing("types"), running))), set())

    facts = detection.facts(THE_PR)

    assert facts.failed_checks == ("tests", "types")
    assert (facts.checks_done, facts.checks_total) == (3, 4)


def test_the_reviewers_are_grouped_by_their_verdict_and_mine_is_picked_out(detection):
    detection.advance(THE_PR, poll(pr_state(
        author="alice",
        reviews=(Review("bob", ReviewState.APPROVED, "2026-09-20T00:00:00Z", "sha0"),
                 Review("carol", ReviewState.CHANGES_REQUESTED, "2026-09-20T00:01:00Z", "sha0"),
                 Review(ACCOUNT, ReviewState.COMMENTED, "2026-09-20T00:02:00Z", "sha0"),
                 Review("dave", ReviewState.APPROVED, "2026-09-20T00:03:00Z", "sha0")),
        pending_reviewers=("erin",))), set())

    facts = detection.facts(THE_PR)

    assert facts.approved_by == ("bob", "dave")
    assert facts.changes_requested_by == ("carol",)
    assert facts.pending_reviewers == ("erin",)
    assert facts.my_review is ReviewerStatus.COMMENTED
    assert facts.is_author is False


def test_github_s_merge_states_read_in_the_snapshot_s_words(detection):
    states = {}
    for state in ("clean", "dirty", "behind", "blocked", "unstable", "draft"):
        detection.advance(THE_PR, poll(pr_state(mergeable_state=state)), set())
        states[state] = detection.facts(THE_PR).merge_state.value

    assert states == {
        "clean": "clean", "dirty": "conflicts", "behind": "behind", "blocked": "blocked",
        "unstable": "checks-failing", "draft": "other"}


def test_a_pr_that_conflicts_with_or_is_behind_its_base_needs_a_rebase_even_with_ci_failing(detection):
    needs = {}
    for state in ("dirty", "behind", "clean", "blocked"):
        detection.advance(THE_PR, poll(pr_state(checks=(failing(),), mergeable_state=state)), set())
        needs[state] = detection.facts(THE_PR).needs_rebase

    assert needs == {"dirty": True, "behind": True, "clean": False, "blocked": False}


def test_a_draft_says_so(detection):
    drafts = {}
    for draft in (True, False):
        detection.advance(THE_PR, poll(pr_state(draft=draft)), set())
        drafts[draft] = detection.facts(THE_PR).draft

    assert drafts == {True: True, False: False}


def test_the_facts_say_whether_i_am_on_the_requested_list_right_now(detection):
    requested = {}
    for pending in ((ACCOUNT, "erin"), ("erin",)):
        detection.advance(THE_PR, poll(pr_state(author="alice", pending_reviewers=pending)), set())
        requested[pending] = detection.facts(THE_PR).viewer_requested

    assert requested == {(ACCOUNT, "erin"): True, ("erin",): False}


def test_a_request_to_a_team_i_am_on_counts_as_requested_when_the_search_found_it(detection):
    requested = {}
    for searched in (True, False):
        detection.advance(THE_PR, poll(pr_state(author="alice", pending_reviewers=("@platform",)),
                                       review_requested=searched), set())
        requested[searched] = detection.facts(THE_PR).viewer_requested

    assert requested == {True: True, False: False}


def test_the_facts_carry_each_mention_and_that_i_have_been_mentioned(detection):
    detection.advance(THE_PR, poll(pr_state(author="alice"), mentions=(ASKED,)), set())

    facts = detection.facts(THE_PR)

    assert (facts.mentions, facts.mentioned) == ((ASKED,), True)


def test_a_poll_that_could_not_read_the_comments_keeps_the_mentions_it_knew(detection):
    detection.advance(THE_PR, poll(pr_state(author="alice"), mentions=(ASKED,)), set())
    detection.advance(THE_PR, poll(pr_state(author="alice"), mentions=None), set())

    assert detection.facts(THE_PR).mentions == (ASKED,)


def test_once_the_mentions_search_finds_the_pr_it_stays_mentioned(detection):
    mentioned = []
    for searched in (False, True, False):
        detection.advance(THE_PR, poll(pr_state(author="alice"), mentions=(),
                                       mentioned=searched), set())
        facts = detection.facts(THE_PR)
        mentioned.append((facts.mentions, facts.mentioned))

    assert mentioned == [((), False), ((), True), ((), True)]


def test_the_facts_say_when_i_gave_the_review_that_stands(detection):
    detection.advance(THE_PR, poll(pr_state(author="alice", reviews=(
        Review(ACCOUNT, ReviewState.APPROVED, "2026-09-20T00:00:00Z", "sha0"),
        Review(ACCOUNT, ReviewState.COMMENTED, "2026-09-21T00:00:00Z", "sha0"),
        Review("bob", ReviewState.APPROVED, "2026-09-22T00:00:00Z", "sha0")))), set())

    facts = detection.facts(THE_PR)

    assert (facts.my_review, facts.my_review_at) == (ReviewerStatus.APPROVED, "2026-09-20T00:00:00Z")


def test_the_facts_say_when_the_watcher_polled_them(detection):
    detection.advance(THE_PR, poll(at="2026-10-08T09:00:00Z"), set())
    detection.advance(THE_PR, poll(at="2026-10-08T09:05:00Z"), set())

    assert detection.facts(THE_PR).polled_at == "2026-10-08T09:05:00Z"


def test_the_facts_say_when_the_pr_has_ended(detection):
    detection.advance(THE_PR, poll(), set())
    before = detection.facts(THE_PR).ended

    detection.close(THE_PR)

    assert (before, detection.facts(THE_PR).ended) == (False, True)


def test_a_reviewer_is_told_what_happened_since_they_last_acted(detection):
    reviewed = (Review(ACCOUNT, ReviewState.CHANGES_REQUESTED, "2026-09-20T00:00:00Z", "sha0"),)
    detection.advance(THE_PR, poll(pr_state(author="alice", reviews=reviewed)), set())
    detection.advance(THE_PR, poll(pr_state(
        author="alice", head_sha="sha1", reviews=reviewed,
        push_events=(PushEvent("committed", "2026-09-21T00:00:00Z"),
                     PushEvent("head_ref_force_pushed", "2026-09-21T00:01:00Z")))), set())

    assert detection.facts(THE_PR).since_review == SinceReview(
        sha="sha0", commits=1, force_push=True, reviews=0, comments=0, resolved=0)
