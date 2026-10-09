from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from github_orchestrator.conversation._domain.conversation import (
    ASSUMED_DONE,
    NOT_MINE,
    OPEN,
    ROLE_REVIEWER,
    WAITING_ON_REVIEWER,
    Conversation,
    ThreadVerdict,
)
from github_orchestrator.conversation._domain.diff import (
    KIND_ISSUE,
    KIND_REVIEW,
    KIND_REVIEW_SUMMARY,
)
from github_orchestrator.conversation._domain.mentions import (
    KIND_PR_BODY,
    names_the_viewer,
)
from github_orchestrator.domain import AuthorKind, author_kind_of

PLACED_BY_A_VERDICT = (OPEN, WAITING_ON_REVIEWER, ASSUMED_DONE, NOT_MINE)

MAX_VERDICT_ASKS = 3

RETRY_AFTER = timedelta(minutes=10)

STATE_OF_VERDICT = {
    ThreadVerdict.MY_MOVE: OPEN,
    ThreadVerdict.NEEDS_VERIFICATION: OPEN,
    ThreadVerdict.THEIR_MOVE: WAITING_ON_REVIEWER,
    ThreadVerdict.ASSUMED_DONE: ASSUMED_DONE,
    ThreadVerdict.NOT_MINE: NOT_MINE,
}

MEANINGS = {
    ThreadVerdict.MY_MOVE: "viewer has to act: someone asks viewer something or asks for "
                           "viewer's input, or a comment since viewer's last comment answers "
                           "viewer, pushes back on viewer, or declines or postpones what viewer "
                           "asked for without saying any part of it is done",
    ThreadVerdict.NEEDS_VERIFICATION: "a comment since viewer's last comment, by anyone, says "
                                      "what viewer asked for, or part of it, has been done, "
                                      "changed or fixed, with or without a commit, and asks "
                                      "viewer nothing; the PR author replying with only an "
                                      "approving emoji such as a thumbs-up counts as saying it "
                                      "is done",
    ThreadVerdict.THEIR_MOVE: "viewer has said their piece and is still waiting on someone "
                              "else: nobody has replied since viewer's last comment, another "
                              "reviewer only agrees with viewer, the PR author only promises to "
                              "look into it, or the reply passes viewer's question on to "
                              "someone else to answer",
    ThreadVerdict.ASSUMED_DONE: "settled: viewer confirmed or approved after the fix, and "
                                "nothing is left to do",
    ThreadVerdict.NOT_MINE: "the thread asks nothing of viewer and viewer is not waiting on "
                            "anything in it: other people discussing their own points, review "
                            "comments for the PR author, a bot summary, or viewer only gave an "
                            "opinion when someone else asked for it and the open question is "
                            "now for another person",
}

KIND_WORDS = {
    KIND_REVIEW: "a line thread",
    KIND_ISSUE: "a conversation comment",
    KIND_REVIEW_SUMMARY: "a review summary",
    KIND_PR_BODY: "the PR description",
}

YOU = "you"


@dataclass(frozen=True)
class VerdictFacts:
    comments: tuple[tuple[str, str, str], ...]
    viewer: str
    pr_author: str
    spoke_last: str
    viewer_commented: bool
    mentions_viewer: bool
    kind: str


def newest_said(conversation: Conversation) -> str | None:
    if not conversation.comments:
        return None
    newest = conversation.comments[-1]
    return str(newest.id) if newest.id is not None else f"#{len(conversation.comments)}"


def _label(login: str, viewer: str, pr_author: str) -> str:
    if login == viewer:
        return YOU
    if pr_author and login == pr_author:
        return "PR author"
    if author_kind_of(login, viewer) is AuthorKind.BOT:
        return "bot"
    return "colleague"


def facts_of(conversation: Conversation, viewer: str, pr_author: str | None) -> VerdictFacts:
    author = pr_author or ""
    labelled = tuple((_label(comment.author, viewer, author), comment.author, comment.body)
                     for comment in conversation.comments)
    last = f"{labelled[-1][0]} {labelled[-1][1]}" if labelled else ""
    return VerdictFacts(
        comments=labelled, viewer=viewer, pr_author=author, spoke_last=last,
        viewer_commented=any(label == YOU for label, _, _ in labelled),
        mentions_viewer=any(names_the_viewer(comment, viewer)
                            for comment in conversation.comments),
        kind=KIND_WORDS.get(conversation.comment_type, conversation.comment_type))


def retry_due(asks: int, asked_at: str | None, now: str | None) -> bool:
    if asks >= MAX_VERDICT_ASKS or now is None:
        return False
    return (asked_at is None
            or datetime.fromisoformat(now) - datetime.fromisoformat(asked_at) >= RETRY_AFTER)


def verdict_due(conversation: Conversation, now: str | None) -> bool:
    newest = newest_said(conversation)
    if (conversation.role != ROLE_REVIEWER or conversation.state not in PLACED_BY_A_VERDICT
            or newest is None or conversation.verdict_for == newest):
        return False
    return conversation.verdict_asked_for != newest or retry_due(
        conversation.verdict_asks, conversation.verdict_asked_at, now)


def with_an_ask(conversation: Conversation, at: str | None) -> Conversation:
    newest = newest_said(conversation)
    asks = conversation.verdict_asks + 1 if conversation.verdict_asked_for == newest else 1
    return replace(conversation, verdict_asked_for=newest, verdict_asks=asks,
                   verdict_asked_at=at)


def unread_of(conversation: Conversation) -> bool:
    return (conversation.role == ROLE_REVIEWER and conversation.state == OPEN
            and conversation.verdict_for != newest_said(conversation))
