from github_orchestrator.change_detection import Poll
from github_orchestrator.conversation import ConversationState
from github_orchestrator.domain import Mention
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    ReviewState,
    Thread,
    ThreadComment,
)
from tests.builders import a_pr
from tests.change_detection.support import POLLED_AT
from tests.conversation.support import PR, REPO, drain, world

THE_PR = a_pr(PR, REPO)
ME = "octocat"


def _said(comment_id, author, body, at):
    return ThreadComment(id=comment_id, author=author, body=body, created_at=at)


def _review_thread(key, *comments):
    return Thread(key=key, kind=CommentKind.REVIEW, path="f", line=1, comments=comments)


def _issue(key, comment):
    return Thread(key=key, kind=CommentKind.ISSUE, comments=(comment,))


def _review_body(key, comment):
    return Thread(key=key, kind=CommentKind.REVIEW_SUMMARY, state=ReviewState.COMMENTED,
                  comments=(comment,))


def _mentions(settings, *threads, body="", author="anna"):
    here = world(settings)
    state = PullRequestState(author=author, body=body)
    here.github.add_pr(THE_PR, state)
    for thread in threads:
        here.github.add_thread(THE_PR, thread)
    return here.conversation_managers.of(THE_PR).poll(state).mentions


def test_a_comment_naming_me_is_a_mention_saying_who_when_and_where(settings):
    mentions = _mentions(settings, _review_thread(
        "PRRT_one", _said(101, "anna", "@octocat what do you think?", "2026-09-01T10:00:00Z")))

    assert mentions == (Mention(author="anna", at="2026-09-01T10:00:00Z", kind="review",
                                thread="PRRT_one", comment_id=101,
                                body="@octocat what do you think?", answered=False),)


def test_only_my_name_as_a_whole_word_by_someone_else_is_a_mention(settings):
    mentions = _mentions(
        settings,
        _issue("IC_1", _said(1, "anna", "ask @octocat-bot", "2026-09-01T10:00:00Z")),
        _issue("IC_2", _said(2, "anna", "mail me at x@octocat.com", "2026-09-01T10:01:00Z")),
        _issue("IC_3", _said(3, ME, "note to self @octocat", "2026-09-01T10:02:00Z")),
        _issue("IC_4", _said(4, "bob", "(@OctoCat, see this)", "2026-09-01T10:03:00Z")),
    )

    assert [(mention.author, mention.comment_id) for mention in mentions] == [("bob", 4)]


def test_a_mention_on_a_review_thread_is_answered_by_my_later_reply_on_that_thread(settings):
    mentions = _mentions(
        settings,
        _review_thread("PRRT_one",
                       _said(1, "anna", "@octocat?", "2026-09-01T10:00:00Z"),
                       _said(2, ME, "done", "2026-09-01T11:00:00Z")),
        _review_thread("PRRT_two",
                       _said(3, "anna", "@octocat here too", "2026-09-01T12:00:00Z")),
        _issue("IC_1", _said(4, ME, "replied above", "2026-09-01T13:00:00Z")),
    )

    assert [(mention.thread, mention.answered) for mention in mentions] == [
        ("PRRT_one", True), ("PRRT_two", False)]


def test_a_top_level_mention_is_answered_by_a_later_comment_of_mine_on_the_pr(settings):
    mentions = _mentions(
        settings,
        _issue("IC_1", _said(1, ME, "first", "2026-09-01T09:00:00Z")),
        _issue("IC_2", _said(2, "anna", "@octocat ping", "2026-09-01T10:00:00Z")),
        _review_body("PRR_1", _said(3, "bob", "and @octocat this", "2026-09-01T12:00:00Z")),
        _issue("IC_3", _said(4, ME, "on it", "2026-09-01T11:00:00Z")),
    )

    assert [(mention.kind, mention.answered) for mention in mentions] == [
        ("issue", True), ("review-summary", False)]


def test_a_mention_in_the_pr_body_is_the_authors_and_answered_by_any_comment_of_mine(settings):
    unanswered = _mentions(settings, body="cc @octocat")
    answered = _mentions(settings, _issue("IC_1", _said(1, ME, "seen", "2026-09-01T09:00:00Z")),
                         body="cc @octocat")

    assert unanswered == (Mention(author="anna", at=None, kind="pr-body", thread="pr-body",
                                  comment_id=None, body="cc @octocat", answered=False),)
    assert [mention.answered for mention in answered] == [True]


def test_my_own_pr_body_naming_me_is_no_mention(settings):
    assert _mentions(settings, body="cc @octocat", author=ME) == ()


def test_naming_me_as_the_detailed_reviewer_is_no_mention(settings):
    template = "## Review\n\nDetailed reviewer: @octocat\n"

    assert _mentions(settings, body=template) == ()
    assert [mention.kind for mention in _mentions(
        settings, body=template + "\ncc @octocat on the schema")] == ["pr-body"]


def test_a_thread_fetch_that_fails_knows_no_mentions(settings):
    here = world(settings)
    state = PullRequestState(author="anna", body="cc @octocat")

    assert here.conversation_managers.of(THE_PR).poll(state).mentions is None


def _watching(settings, *threads, body="", author="anna"):
    here = world(settings)
    state = PullRequestState(author=author, body=body)
    here.github.add_pr(THE_PR, state)
    for thread in threads:
        here.github.add_thread(THE_PR, thread)
    here.change_detection.advance(THE_PR, Poll(state, POLLED_AT), set())
    return here, state


def _heard(here, state):
    manager = here.conversation_managers.of(THE_PR)
    polled = manager.poll(state)
    polled.commit()
    if polled.activity is not None:
        manager.absorb(polled.activity)
    here.change_detection.advance(
        THE_PR, Poll(state, POLLED_AT, mentions=polled.mentions), set())
    return manager


def test_the_first_poll_of_someone_elses_pr_opens_a_conversation_for_each_unanswered_mention(settings):
    here, state = _watching(
        settings,
        _issue("IC_1", _said(1, "anna", "@octocat ping", "2026-09-01T10:00:00Z")),
        _issue("IC_2", _said(2, "anna", "no name here", "2026-09-01T10:01:00Z")),
        _review_body("PRR_1", _said(3, "bob", "and @octocat this", "2026-09-01T12:00:00Z")),
        body="cc @octocat")

    manager = _heard(here, state)

    assert sorted(conversation.key for conversation in manager.all()) == [
        "IC_1", "PRR_1", "pr-body"]
    opening = manager.get("pr-body")
    assert (opening.comment_type, opening.author, opening.body) == ("pr-body", "anna",
                                                                    "cc @octocat")


def test_the_first_poll_of_my_own_pr_opens_nothing_for_a_comment_naming_me(settings):
    here, state = _watching(
        settings, _issue("IC_1", _said(1, "anna", "@octocat ping", "2026-09-01T10:00:00Z")),
        author=ME)

    assert _heard(here, state).all() == []


def test_a_conversation_holding_a_mention_i_have_not_answered_is_marked_a_mention(settings):
    here, state = _watching(
        settings,
        _issue("IC_1", _said(1, "anna", "@octocat ping", "2026-09-01T10:00:00Z")),
        _review_thread("PRRT_one", _said(2, "bob", "rename this", "2026-09-01T11:00:00Z")))

    manager = _heard(here, state)

    assert {conversation.key: conversation.mention for conversation in manager.all()} == {
        "IC_1": True, "PRRT_one": False}
    assert manager.get("IC_1").mention is True


def test_a_mention_i_answered_on_github_is_no_longer_marked(settings):
    here, state = _watching(
        settings, _issue("IC_1", _said(1, "anna", "@octocat ping", "2026-09-01T10:00:00Z")))
    _heard(here, state)
    here.github.add_thread(THE_PR, _issue("IC_2", _said(2, ME, "on it", "2026-09-01T11:00:00Z")))

    manager = _heard(here, state)

    assert manager.get("IC_1").mention is False


def _replied_and_resolved(here, state, key, reply):
    manager = here.conversation_managers.of(THE_PR)
    with manager.editing(key) as editable:
        editable.resolve(reply=reply)
    drain(manager)
    return _heard(here, state)


def _posted_on_the_pr(here):
    return [comment.body for thread in here.github.threads(THE_PR)
            if thread.kind is CommentKind.ISSUE for comment in thread.comments
            if comment.author == ME]


def test_reply_and_resolve_on_a_review_thread_mention_replies_there_and_resolves_here_only(settings):
    here, state = _watching(settings, _review_thread(
        "PRRT_one", _said(1, "anna", "@octocat is this right?", "2025-12-01T10:00:00Z")))
    _heard(here, state)

    manager = _replied_and_resolved(here, state, "PRRT_one", "yes, go ahead")

    thread = here.github.thread("PRRT_one")
    assert thread.comments[-1].body == "yes, go ahead"
    assert not thread.is_resolved
    assert manager.get("PRRT_one").standing is ConversationState.DONE
    assert manager.get("PRRT_one").mention is False
    assert here.change_detection.facts(THE_PR).mentions[0].answered is True


def test_reply_and_resolve_on_a_conversation_comment_mention_quotes_it_on_the_pr(settings):
    here, state = _watching(
        settings, _issue("IC_1", _said(1, "anna", "@octocat ping", "2025-12-01T10:00:00Z")))
    _heard(here, state)

    manager = _replied_and_resolved(here, state, "IC_1", "pong")

    assert _posted_on_the_pr(here) == ["@anna\n\n> @octocat ping\n\npong"]
    assert manager.get("IC_1").standing is ConversationState.DONE
    assert here.change_detection.facts(THE_PR).mentions[0].answered is True
    assert sorted(conversation.key for conversation in manager.all()) == ["IC_1"]


def test_reply_and_resolve_on_a_pr_body_mention_names_the_author_without_quoting_the_body(settings):
    here, state = _watching(settings, body="A long description.\n\ncc @octocat")
    _heard(here, state)

    manager = _replied_and_resolved(here, state, "pr-body", "looks fine")

    assert _posted_on_the_pr(here) == ["@anna\n\nlooks fine"]
    assert manager.get("pr-body").standing is ConversationState.DONE
    assert here.change_detection.facts(THE_PR).mentions[0].answered is True


def test_a_mention_its_writer_spoke_last_on_is_mine_to_decide_not_waiting_on_the_author(settings):
    here, state = _watching(
        settings, _issue("IC_1", _said(1, "anna", "@octocat ping", "2026-09-01T10:00:00Z")))

    manager = _heard(here, state)

    assert manager.get("IC_1").standing is ConversationState.READY


def test_a_review_thread_mention_its_writer_spoke_last_on_is_mine_to_decide(settings):
    here, state = _watching(settings, _review_thread(
        "PRRT_one", _said(1, "anna", "@octocat is this right?", "2026-09-01T10:00:00Z")))

    manager = _heard(here, state)

    assert manager.get("PRRT_one").standing is ConversationState.READY
