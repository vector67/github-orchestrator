import time

import pytest

from github_orchestrator.conversation import (
    ConversationState,
    OperationState,
    Verdict,
)
from github_orchestrator.conversation import (
    ReviewState as ThreadReviewState,
)
from github_orchestrator.domain import Location, Side
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    ReviewState,
    Thread,
    ThreadComment,
)
from github_orchestrator.github.fake import FAKE_NOW, FakeGitHub, ThreadAnchor
from tests.builders import a_pr
from tests.conversation.support import (
    PR,
    REPO,
    WORKTREE,
    diff_over,
    drain,
    hear,
    propose,
    repo_at,
    world,
)

THE_PR = a_pr(PR, REPO)

ME = "octocat"
HEAD = "a" * 40


def _comment(comment_id, author="reviewer", body="Please fix this.", **fields):
    return ThreadComment(id=comment_id, author=author, body=body,
                         created_at="2026-09-01T10:00:00Z",
                         updated_at="2026-09-01T10:00:00Z", **fields)


def _review_thread(key="PRRT_one", *comments):
    return Thread(key=key, kind=CommentKind.REVIEW, path="src/app.py", line=12,
                  anchor=ThreadAnchor(side=Side.AFTER, start_line=12, original_line=12,
                                      original_commit="c" * 40),
                  comments=comments or (_comment(101),), is_resolved=False)


def _github(*threads, github=None):
    github = github or FakeGitHub(account=ME)
    github.add_pr(THE_PR, PullRequestState(author="anna"))
    for thread in threads:
        github.add_thread(THE_PR, thread)
    return github


def _world(settings, *threads, github=None):
    built = world(settings, github=_github(github=github))
    built.polled(head_sha=HEAD)
    built.conversation_managers.of(THE_PR).poll(PullRequestState()).commit()
    for thread in threads:
        built.github.add_thread(THE_PR, thread)
    return built




def _heard(built, is_author=False):
    repo_at(built.working_copies, WORKTREE)
    threads = built.threads(is_author=is_author)
    hear(threads)
    return threads


def _replied(built, key, text):
    threads = _heard(built)
    with threads.editing(key) as editable:
        editable.reply(text)
    drain(threads)
    return threads.get(key)


def _decided(threads, key, verb, *args, **kwargs):
    with threads.editing(key) as conversation:
        getattr(conversation, verb)(*args, **kwargs)
    drain(threads)
    return threads.get(key)


def _fields(comment):
    return (comment.id, comment.author, comment.body, comment.created_at, comment.updated_at)


def _issue_thread(key, comment_type="issue", author="reviewer", body="Please fix this."):
    kind = CommentKind.ISSUE if comment_type == "issue" else CommentKind.REVIEW_SUMMARY
    state = None if comment_type == "issue" else ReviewState.COMMENTED
    return Thread(key=key, kind=kind, state=state,
                  comments=(_comment(55, author=author, body=body),))


def test_a_review_comment_is_answered_on_its_own_thread(settings):
    built = _world(settings, _review_thread())

    stored = _replied(built, "PRRT_one", "on it")

    reply = built.github.thread("PRRT_one").comments[-1]
    assert (reply.author, reply.body) == (ME, "on it")
    assert _fields(stored.comments[-1]) == (reply.id, ME, "on it", FAKE_NOW, FAKE_NOW)
    assert stored.posted_comment_keys == ()


@pytest.mark.parametrize("comment_type", ["issue", "review-summary"])
def test_a_comment_with_no_thread_is_answered_on_the_pr_mentioning_and_quoting_it(
        settings, comment_type):
    built = _world(settings, _issue_thread("IC_one", comment_type))

    stored = _replied(built, "IC_one", "on it")

    [posted_key] = stored.posted_comment_keys
    thread = built.github.thread(posted_key)
    assert thread.kind is CommentKind.ISSUE
    assert thread.comments[0].body == "@reviewer\n\n> Please fix this.\n\non it"
    assert _fields(stored.comments[-1]) == _fields(thread.comments[0])
    polled = built.conversation_managers.of(THE_PR).poll(PullRequestState())
    assert polled.activity is None, (
        "a comment of ours on the PR has to stay off the next poll")


@pytest.mark.parametrize(("reply", "posted"), [
    ("done", "done\n\n{link}"),
    ("", "\U0001F916 {link}"),
])
def test_the_commit_that_answers_the_comment_is_linked_under_the_reply(
        settings, reply, posted):
    built = _world(settings, _review_thread())
    threads = _heard(built, is_author=None)
    propose(built, threads, "PRRT_one")

    stored = _decided(threads, "PRRT_one", "approve", reply=reply)

    _, landed = stored.fix.commits
    link = f"[{str(landed)[:7]}](https://github.com/{REPO}/commit/{landed})"
    assert built.github.thread("PRRT_one").comments[-1].body == posted.format(link=link)
    assert stored.standing is ConversationState.DONE


def test_a_plain_reply_carries_no_commit_link(settings):
    built = _world(settings, _review_thread())

    _replied(built, "PRRT_one", "please explain")

    assert built.github.thread("PRRT_one").comments[-1].body == "please explain"


def test_a_posted_draft_is_answered_and_resolved_on_the_thread_github_gave_it(settings):
    built = _world(settings)
    threads = _reviewing(built)
    key = _decided(threads, _drafted(threads, "please fix", _anchor()), "post_now").key
    [posted] = built.github.threads(THE_PR)

    _decided(threads, key, "reply", "on it")
    stored = _decided(threads, key, "resolve", resolve=True)

    assert built.github.thread(posted.key).comments[-1].body == "on it"
    assert built.github.thread(posted.key).is_resolved is True
    assert stored.standing is ConversationState.DONE


def test_the_thread_the_conversation_names_is_resolved_and_unresolved(settings):
    built = _world(settings, _review_thread())
    threads = _heard(built)

    _decided(threads, "PRRT_one", "resolve", resolve=True)
    resolved = built.github.thread("PRRT_one").is_resolved
    _decided(threads, "PRRT_one", "unpark")

    assert (resolved, built.github.thread("PRRT_one").is_resolved) == (True, False)


def test_the_thumbs_up_goes_on_the_newest_other_comment_and_not_the_root(settings):
    built = _world(settings, _review_thread("PRRT_one", _comment(101, author=ME),
                                            _comment(404, author="anna")))
    threads = _heard(built)

    _decided(threads, "PRRT_one", "resolve", resolve=True)

    assert built.github.reactions == {404: ["+1"]}


def test_the_comment_the_conversation_names_is_deleted(settings):
    built = _world(settings, _issue_thread("IC_one", author=ME))
    threads = _heard(built)

    stored = _decided(threads, "IC_one", "resolve", delete_comment=True)

    assert built.github.comment_exists(THE_PR, CommentKind.ISSUE, 55) is False
    assert stored.comment_deleted is True


class _Answering(FakeGitHub):
    def __init__(self, account):
        super().__init__(account)
        self.answered = {}

    def comment_exists(self, pr, kind, comment_id):
        present = super().comment_exists(pr, kind, comment_id)
        self.answered[comment_id] = present
        return present


def _eventually(check, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not check() and time.monotonic() < deadline:
        time.sleep(0.01)
    return check()


def test_github_is_asked_whether_the_comment_is_still_there(settings):
    github = _Answering(ME)
    built = _world(settings, _review_thread("PRRT_one", _comment(101)),
                   _review_thread("PRRT_lost", _comment(202)), github=github)
    diff_over(built, "src/app.py", is_author=True)
    threads = built.threads()
    hear(threads)
    draft = _drafted(threads, "please fix", _anchor())
    github.delete_comment(THE_PR, CommentKind.REVIEW, 202)

    for key in ("PRRT_one", "PRRT_lost", draft):
        threads.recheck(threads.get(key))

    assert _eventually(lambda: threads.get("PRRT_lost").is_removed)
    assert _eventually(lambda: {101, 202} <= github.answered.keys())
    assert threads.get("PRRT_lost").comment_deleted is True
    one = threads.get("PRRT_one")
    assert (one.is_removed, one.comment_deleted) == (False, False)
    assert threads.get(draft).standing is ConversationState.DRAFT
    assert github.answered == {101: True, 202: False}, "a draft is never asked of GitHub"


def test_one_thread_is_queued_as_the_review_domain_sees_it(settings):
    built = _world(settings, _review_thread("PRRT_one", _comment(101), _comment(102)))

    polled = built.conversation_managers.of(THE_PR).poll(PullRequestState())

    [thread] = polled.activity.threads
    assert (thread.key, thread.kind, thread.path, thread.line, thread.is_resolved,
            thread.resolved_by, thread.state) == (
        "PRRT_one", "review", "src/app.py", 12, False, None, None)
    anchor = thread.anchor
    assert (anchor.is_outdated, anchor.side, anchor.start_line, anchor.original_line,
            anchor.original_start_line, anchor.original_commit) == (
        False, Side.AFTER, 12, 12, None, "c" * 40)
    assert [(c.id, c.author, c.body, c.created_at, c.updated_at, c.author_name,
             c.review_state) for c in thread.comments] == [
        (comment_id, "reviewer", "Please fix this.", "2026-09-01T10:00:00Z",
         "2026-09-01T10:00:00Z", "", None) for comment_id in (101, 102)]


def test_a_materialised_thread_carries_githubs_comments_and_anchor(settings):
    built = _world(settings, _review_thread("PRRT_one", _comment(101), _comment(102)))
    polled = built.conversation_managers.of(THE_PR).poll(PullRequestState())

    threads = built.threads(is_author=False)
    threads.absorb(polled.activity)

    stored = threads.get("PRRT_one")
    assert [(c.id, c.author) for c in stored.comments] == [(101, "reviewer"),
                                                            (102, "reviewer")]
    assert (stored.path, stored.line, stored.side, stored.start_line,
            stored.original_line, stored.original_commit) == (
        "src/app.py", 12, Side.AFTER, 12, 12, "c" * 40)
    assert (stored.comment_id, stored.comment_type, stored.author,
            stored.github_node_id) == (101, "review", "reviewer", "PRRT_one")


def test_a_review_summary_keeps_its_reviewers_name_and_verdict(settings):
    built = _world(settings, Thread(
        key="PRR_one", kind=CommentKind.REVIEW_SUMMARY, state=ReviewState.CHANGES_REQUESTED,
        comments=(_comment(77, author_name="Rhea Viewer"),)))
    polled = built.conversation_managers.of(THE_PR).poll(PullRequestState())

    threads = built.threads(is_author=False)
    threads.absorb(polled.activity)

    stored = threads.get("PRR_one")
    assert (stored.reviewer_name, stored.review_state) == (
        "Rhea Viewer", ThreadReviewState.CHANGES_REQUESTED)
    assert stored.comments[0].author_name == "Rhea Viewer"


def _anchor(line=12, side=Side.AFTER, start_line=None):
    return Location(path="src/app.py", line=line, side=side, start_line=start_line,
                    start_side=None if start_line is None else side)


def _reviewing(built):
    diff_over(built, "src/app.py")
    return built.threads(is_author=False)


def _drafted(threads, body, anchor):
    return threads.open_draft(body, anchor).key


def test_a_draft_is_posted_and_names_the_thread_it_became(settings):
    built = _world(settings)
    threads = _reviewing(built)
    key = _drafted(threads, "please fix", _anchor())

    stored = _decided(threads, key, "post_now")

    [thread] = built.github.threads(THE_PR)
    assert (thread.path, thread.line, thread.comments[0].body) == (
        "src/app.py", 12, "please fix")
    assert stored.github_node_id == thread.key
    assert [_fields(comment) for comment in stored.comments] == [_fields(thread.comments[0])]
    assert (stored.standing, stored.comment_type) == (ConversationState.WAITING, "review")


def _enrolled(threads, body, anchor):
    key = _drafted(threads, body, anchor)
    _decided(threads, key, "enrol")
    return key


def _reviewed(threads, verdict, body=None):
    threads.send_review(verdict, body)
    drain(threads)
    [review] = threads.reviews()
    return review


def test_each_drafts_comment_and_the_thread_it_opened_are_named(settings):
    built = _world(settings)
    threads = _reviewing(built)
    keys = [_enrolled(threads, "rename", _anchor()),
            _enrolled(threads, "gone", _anchor(line=30, start_line=28, side=Side.BEFORE)),
            _enrolled(threads, "rename", _anchor(line=40))]

    review = _reviewed(threads, Verdict.COMMENT, "a few things")

    by_line = {t.line: t for t in built.github.threads(THE_PR)
               if t.kind is CommentKind.REVIEW}
    stored = [threads.get(key) for key in keys]
    assert [(one.comments[0].body, one.github_node_id) for one in stored] == [
        ("rename", by_line[12].key), ("gone", by_line[30].key),
        ("rename", by_line[40].key)]
    assert [one.comment_id for one in stored] == [
        by_line[line].comments[0].id for line in (12, 30, 40)]
    assert by_line[30].anchor.start_line == 28
    assert stored[0].comments[0].author == ME
    assert (review.state, review.posted_review is not None) == (OperationState.APPLIED, True)
    assert built.github.pr_state(THE_PR).reviews[-1].state is ReviewState.COMMENTED


class _NotListedYet(FakeGitHub):
    def threads(self, pr):
        return [t for t in super().threads(pr) if t.comments[0].body != "gone"]


def test_a_thread_github_does_not_list_yet_is_left_for_the_poller(settings):
    built = _world(settings, github=_NotListedYet(account=ME))
    threads = _reviewing(built)
    listed = _enrolled(threads, "rename", _anchor())
    unlisted = _enrolled(threads, "gone", _anchor(line=30))

    _reviewed(threads, Verdict.COMMENT, "a few things")

    assert threads.get(listed).github_node_id is not None
    assert threads.get(unlisted).github_node_id is None
    assert threads.get(unlisted).comments[0].body == "gone"
    assert threads.get(unlisted).comment_id is not None


def test_a_review_with_no_drafts_names_only_the_review(settings):
    built = _world(settings)

    review = _reviewed(_reviewing(built), Verdict.APPROVE)

    assert review.posted_review is not None
    assert review.drafts == ()
    assert built.github.pr_state(THE_PR).reviews[-1].approves
