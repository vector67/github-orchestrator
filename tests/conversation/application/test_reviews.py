from github_orchestrator.conversation import (
    ConversationState,
    Denied,
    OperationKind,
    OperationState,
    ReasonCode,
    Verdict,
)
from github_orchestrator.domain import Location, Side
from github_orchestrator.github.fake import FakeGitHub, GhError
from tests.builders import a_pr
from tests.conversation.support import (
    PR,
    REPO,
    at,
    diff_over,
    drain,
    world,
)

THE_PR = a_pr(PR, REPO)

NOW = "2026-09-23T10:00:00Z"


class ReviewRefused(FakeGitHub):
    def post_review(self, pr, head, verdict, body, comments):
        raise GhError("HTTP 422: Pull request review thread line must be part "
                      "of the diff")


def _reviewing(settings, github=None):
    here = world(settings, github=github or FakeGitHub(), clock=at(NOW))
    here.github.add_pr(THE_PR)
    head = diff_over(here, "billing/invoice_writer.py")
    return here, here.threads(), head


def _draft(threads, number: int, enrolled: bool = True):
    drafted = threads.open_draft(
        f"finding {number}",
        Location(path="billing/invoice_writer.py", line=10 + number, side=Side.AFTER),
        f"op_created{number}")
    assert not isinstance(drafted, Denied), drafted
    if enrolled:
        with threads.editing(drafted.key) as editable:
            outcome = editable.enrol()
        assert not isinstance(outcome, Denied), outcome
        drain(threads)
    return threads.get(drafted.key)


def _request_review(threads) -> None:
    sent = threads.send_review(Verdict.REQUEST_CHANGES, "a few things")
    assert not isinstance(sent, Denied), sent


def _review(threads):
    [review] = threads.reviews()
    return review


def _roots_on_github(here) -> dict[str, tuple[str, int]]:
    return {thread.comments[0].body: (thread.key, thread.comments[0].id)
            for thread in here.github.threads(THE_PR)
            if thread.key.startswith("PRRT_")}


def test_six_enrolled_drafts_go_out_as_one_review_and_each_is_posted(settings):
    here, threads, head = _reviewing(settings)
    drafts = [_draft(threads, number) for number in range(1, 7)]
    _request_review(threads)

    drain(threads)

    [sent] = here.github.pr_state(THE_PR).reviews
    assert (sent.requests_changes, sent.commit_id) == (True, head)
    roots = _roots_on_github(here)
    review = _review(threads)
    for draft in drafts:
        posted = threads.get(draft.key)
        thread_key, comment_id = roots[draft.body]
        assert posted.standing is ConversationState.WAITING
        assert posted.github_node_id == thread_key
        operation = posted.operations[-1]
        assert (operation.kind, operation.state, operation.review,
                operation.posted_comment) == (OperationKind.POSTED, OperationState.APPLIED,
                                              review.id, comment_id)
    assert review.state is OperationState.APPLIED
    assert sorted(review.drafts) == sorted(draft.key for draft in drafts)
    assert here.github.thread(f"PRR_{review.posted_review}").comments[0].body == "a few things"
    assert review.settled_at == NOW


def test_drafts_go_out_in_the_review_left_pending_on_github_with_its_comments(settings):
    here, threads, _ = _reviewing(settings)
    pending = here.github.start_pending_review(THE_PR, [
        (Location("billing/invoice_writer.py", 3, Side.AFTER), "drafted on github")])
    draft = _draft(threads, 1)
    _request_review(threads)

    drain(threads)

    review = _review(threads)
    assert (review.state, review.posted_review) == (OperationState.APPLIED, pending)
    roots = _roots_on_github(here)
    assert set(roots) == {"drafted on github", draft.body}
    assert threads.get(draft.key).operations[-1].posted_comment == roots[draft.body][1]


def test_a_draft_that_is_not_enrolled_stays_behind(settings):
    here, threads, _ = _reviewing(settings)
    enrolled, kept_back = _draft(threads, 1), _draft(threads, 2, enrolled=False)
    _request_review(threads)

    drain(threads)

    assert set(_roots_on_github(here)) == {enrolled.body}
    assert _review(threads).drafts == (enrolled.key,)
    assert threads.get(kept_back.key) == kept_back


def test_a_review_github_rejects_leaves_every_draft_enrolled_and_says_why(settings):
    _, threads, _ = _reviewing(settings, ReviewRefused())
    drafts = [_draft(threads, 1), _draft(threads, 2)]
    _request_review(threads)

    drain(threads)

    for draft in drafts:
        assert threads.get(draft.key) == draft
    review = _review(threads)
    assert (review.state, review.reason_code) == (OperationState.REFUSED,
                                                  ReasonCode.GITHUB_REJECTED)
    assert "must be part of the diff" in (review.reason or "")
    assert sorted(review.drafts) == sorted(draft.key for draft in drafts)


def test_a_review_that_has_settled_is_not_sent_again(settings):
    here, threads, _ = _reviewing(settings)
    _draft(threads, 1)
    _request_review(threads)

    drain(threads)
    drain(threads)

    assert len(here.github.pr_state(THE_PR).reviews) == 1
