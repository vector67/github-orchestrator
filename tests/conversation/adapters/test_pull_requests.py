from github_orchestrator.conversation import (
    ConversationState,
    Denied,
)
from github_orchestrator.domain import Location, Side
from github_orchestrator.github import PullRequestState
from github_orchestrator.github.fake import Check, FakeGitHub
from github_orchestrator.notifications.fake import FakeNotifications
from tests.builders import a_pr
from tests.change_detection.support import passing
from tests.conversation.support import (
    PR,
    REPO,
    WORKTREE,
    drain,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    world,
)

THE_PR = a_pr(PR, REPO)

KEY = "PRRT_one"
HEAD = "a9296dba" + "0" * 32
WAKE_CI = "ci"
WAKE_PUSH = "push"


def _deferred(here, wake_on):
    repo_at(here.working_copies, WORKTREE, {"f": "old\n"})
    threads = here.threads()
    on_github(here.github, KEY, said(101, "rename this"))
    hear(threads)
    propose(here, threads, KEY)
    with threads.editing(KEY) as editable:
        editable.place(ConversationState.DEFERRED, until=wake_on)
    drain(threads)
    return threads


def _woken(threads):
    threads.tick(FakeNotifications(), on_hold=True)

    return threads.get(KEY).standing is not ConversationState.DEFERRED


def _woken_on(here, wake_on, **snapshot):
    threads = _deferred(here, wake_on)
    if snapshot:
        here.polled(is_author=True, **snapshot)
    return _woken(threads)


def test_a_green_snapshot_wakes_what_waited_on_ci(settings):
    here = world(settings)

    assert _woken_on(here, WAKE_CI, checks=(passing(),)) is True
    assert here.load(KEY).fix.reply_note == "woken: this PR's CI passed"


def test_a_pending_snapshot_is_not_green(settings):
    assert _woken_on(world(settings), WAKE_CI, checks=(Check("tests", "in_progress"),)) is False


def test_a_missing_ci_status_answers_it_cannot_tell(settings):
    assert _woken_on(world(settings), WAKE_CI) is False


def test_head_sha_is_read_off_the_snapshot(settings):
    here = world(settings)
    here.polled(head_sha=HEAD)

    assert here.threads().facts().head_sha == HEAD


def test_a_snapshot_that_names_no_head_answers_it_cannot_tell(settings):
    here = world(settings)
    here.polled(checks=(passing(),))

    assert here.threads().facts().head_sha is None


def _waiting_on_a_push(here):
    here.polled(is_author=True, head_sha=HEAD)
    return _deferred(here, WAKE_PUSH)


def test_a_push_past_the_head_waited_on_wakes_the_thread(settings):
    here = world(settings)
    threads = _waiting_on_a_push(here)
    here.polled(is_author=True, head_sha="c" * 40)

    assert _woken(threads) is True


def test_the_head_waited_on_still_there_wakes_nothing(settings):
    assert _woken(_waiting_on_a_push(world(settings))) is False


def test_a_closed_pull_request_reads_as_closed(settings):
    github = FakeGitHub()
    github.add_pr(a_pr(87, REPO), PullRequestState(), status="CLOSED")

    assert _woken_on(world(settings, github=github), "pr:87") is True


def test_an_open_pull_request_reads_as_not_closed(settings):
    github = FakeGitHub()
    github.add_pr(a_pr(87, REPO), PullRequestState())

    assert _woken_on(world(settings, github=github), "pr:87") is False


def test_a_pull_request_gh_cannot_reach_answers_it_cannot_tell(settings):
    assert _woken_on(world(settings), "pr:87") is False


def test_a_pr_whose_snapshot_says_you_did_not_open_it_is_reviewed(settings):
    here = world(settings)
    here.polled(is_author=False)

    assert here.conversation_managers.of(THE_PR).facts().is_author is False


def test_a_pr_whose_snapshot_says_you_opened_it_is_yours(settings):
    here = world(settings)
    here.polled(is_author=True)

    assert here.conversation_managers.of(THE_PR).facts().is_author is True


def test_a_pr_with_no_snapshot_has_no_role_yet(settings):
    assert world(settings).conversation_managers.of(THE_PR).facts().is_author is None


def test_a_pr_closing_before_any_poll_said_whose_it_is_gives_no_role(settings):
    here = world(settings)
    here.change_detection.close(THE_PR)

    assert here.conversation_managers.of(THE_PR).facts().is_author is None


def test_no_draft_is_opened_while_the_role_is_unknown(settings):
    here = world(settings)

    drafted = here.conversation_managers.of(THE_PR).open_draft(
        "rename it", Location(path="f.py", line=2, side=Side.AFTER))

    assert isinstance(drafted, Denied)
    assert here.conversation_managers.of(THE_PR).all() == []


def test_no_thread_is_opened_by_hand_while_the_role_is_unknown(settings):
    here = world(settings)
    repo_at(here.working_copies, WORKTREE)

    opened = here.conversation_managers.of(THE_PR).open_thread(
        KEY, kind="review", path="f.py", line=2, comment_id=101, author="alice",
        body="rename it")

    assert isinstance(opened, Denied)
    assert here.conversation_managers.of(THE_PR).all() == []


def test_the_role_is_learnt_once_the_snapshot_says_it(settings):
    here = world(settings)
    threads = here.conversation_managers.of(THE_PR)
    assert threads.facts().is_author is None

    here.polled(is_author=False)

    assert threads.facts().is_author is False
