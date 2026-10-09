import json
from types import SimpleNamespace

import pytest

from github_orchestrator.change_detection import (
    CiStatus,
    ReviewerStatus,
)
from github_orchestrator.change_detection.fake import ReviewDecision
from github_orchestrator.domain import Repo, Side
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    ReviewState,
    Thread,
    ThreadComment,
)
from github_orchestrator.github.fake import (
    Check,
    FakeGitHub,
    GhError,
    Review,
    ThreadAnchor,
)
from github_orchestrator.notifications.fake import (
    Arrival,
    CommentArrived,
    FakeNotifications,
)
from github_orchestrator.settings.fake import RepoEntry, fake_settings
from github_orchestrator.thread_records.fake import FakeThreadRecords
from tests.builders import a_pr
from tests.change_detection.support import disk_change_detection, seen
from tests.conversation.support import conversation_managers_over, drain, hear
from tests.disk_layout import thread_file
from tests.pr_event_queue.support import disk_event_queue, pending_of
from tests.thread_records.support import disk_thread_records
from tests.watcher.support import watcher_over

GH_ACCOUNT = "octocat"
REPO = "acme/widgets"


def _state(**fields):
    defaults = {
        "head_sha": "abc123", "mergeable": True, "mergeable_state": "clean",
        "author": GH_ACCOUNT,
        "checks": (Check("tests", "completed", "success", "https://github.com/run/1",
                         "All passed"),
                   Check("lint", "completed", "success", "https://github.com/run/2",
                         "Clean")),
        "reviews": (Review("reviewer1", ReviewState.APPROVED),),
        "review_decision": "APPROVED",
    }
    return PullRequestState(**{**defaults, **fields})


def _comment(comment_id=10, author="reviewer1", body="Looks good",
             at="2026-04-20T15:00:00Z"):
    return ThreadComment(id=comment_id, author=author, body=body,
                         created_at=at, updated_at=at)


def _thread(key="PRRT_one", kind=CommentKind.REVIEW, comments=None, resolved=False,
            path="src/main.py", line=42):
    return Thread(
        key=key, kind=kind, is_resolved=resolved, path=path, line=line,
        anchor=ThreadAnchor(is_outdated=False, side=Side.AFTER, original_line=line,
                            original_commit="deadbeef"),
        comments=(_comment(),) if comments is None else tuple(comments),
    )


def _threads():
    return [
        _thread(),
        _thread(key="IC_one", kind=CommentKind.ISSUE, path=None, line=None,
                comments=[_comment(20, body="Nice work", at="2026-04-20T15:30:00Z")]),
    ]


def _holding(state, threads, number, github=None):
    github = github or FakeGitHub(account=GH_ACCOUNT)
    github.add_pr(a_pr(number, REPO), state, review_requested=True)
    for thread in threads:
        github.add_thread(a_pr(number, REPO), thread)
    return github


def _board(settings, github, records, number):
    pr = a_pr(number, REPO)
    disk_change_detection(settings.state_dir).advance(pr, seen(GH_ACCOUNT, is_author=False), set())
    threads = conversation_managers_over(settings, github=github, thread_records=records).of(pr)
    hear(threads)
    return threads


@pytest.fixture
def settings(tmp_path):
    return fake_settings(tmp_path, repos=(RepoEntry(Repo.parse(REPO), str(tmp_path / "clone")),))


def _poll(settings, state=None, threads=(), number=23, github=None, clock=None,
          cursor=None, notifications=None, records=None, dry_run=False):
    github = _holding(state or _state(), threads, number, github)
    records = records or FakeThreadRecords()
    if cursor is not None:
        records.of(a_pr(number, REPO)).save("cursor", "poll", json.dumps(cursor).encode())
    return _cycled(settings, github, records, number, clock=clock,
                   notifications=notifications, dry_run=dry_run)


def _cycled(settings, github, records, number=23, *, clock=None, notifications=None,
            dry_run=False):
    watcher_over(settings, github=github, clock=clock, notifications=notifications,
                 thread_records=records, dry_run=dry_run).run_cycle()
    activity = [event for event in pending_of(disk_event_queue(settings.queues_dir), a_pr(number, REPO))
                if event.kind == "thread-activity"]
    return SimpleNamespace(
        facts=disk_change_detection(settings.state_dir).facts(a_pr(number, REPO)),
        tracked=disk_change_detection(settings.state_dir).tracked(),
        cursor=json.loads(records.of(a_pr(number, REPO)).load("cursor", "poll")
                          or b"null"),
        active_threads=list(activity[0].threads) if activity else [],
        stale_threads=list(activity[0].stale) if activity else [],
    )


class _ThreadsDown(FakeGitHub):
    def threads(self, pr):
        raise GhError("gh graphql failed (exit 1): graphql down")


class _FetchingAhead(FakeGitHub):
    def __init__(self) -> None:
        super().__init__(account=GH_ACCOUNT)
        self.fetched_ahead: list[list] = []

    def prefetch(self, prs):
        self.fetched_ahead.append(sorted(prs, key=lambda pr: pr.number))


def test_a_poll_fetches_every_pr_it_polls_ahead_in_one_go(settings):
    github = _FetchingAhead()
    _holding(_state(), (), 24, github)

    _poll(settings, github=github)

    assert github.fetched_ahead == [[a_pr(23, REPO), a_pr(24, REPO)]]


def test_a_poll_assembles_state(settings):
    poll = _poll(settings)

    assert poll.facts.head_sha == "abc123"
    assert poll.facts.mergeable is True
    assert poll.facts.merge_state.value == "clean"
    assert poll.facts.ci_status is CiStatus.PASSING
    assert poll.facts.review_decision is ReviewDecision.APPROVED
    assert poll.facts.approved_by == ("reviewer1",)
    assert poll.facts.is_author is True
    assert poll.tracked == [a_pr(23, REPO)]


def test_a_poll_includes_draft_flag(settings):
    assert _poll(settings, _state(draft=True)).facts.draft is True


def test_a_poll_records_commented_reviews_in_reviewer_status(settings):
    poll = _poll(settings, _state(reviews=(Review(GH_ACCOUNT, ReviewState.COMMENTED),)))

    assert poll.facts.my_review is ReviewerStatus.COMMENTED


def test_a_poll_commented_review_does_not_clobber_prior_approval(settings):
    poll = _poll(settings, _state(reviews=(Review(GH_ACCOUNT, ReviewState.APPROVED),
                                 Review(GH_ACCOUNT, ReviewState.COMMENTED))))

    assert poll.facts.my_review is ReviewerStatus.APPROVED


def test_a_poll_review_decision_from_graphql_overrides_dismissed_rest_state(settings):
    poll = _poll(settings, _state(reviews=(Review("reviewer1", ReviewState.APPROVED),
                                 Review("reviewer1", ReviewState.DISMISSED)),
                        review_decision="APPROVED"))

    assert poll.facts.review_decision is ReviewDecision.APPROVED


def test_a_poll_detects_ci_failure(settings):
    poll = _poll(settings, _state(checks=(Check("tests", "completed", "failure",
                                      "https://github.com/run/1", "3 failed"),)))

    assert poll.facts.ci_status is CiStatus.FAILING


def test_a_poll_ci_pending_when_checks_still_in_progress(settings):
    poll = _poll(settings, _state(checks=(
        Check("claude", "completed", "skipped"),
        Check("quality-checks", "completed", "success"),
        Check("unit-tests", "completed", "success"),
        Check("integration-tests", "in_progress", None),
    )))

    assert poll.facts.ci_status is CiStatus.PENDING


def test_no_checks_at_all_is_pending(settings):
    poll = _poll(settings, _state(checks=()))

    assert poll.facts.ci_status is CiStatus.PENDING
    assert poll.facts.checks_total == 0


def test_a_neutral_check_counts_as_a_pass(settings):
    poll = _poll(settings, _state(checks=(Check("info-check", "completed", "neutral"),)))

    assert poll.facts.ci_status is CiStatus.PASSING


def test_a_cancelled_timed_out_or_blocked_check_counts_as_a_failure(settings):
    for conclusion in ("cancelled", "timed_out", "action_required"):
        poll = _poll(settings, _state(checks=(Check("tests", "completed", conclusion),)))
        assert poll.facts.ci_status is CiStatus.FAILING, conclusion


def test_a_poll_includes_checks(settings):
    poll = _poll(settings)

    assert (poll.facts.checks_done, poll.facts.checks_total, poll.facts.failed_checks) == (
        2, 2, ())


def test_no_reviews_names_no_decision_and_no_latest_reviewer(settings):
    poll = _poll(settings, _state(reviews=(), review_decision=None))

    assert poll.facts.review_decision is None
    assert poll.facts.approved_by == ()


def test_a_review_from_a_deleted_account_names_nobody(settings):
    poll = _poll(settings, _state(reviews=(Review(None, ReviewState.APPROVED),)))

    assert (poll.facts.approved_by, poll.facts.my_review) == ((), None)


def test_a_pr_from_a_deleted_account_is_not_mine(settings):
    poll = _poll(settings, _state(author=None))

    assert poll.facts.author is None
    assert poll.facts.is_author is False


def test_a_poll_reports_every_thread_with_a_comment_the_cursor_has_not_seen(settings):
    poll = _poll(settings, threads=_threads(), cursor=SEEN_BEFORE)

    assert [t.key for t in poll.active_threads] == ["PRRT_one", "IC_one"]
    assert [t.kind for t in poll.active_threads] == ["review", "issue"]
    assert poll.active_threads[0].path == "src/main.py"


def test_a_pr_seen_for_the_first_time_queues_its_open_review_threads(settings):
    github = _holding(_state(), [*_threads(), _thread(key="PRRT_done", resolved=True)], 23)

    poll = _cycled(settings, github, FakeThreadRecords())

    assert [t.key for t in poll.active_threads] == ["PRRT_one"]


def test_a_poll_keeps_the_old_cursor_when_the_thread_fetch_fails(settings):
    poll = _poll(settings, github=_ThreadsDown(account=GH_ACCOUNT), threads=_threads(),
                 cursor={"PRRT_one": [10]})

    assert poll.cursor == {"PRRT_one": [10]}
    assert poll.active_threads == []
    assert poll.facts.ci_status is CiStatus.PASSING
    assert poll.facts.unresolved_threads is None


def test_a_poll_filters_the_boards_own_decline_replies(settings):
    github = _holding(_state(), [_thread(key="PRRT_reply", comments=[
        _comment(102, body="is this needed?")])], 60)
    records = FakeThreadRecords()
    board = _board(settings, github, records, 60)
    with board.editing("PRRT_reply") as editable:
        editable.reply("Not needed: see #12.")
    drain(board)
    [posted] = github.thread("PRRT_reply").comments[1:]
    reply_id = posted.id
    github.add_thread(a_pr(60, REPO), _thread(key="PRRT_hand", comments=[
        _comment(104, author=GH_ACCOUNT, body="typed on GitHub by hand")]))
    github.add_thread(a_pr(60, REPO), _thread(
        key="IC_same_number", kind=CommentKind.ISSUE, path=None, line=None, comments=[
            _comment(reply_id, author=GH_ACCOUNT, body="same number, other table")]))

    poll = _cycled(settings, github, records, 60)

    assert [t.key for t in poll.active_threads] == ["PRRT_hand", "IC_same_number"], (
        "the board's own review reply is filtered, but an issue comment that "
        "happens to share its number is a different id space"
    )


def test_a_detailed_reviewer_named_mid_sentence_is_not_one(settings):
    poll = _poll(settings, _state(body="Note: detailed reviewer: @bob is unavailable."))

    assert poll.facts.detailed_reviewer is None


def test_a_detailed_reviewer_on_a_line_of_its_own_is_named(settings):
    poll = _poll(settings, _state(body="Some intro\nDetailed reviewer: @bob\nMore body"))

    assert poll.facts.detailed_reviewer == "bob"
    assert poll.facts.is_detailed_reviewer is False


def test_being_the_detailed_reviewer_is_told(settings):
    poll = _poll(settings, _state(body=f"Detailed reviewer: @{GH_ACCOUNT}"))

    assert poll.facts.is_detailed_reviewer is True


def test_when_the_pr_was_made_ready_for_review_is_kept(settings):
    poll = _poll(settings, _state(ready_for_review_at="2026-04-01T00:00:00Z"))

    assert poll.facts.review_ready_at == "2026-04-01T00:00:00Z"


SEEN_BEFORE = {"IC_elsewhere": [99]}


def _arrived(notifications):
    return [item for item in notifications.gathered if isinstance(item, CommentArrived)]


def test_a_comment_on_a_thread_nobody_has_recorded_arrives_as_a_new_thread(settings):
    notifications = FakeNotifications()

    _poll(settings, threads=[_thread()], cursor=SEEN_BEFORE, notifications=notifications)

    assert _arrived(notifications) == [CommentArrived(
        pr=a_pr(23, REPO), key="PRRT_one", comment_id=10, author="reviewer1",
        body="Looks good", created_at="2026-04-20T15:00:00Z", arrival=Arrival.NEW_THREAD,
        review_comment=False)]


def test_a_reviews_own_message_arrives_flagged_as_a_review_comment(settings):
    notifications = FakeNotifications()
    summary = Thread(key="PRR_one", kind=CommentKind.REVIEW_SUMMARY, state=ReviewState.COMMENTED,
                     comments=(_comment(4513159404, body="Keep `field` for compatibility?"),))

    _poll(settings, threads=[summary], cursor=SEEN_BEFORE, notifications=notifications)

    assert [item.review_comment for item in _arrived(notifications)] == [True]


def test_the_accounts_own_comment_does_not_arrive(settings):
    notifications = FakeNotifications()
    thread = _thread(comments=[_comment(10, author=GH_ACCOUNT, body="note to self")])

    _poll(settings, threads=[thread], cursor=SEEN_BEFORE, notifications=notifications)

    assert _arrived(notifications) == []


def test_nothing_arrives_on_the_first_poll_of_a_pr(settings):
    notifications = FakeNotifications()

    _poll(settings, threads=_threads(), notifications=notifications)

    assert _arrived(notifications) == []


def test_nothing_arrives_on_a_dry_run(settings):
    notifications = FakeNotifications()

    _poll(settings, threads=[_thread()], cursor=SEEN_BEFORE, notifications=notifications,
          dry_run=True)

    assert _arrived(notifications) == []


def test_a_record_that_will_not_parse_does_not_stop_the_comment_arriving(settings):
    notifications = FakeNotifications()
    corrupt = thread_file(settings.threads_dir, a_pr(23, REPO), "PRRT_one")
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("{")

    _poll(settings, threads=[_thread()], cursor=SEEN_BEFORE, notifications=notifications,
          records=disk_thread_records(settings.threads_dir))

    assert [(item.key, item.arrival.value) for item in _arrived(notifications)] == [
        ("PRRT_one", "Reply")]


class _AddFailsOnce:
    def __init__(self, inner, event_type):
        self._inner = inner
        self._event_type = event_type

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def add_thread_activity(self, pr, activity):
        if activity.kind == self._event_type:
            self._event_type = None
            raise OSError("the watcher died before the event reached the event_queue")
        self._inner.add_thread_activity(pr, activity)


def _with_a_new_reply(settings, **modules):
    github = _holding(_state(), [_thread()], 23)
    _board(settings, github, modules["thread_records"], 23)
    github.prs[(a_pr(23, REPO))].threads = [_thread(comments=[
        _comment(), _comment(11, body="still broken", at="2026-04-20T15:05:00Z")])]
    return github


def _thread_activity(settings):
    return [event for event in pending_of(disk_event_queue(settings.queues_dir), a_pr(23, REPO))
            if event.kind == "thread-activity"]


def test_thread_activity_the_watcher_died_before_queueing_is_queued_by_the_next_cycle(
        settings):
    records = FakeThreadRecords()
    github = _with_a_new_reply(settings, thread_records=records)
    notifications = FakeNotifications()

    watcher_over(settings, github=github, thread_records=records, notifications=notifications,
                 event_queue=_AddFailsOnce(disk_event_queue(settings.queues_dir), "thread-activity"),
                 ).run_cycle()
    assert _thread_activity(settings) == []
    watcher_over(settings, github=github, thread_records=records,
                 notifications=notifications).run_cycle()

    [queued] = _thread_activity(settings)
    assert [c.id for c in queued.threads[0].comments] == [10, 11]
    assert [item.comment_id for item in _arrived(notifications)] == [11]


def test_thread_activity_queued_before_the_watcher_died_is_not_queued_twice(settings):
    records = FakeThreadRecords()
    github = _with_a_new_reply(settings, thread_records=records)
    records.fail_saves(OSError("the watcher died before the cursor was saved"), times=1)
    notifications = FakeNotifications()

    watcher_over(settings, github=github, thread_records=records,
                 notifications=notifications).run_cycle()
    watcher_over(settings, github=github, thread_records=records,
                 notifications=notifications).run_cycle()

    [queued] = _thread_activity(settings)
    assert [c.id for c in queued.threads[0].comments] == [10, 11]
    assert [item.comment_id for item in _arrived(notifications)] == [11]
    watcher_over(settings, github=github, thread_records=records,
                 notifications=notifications).run_cycle()
    assert len(_thread_activity(settings)) == 1
