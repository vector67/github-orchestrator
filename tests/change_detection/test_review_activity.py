from github_orchestrator.github import ReviewState
from github_orchestrator.github.fake import PushEvent, Review
from tests.builders import a_pr
from tests.change_detection.support import ACCOUNT, PR, REPO, poll, pr_state

THE_PR = a_pr(PR, REPO)

OTHER = "someone-else"


def _commits(n, at="2026-06-30T00:00:00Z"):
    return [PushEvent("committed", at) for _ in range(n)]


def _activity(detection, *reviews, head="a", pushes=(), mine=None, others=0, unresolved=0,
              author=OTHER):
    detection.advance(THE_PR, poll(
        pr_state(author=author, head_sha=head, reviews=tuple(reviews),
                 push_events=tuple(pushes)),
        my_last_comment_at=mine, comments_by_others=others,
        unresolved_thread_count=unresolved,
    ), set())
    return detection.facts(THE_PR).since_review


def _mine(at="2026-06-10T00:00:00Z", sha="a", state=ReviewState.APPROVED):
    return Review(ACCOUNT, state, at, sha)


def test_my_own_pr_carries_no_review_activity(detection):
    result = _activity(detection, _mine("2026-06-01T00:00:00Z"), head="b",
                       pushes=_commits(5), author=ACCOUNT)

    assert result is None


def test_no_action_yet_means_no_anchor(detection):
    result = _activity(detection, Review(OTHER, ReviewState.APPROVED, "2026-06-01T00:00:00Z", "a"),
                       head="b", pushes=_commits(5))

    assert result is None


def test_my_review_anchors_and_commits_since_are_counted(detection):
    result = _activity(detection, _mine(sha="rev_sha", state=ReviewState.CHANGES_REQUESTED),
                       head="head_sha", pushes=_commits(3, at="2026-06-12T00:00:00Z"))

    assert result.commits == 3
    assert result.force_push is False


def test_a_force_push_is_seen_on_the_timeline_even_back_onto_the_reviewed_commit(detection):
    result = _activity(detection, _mine("2026-06-16T13:18:19Z", "eefd72f"), head="eefd72f",
                       pushes=[*_commits(4, at="2026-06-17T14:48:12Z"),
                               PushEvent("head_ref_force_pushed", "2026-06-17T14:48:52Z")])

    assert result.force_push is True
    assert result.commits == 4


def test_pushes_at_or_before_my_review_are_ignored(detection):
    result = _activity(detection, _mine("2026-06-16T00:00:00Z", "x"), head="y",
                       pushes=[PushEvent("committed", "2026-06-15T00:00:00Z"),
                               PushEvent("committed", "2026-06-16T00:00:00Z")])

    assert result.commits == 0
    assert result.force_push is False


def test_my_comment_moves_the_anchor_past_an_older_review(detection):
    result = _activity(detection, _mine("2026-06-01T00:00:00Z", "old_sha", ReviewState.CHANGES_REQUESTED),
                       head="head_sha", mine="2026-06-15T00:00:00Z",
                       pushes=[*_commits(2, at="2026-06-10T00:00:00Z"),
                               *_commits(1, at="2026-06-16T00:00:00Z")])

    assert result.commits == 1


def test_other_reviewers_verdicts_since_my_review_are_counted(detection):
    result = _activity(detection, _mine(state=ReviewState.CHANGES_REQUESTED),
                       Review(OTHER, ReviewState.APPROVED, "2026-06-11T00:00:00Z", "a"),
                       Review(OTHER, ReviewState.COMMENTED, "2026-06-12T00:00:00Z", "a"))

    assert result.reviews == 1


def test_comments_accumulate_across_polls_while_the_anchor_stays(detection):
    _activity(detection, _mine(), unresolved=3)
    _activity(detection, _mine(), unresolved=3, others=2)

    result = _activity(detection, _mine(), unresolved=3, others=2)

    assert result.comments == 4


def test_resolved_threads_accumulate_as_the_unresolved_count_drops(detection):
    _activity(detection, _mine(), unresolved=6)
    _activity(detection, _mine(), unresolved=5)

    result = _activity(detection, _mine(), unresolved=2)

    assert result.resolved == 4


def test_acting_again_resets_what_has_happened_since(detection):
    _activity(detection, _mine(), unresolved=5)
    _activity(detection, _mine(), unresolved=3, others=1)

    result = _activity(detection, _mine("2026-06-16T00:00:00Z"), unresolved=2)

    assert result is not None
    assert result.comments == 0
    assert result.resolved == 0
