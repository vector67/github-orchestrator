import json
from dataclasses import dataclass, replace
from typing import Any

from github_orchestrator.conversation import Denied, ReviewState
from github_orchestrator.domain import Side
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    Thread,
    ThreadComment,
)
from github_orchestrator.github.fake import ThreadAnchor
from github_orchestrator.notifications.fake import CommentArrived, FakeNotifications
from tests.builders import a_pr
from tests.conversation.support import (
    PR,
    REPO,
    WORKTREE,
    Moment,
    drain,
    hear,
    repo_at,
    without_runs,
    world,
)

THE_PR = a_pr(PR, REPO)

BOT = "octocat"

KEY = "PRRT_one"


def _comment(comment_id=1, author="reviewer", body="please fix", **fields):
    return ThreadComment(id=comment_id, author=author, body=body, **fields)


def _thread(key=KEY, comments=None, resolved=False, kind=CommentKind.REVIEW):
    return Thread(key=key, kind=kind, is_resolved=resolved, path="f", line=1,
                  anchor=ThreadAnchor(side=Side.AFTER, original_line=1),
                  comments=tuple(comments or [_comment()]))


@dataclass(frozen=True)
class Seen:
    polled: Any
    active: list[str]
    stale: list[str]
    arrived: list[int | None]


class Diffing:
    def __init__(self, settings, clock=None):
        self.here = world(without_runs(settings), clock=clock)
        self.here.github.add_pr(THE_PR)
        repo_at(self.here.working_copies, WORKTREE)
        self.threads = self.here.threads()
        self.poll()

    def show(self, *threads: Thread) -> None:
        self.here.github.prs[THE_PR].threads.clear()
        for thread in threads:
            self.here.github.add_thread(THE_PR, thread)

    def poll(self, *threads: Thread) -> Seen:
        self.show(*threads)
        return self.seen()

    def seen(self) -> Seen:
        polled = self.threads.poll(PullRequestState())
        polled.commit()
        news = FakeNotifications()
        polled.announce(news)
        found = polled.activity
        if found is not None:
            self.threads.absorb(found)
        return Seen(polled=polled,
                    active=[] if found is None else [thread.key for thread in found.threads],
                    stale=[] if found is None else [thread.key for thread in found.stale],
                    arrived=[item.comment_id for item in news.gathered
                             if isinstance(item, CommentArrived)])

    def changes(self, before: list[Thread], after: list[Thread]) -> Seen:
        self.poll()
        self.poll(*before)
        return self.poll(*after)

    def cursor_written_before(self, cursor: dict[str, Any]) -> None:
        self.here.thread_records.of(THE_PR).save("cursor", "poll", json.dumps(cursor).encode())

    def board_replies(self, thread: Thread, text: str = "landed") -> ThreadComment:
        self.show(thread)
        hear(self.threads)
        with self.threads.editing(thread.key) as editable:
            replied = editable.reply(text)
        assert not isinstance(replied, Denied), replied
        drain(self.threads)
        return self.board_comment()

    def board_comment(self) -> ThreadComment:
        [comment] = [comment for thread in self.here.github.threads(THE_PR)
                     for comment in thread.comments if comment.author == BOT]
        return comment

    def rewrite(self, key: str, **fields: Any) -> None:
        record = self.here.github.prs[THE_PR]
        [thread] = [one for one in record.threads if one.key == key]
        record.threads.remove(thread)
        self.here.github.add_thread(THE_PR, replace(thread, **fields))


def test_the_first_poll_after_the_fetch_grew_reports_nothing_new(settings):
    diffing = Diffing(settings)
    fuller = _comment(author_name="Robin Reviewer", review_state=ReviewState.COMMENTED)

    result = diffing.changes([_thread()], [_thread(comments=[fuller])])

    assert (result.active, result.stale) == ([], [])


def test_a_thread_whose_reply_was_edited_is_stale(settings):
    diffing = Diffing(settings)
    before = _thread(comments=[_comment(), _comment(2, body="typo")])
    after = _thread(comments=[_comment(), _comment(2, body="typo — I meant the other one")])

    result = diffing.changes([before], [after])

    assert result.active == []
    assert result.stale == [KEY]


def test_a_thread_whose_root_comment_was_edited_reopens(settings):
    diffing = Diffing(settings)
    before = _thread(comments=[_comment(body="rename this")])
    after = _thread(comments=[_comment(body="rename this to _reference")])

    result = diffing.changes([before], [after])

    assert result.active == [KEY], "the root comment is the instruction the agent worked from"
    assert result.arrived == [1]
    assert result.stale == []


def test_a_thread_that_lost_a_reply_is_stale(settings):
    diffing = Diffing(settings)
    before = _thread(comments=[_comment(), _comment(2, body="never mind")])

    result = diffing.changes([before], [_thread()])

    assert result.active == []
    assert result.stale == [KEY]


def test_the_boards_own_reply_makes_the_thread_stale_but_never_reopens_it(settings):
    diffing = Diffing(settings)
    diffing.board_replies(_thread())

    result = diffing.seen()

    assert result.active == [], "our own reply never reopens the thread"
    assert result.stale == [KEY]


def test_an_id_only_snapshot_calls_nothing_stale(settings):
    diffing = Diffing(settings)
    thread = _thread(comments=[_comment(), _comment(2, body="and this")])
    diffing.poll(thread)
    diffing.cursor_written_before({KEY: [1, 2]})

    result = diffing.poll(thread)

    assert result.active == []
    assert result.stale == [], (
        "the snapshot written before fingerprints existed knows no bodies, so "
        "the first cycle after the upgrade must stay quiet"
    )


def test_a_comment_the_cutoff_deferred_is_reported_on_the_next_cycle(settings):
    clock = Moment("2026-09-01T10:00:10Z")
    diffing = Diffing(settings, clock=clock)
    thread = _thread(comments=[
        _comment(created_at="2026-09-01T10:00:00Z"),
        _comment(2, created_at="2026-09-01T10:00:09Z"),
    ])

    first = diffing.poll(thread)
    clock.iso = "2026-09-01T10:01:05Z"
    second = diffing.poll(thread)

    assert first.arrived == [1], "the reply younger than the cutoff waits for the next cycle"
    assert second.active == [KEY]
    assert second.arrived == [2]


def test_a_thread_that_gained_a_reply_is_active_with_only_the_fresh_comment(settings):
    diffing = Diffing(settings)

    result = diffing.changes([_thread()], [_thread(comments=[_comment(), _comment(2)])])

    assert result.active == [KEY]
    assert result.arrived == [2]
    assert [c.id for c in result.polled.activity.threads[0].comments] == [1, 2]


def test_our_own_marked_reply_whose_id_was_never_recorded_does_not_reopen(settings):
    diffing = Diffing(settings)
    marked = _comment(2, author=BOT, body="\U0001F916 landed in abc123")

    result = diffing.changes([_thread()], [_thread(comments=[_comment(), marked])])

    assert result.active == []


def test_a_marked_reply_by_someone_else_still_reopens_the_thread(settings):
    diffing = Diffing(settings)
    marked = _comment(2, author="colleague", body="\U0001F916 landed in abc123")

    result = diffing.changes([_thread()], [_thread(comments=[_comment(), marked])])

    assert result.active == [KEY]


def test_a_marked_comment_by_a_deleted_account_is_never_ours(settings):
    diffing = Diffing(settings)

    result = diffing.poll(_thread(comments=[_comment(author="", body="\U0001F916 anything")]))

    assert result.active == [KEY]


def test_posted_reply_ids_do_not_apply_to_an_issue_comment(settings):
    diffing = Diffing(settings)
    reply = diffing.board_replies(_thread())
    diffing.seen()

    diffing.here.github.add_thread(THE_PR, _thread(
        key="IC_one", kind=CommentKind.ISSUE, comments=[_comment(reply.id)]))
    result = diffing.seen()

    assert result.active == ["IC_one"], (
        "review and issue comments are separate id spaces; an issue comment "
        "sharing a number with a posted review reply is not that reply"
    )


def _board_commented_on_the_pr(diffing):
    diffing.board_replies(_thread(key="IC_root", kind=CommentKind.ISSUE,
                                  comments=[_comment(7, body="please fix this")]), "fixed")
    posted = diffing.board_comment()
    [ours] = [thread.key for thread in diffing.here.github.threads(THE_PR)
              if posted in thread.comments]
    return ours


def test_a_pr_comment_the_board_posted_is_neither_active_nor_stale(settings):
    diffing = Diffing(settings)
    _board_commented_on_the_pr(diffing)

    result = diffing.seen()

    assert result.active == []
    assert result.stale == []


def test_an_edit_to_a_pr_comment_the_board_posted_says_nothing_either(settings):
    diffing = Diffing(settings)
    ours = _board_commented_on_the_pr(diffing)
    diffing.seen()
    [posted] = diffing.here.github.thread(ours).comments

    diffing.rewrite(ours, comments=(replace(posted, body="edited", updated_at=None),))
    result = diffing.seen()

    assert result.active == []
    assert result.stale == []


def test_a_thread_github_resolved_with_nobody_speaking_is_stale(settings):
    diffing = Diffing(settings)

    resolved = diffing.changes([_thread(resolved=False)], [_thread(resolved=True)])
    reopened = diffing.changes([_thread(resolved=True)], [_thread(resolved=False)])

    assert resolved.stale == [KEY]
    assert resolved.active == [], "the flag moved and the words did not: a refresh, never a reopen"
    assert reopened.stale == [KEY]
    assert reopened.active == []


def test_a_snapshot_written_before_the_flag_says_nothing_about_resolution(settings):
    diffing = Diffing(settings)
    diffing.poll(_thread())
    current = json.loads(diffing.here.thread_records.of(THE_PR).load("cursor", "poll"))
    diffing.cursor_written_before({KEY: current[KEY]["comments"]})

    result = diffing.poll(_thread(resolved=True))

    assert (result.active, result.stale) == ([], []), (
        "the first cycle after the upgrade is quiet; the next write fills the flag in"
    )


def test_a_resolved_thread_is_still_diffed(settings):
    diffing = Diffing(settings)
    before = _thread(resolved=True, comments=[_comment(), _comment(2, body="typo")])
    edited = _thread(resolved=True,
                     comments=[_comment(), _comment(2, body="typo — the other one")])
    replied = _thread(resolved=True, comments=[
        _comment(), _comment(2, body="typo"), _comment(3, author="jeffrey", body="done")])

    drifted = diffing.changes([before], [edited])
    answered = diffing.changes([before], [replied])

    assert [(t.key, t.is_resolved) for t in drifted.polled.activity.stale] == [
        (KEY, True)]
    assert drifted.active == []
    assert answered.active == [KEY]


def test_a_resolved_thread_that_goes_leaves_the_cursor(settings):
    diffing = Diffing(settings)
    diffing.changes([_thread(resolved=True)], [])

    back = diffing.poll(_thread(resolved=True))

    assert back.active == [KEY]
