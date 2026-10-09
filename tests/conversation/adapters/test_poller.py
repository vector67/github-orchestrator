from dataclasses import dataclass
from typing import Any

import pytest

from github_orchestrator.agent_runs.fake import HeldVerdicts
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    Thread,
    ThreadComment,
)
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications.fake import CommentArrived, FakeNotifications
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.builders import a_pr
from tests.conversation.support import (
    PR,
    REPO,
    WORKTREE,
    Moment,
    hear,
    repo_at,
    world,
)

THE_PR = a_pr(PR, REPO)

ME = "octocat"


def _comment(comment_id=1, author="reviewer", body="please fix",
             created_at="2026-04-28T09:00:00Z"):
    return ThreadComment(id=comment_id, author=author, body=body,
                         created_at=created_at, updated_at=created_at)


def _thread(key="PRRT_one", kind=CommentKind.REVIEW, comments=None, resolved=False):
    return Thread(
        key=key, kind=kind, is_resolved=resolved, path="src/app.py", line=4,
        comments=(_comment(),) if comments is None else tuple(comments))


def _holding(*threads):
    github = FakeGitHub(account=ME)
    github.add_pr(THE_PR, PullRequestState())
    for thread in threads:
        github.add_thread(THE_PR, thread)
    return github


def _world(settings, *threads, **fields):
    built = world(settings, github=_holding(*threads), **fields)
    repo_at(built.working_copies, WORKTREE)
    return built


def _after_a_first_poll(settings, *threads, **fields):
    built = _world(settings, **fields)
    _heard(built)
    for thread in threads:
        built.github.add_thread(THE_PR, thread)
    return built


def _now_on_github(built, *threads):
    built.github.prs[THE_PR].threads = []
    for thread in threads:
        built.github.add_thread(THE_PR, thread)


@dataclass(frozen=True)
class _Heard:
    polled: Any
    active: list[str]
    stale: list[str]
    arrivals: list[CommentArrived]

    @property
    def arrived(self):
        return [arrived.comment_id for arrived in self.arrivals]


def _heard(built, *, save=True):
    threads = built.threads()
    polled = threads.poll(PullRequestState())
    if save:
        polled.commit()
    news = FakeNotifications()
    polled.announce(news)
    found = polled.activity
    if save and found is not None:
        threads.absorb(found)
    return _Heard(polled=polled,
                  active=[] if found is None else [thread.key for thread in found.threads],
                  stale=[] if found is None else [thread.key for thread in found.stale],
                  arrivals=[item for item in news.gathered if isinstance(item, CommentArrived)])


def test_the_cutoff_is_five_seconds_behind_the_clock(settings):
    built = world(settings, github=_holding(), clock=Moment("2026-04-28T10:00:05Z"))

    assert built.conversation_managers.of(THE_PR).poll(PullRequestState()).polled_at == "2026-04-28T10:00:00Z"


def test_the_cursor_fingerprints_each_comment_body(settings):
    built = _world(settings, _thread(comments=[_comment(1, body="please fix")]))
    _heard(built)
    _now_on_github(built, _thread(comments=[_comment(1, body="please fix the other one")]))

    assert _heard(built).polled.activity is not None, (
        "an edit changes no id, so only the body can tell the cursor"
    )


def test_a_comment_the_cursor_has_never_seen_is_active_work(settings):
    polled = _heard(_after_a_first_poll(settings, _thread()))

    assert polled.active == ["PRRT_one"]
    assert polled.arrived == [1]
    assert polled.stale == []


def test_a_thread_the_cursor_holds_and_github_no_longer_has_leaves_the_cursor(settings):
    built = _world(settings, _thread())
    _heard(built)
    _now_on_github(built)

    assert _heard(built).polled.activity is None
    _now_on_github(built, _thread())
    assert _heard(built).active == ["PRRT_one"]


def test_a_deferred_comment_is_reported_by_the_poll_after_the_cutoff_passes(settings):
    clock = Moment("2026-04-28T10:00:05Z")
    built = _world(settings, _thread(comments=[
        _comment(1, created_at="2026-04-28T09:59:55Z"),
        _comment(2, created_at="2026-04-28T10:00:03Z"),
    ]), clock=clock)
    _heard(built)
    clock.iso = "2026-04-28T10:00:15Z"

    assert _heard(built).arrived == [2]


def test_a_marked_reply_of_our_own_is_not_new_work(settings):
    ours = _thread(key="PRRT_ours", comments=[
        _comment(1, author=ME, body="\U0001F916 landed in abc123"),
    ])
    theirs = _thread(key="PRRT_theirs", comments=[
        _comment(2, author="alice", body="\U0001F916 not from me"),
    ])

    assert _heard(_world(settings, ours, theirs)).active == ["PRRT_theirs"]


def test_the_same_comment_is_new_work_when_no_record_says_the_board_posted_it(settings):
    built = _world(settings, _thread(comments=[_comment(555, author=ME,
                                                        body="Not needed: see #12.")]))

    assert _heard(built).active == ["PRRT_one"]


def test_only_an_unresolved_review_thread_counts_as_unresolved(settings):
    polled = _heard(_world(
        settings,
        _thread(key="PRRT_open"),
        _thread(key="PRRT_resolved", resolved=True),
        _thread(key="IC_one", kind=CommentKind.ISSUE),
        _thread(key="PRR_one", kind=CommentKind.REVIEW_SUMMARY),
    ))

    assert polled.polled.unresolved_count == 1


def test_a_fetch_that_raises_keeps_the_old_cursor_and_reports_nothing(settings):
    built = _world(settings, _thread(comments=[_comment(1)]))
    _heard(built)
    built.github.prs.pop(THE_PR)

    polled = _heard(built)

    assert (polled.polled.activity, polled.arrived) == (None, [])
    assert polled.polled.unresolved_count is None
    built.github.add_pr(THE_PR, PullRequestState())
    built.github.add_thread(THE_PR, _thread(comments=[_comment(1), _comment(2)]))
    assert _heard(built).arrived == [2], "the next cycle has to pick up where this one left off"


def test_a_fetch_that_raises_on_a_pr_never_polled_leaves_an_empty_cursor(settings):
    built = world(settings, github=FakeGitHub(account=ME))
    _heard(built)
    built.github.add_pr(THE_PR, PullRequestState())
    built.github.add_thread(THE_PR, _thread())

    assert _heard(built).arrived == [1]


def test_a_fetch_that_raises_says_so(settings, caplog):
    built = world(settings, github=FakeGitHub(account=ME))

    with caplog.at_level("ERROR"):
        _heard(built)

    assert f"{REPO}#{PR}" in caplog.text
    assert "Not Found" in caplog.text


def test_a_dry_run_poll_moves_no_cursor(settings):
    built = _world(settings, _thread())

    assert _heard(built, save=False).active == ["PRRT_one"]
    assert _heard(built).active == ["PRRT_one"]


def test_a_stale_thread_alone_is_thread_activity(settings):
    built = _world(settings, _thread())
    _heard(built)
    built.github.resolve_thread("PRRT_one")

    polled = _heard(built)

    assert polled.polled.activity.threads == ()
    assert [thread.key for thread in polled.polled.activity.stale] == ["PRRT_one"]


def test_the_thread_activity_carries_the_cutoff_it_was_found_under(settings):
    built = _world(settings, _thread(), clock=Moment("2026-04-28T10:00:05Z"))

    assert _heard(built).polled.activity.cutoff == "2026-04-28T10:00:00Z"


def test_a_poll_that_finds_nothing_new_is_no_thread_activity(settings):
    built = _world(settings, _thread())
    _heard(built)

    assert _heard(built).polled.activity is None


def test_an_open_thread_with_no_record_is_offered_once_on_my_pr_while_claude_is_disabled(
        settings):
    built = _world(settings, _thread())
    threads = built.threads(is_author=True, agents_enabled=False)
    threads.poll(PullRequestState()).commit()

    assert threads.poll(PullRequestState()).activity is None


def test_an_open_thread_with_no_record_is_offered_on_a_pr_i_review_while_claude_is_disabled(
        settings):
    built = _world(settings, _thread())
    threads = built.threads(is_author=False, agents_enabled=False)

    assert [thread.key for thread in threads.poll(PullRequestState()).activity.threads] == ["PRRT_one"]


def test_thread_activity_on_my_pr_while_claude_is_disabled_is_drained_without_records(
        settings):
    built = _world(settings, _thread())
    threads = built.threads(is_author=True, agents_enabled=False)

    absorbed = threads.absorb(threads.poll(PullRequestState()).activity)

    assert absorbed.drained
    assert threads.all() == []


def test_thread_activity_on_a_pr_i_review_while_claude_is_disabled_still_becomes_records(
        settings):
    built = _world(settings, _thread())
    threads = built.threads(is_author=False, agents_enabled=False)

    absorbed = threads.absorb(threads.poll(PullRequestState()).activity)

    assert not absorbed.drained
    assert [conversation.key for conversation in threads.all()] == ["PRRT_one"]


def _arrived_as(polled):
    return [(arrived.comment_id, arrived.arrival.value) for arrived in polled.arrivals]


def _arrivals(settings, *comments):
    return _arrived_as(_heard(_after_a_first_poll(settings, _thread(comments=comments))))


def _recorded(settings, root, *, is_author=None):
    built = _world(settings, _thread(comments=[root]), agent_runs=HeldVerdicts(FakePrProcesses()))
    hear(built.threads(is_author=is_author))
    return built


def _resolved(settings):
    built = _recorded(settings, _comment(1))
    built.github.resolve_thread("PRRT_one")
    hear(built.threads())
    return built


def _placed_by(word):
    def placed(settings):
        built = _recorded(settings, _comment(1, author=ME), is_author=False)
        built.agent_runs.give(word)
        return built
    return placed


_waiting_on_reviewer = _placed_by("their-move")


def test_the_first_comment_of_a_thread_nobody_has_recorded_arrives_as_a_new_thread(settings):
    assert _arrivals(settings, _comment(1)) == [(1, "New thread")]


def test_a_later_comment_on_a_thread_nobody_has_recorded_arrives_as_a_reply(settings):
    assert _arrivals(settings, _comment(1), _comment(2))[1] == (2, "Reply")


@pytest.mark.parametrize("recorded", [_resolved, _waiting_on_reviewer,
                                      _placed_by("assumed-done"), _placed_by("not-mine")],
                         ids=["resolved", "waiting_on_reviewer", "assumed_done", "not_mine"])
def test_the_first_new_comment_on_a_closed_thread_arrives_reopening_it(settings, recorded):
    built = recorded(settings)
    root = built.github.thread("PRRT_one").comments[0]
    _now_on_github(built, _thread(comments=[root, _comment(2), _comment(3)]))

    assert _arrived_as(_heard(built)) == [(2, "Reopened"), (3, "Reply")]


def test_a_comment_on_an_open_thread_arrives_as_a_reply(settings):
    built = _recorded(settings, _comment(1))
    _now_on_github(built, _thread(comments=[_comment(1), _comment(2)]))

    assert _arrived_as(_heard(built)) == [(2, "Reply")]
