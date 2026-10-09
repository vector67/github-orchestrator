import pytest

from github_orchestrator.conversation import Classification
from github_orchestrator.notifications import FixProgress
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    world,
)

KEY = "PRRT_1"
ARRIVED = "2026-09-24T15:40:00Z"


def _commented(settings, *replies, is_author=None):
    here = world(settings)
    repo_at(here.working_copies, WORKTREE)
    threads = here.threads(is_author=is_author)
    on_github(here.github, KEY, said(1, "fetch them in one query", author="ada",
                                     created_at=ARRIVED), *replies)
    hear(threads)
    return here, threads


def _only_heard(here, threads):
    return None


def _running(here, threads):
    start_run(here, threads, finishes=False)


def _proposed(here, threads):
    propose(here, threads, KEY)


def _declined(here, threads):
    start_run(here, threads, finishes=False)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.NEEDS_HUMAN, "a question")


@pytest.mark.parametrize("reached, said_", [
    (_only_heard, FixProgress.QUEUED),
    (_running, FixProgress.STARTED),
    (_proposed, FixProgress.STARTED),
    (_declined, FixProgress.NONE),
], ids=["queued", "running", "proposed", "declined"])
def test_the_fix_reads_as_how_far_it_got(settings, reached, said_):
    here, threads = _commented(settings)

    reached(here, threads)

    assert here.standing.fix_progress(THE_PR, KEY) is said_


def test_a_reviewers_thread_has_no_fix_to_read(settings):
    here, _ = _commented(settings, is_author=False)

    assert here.standing.fix_progress(THE_PR, KEY) is FixProgress.NONE


def test_a_thread_with_no_record_has_no_fix(settings):
    assert world(settings).standing.fix_progress(THE_PR, KEY) is FixProgress.NONE


def test_a_reply_from_the_account_after_the_comment_answers_it(settings):
    here, _ = _commented(settings, said(2, "done", author="octocat",
                                        created_at="2026-09-24T15:41:00Z"))

    assert not here.standing.comment_still_news(THE_PR, KEY, ARRIVED)


def test_a_reply_from_the_account_before_the_comment_does_not(settings):
    here, _ = _commented(settings, said(2, "done", author="octocat",
                                        created_at="2026-09-24T15:39:00Z"))

    assert here.standing.comment_still_news(THE_PR, KEY, ARRIVED)


def test_someone_else_replying_does_not_answer_for_the_account(settings):
    here, _ = _commented(settings, said(2, "done", author="bob",
                                        created_at="2026-09-24T15:41:00Z"))

    assert here.standing.comment_still_news(THE_PR, KEY, ARRIVED)


def test_a_thread_with_no_record_has_no_reply(settings):
    assert world(settings).standing.comment_still_news(THE_PR, KEY, ARRIVED)
