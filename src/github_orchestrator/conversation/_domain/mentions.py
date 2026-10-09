import re
from collections.abc import Sequence

from github_orchestrator.conversation._domain.conversation import Comment
from github_orchestrator.conversation._domain.diff import KIND_ISSUE, KIND_REVIEW
from github_orchestrator.conversation._domain.thread import FetchedThread
from github_orchestrator.domain import Mention

KIND_PR_BODY = "pr-body"
PR_BODY_KEY = "pr-body"
_DETAILED_REVIEWER = re.compile(r"^\s*detailed reviewer:.*$", re.IGNORECASE | re.MULTILINE)


def _names(account: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w@./-])@{re.escape(account)}(?![\w-])", re.IGNORECASE)


def _names_me(names: re.Pattern[str], body: str) -> bool:
    return names.search(_DETAILED_REVIEWER.sub("", body)) is not None


def _mine(comment: Comment, account: str) -> bool:
    return comment.author.lower() == account.lower()


def names_the_viewer(comment: Comment, account: str) -> bool:
    return not _mine(comment, account) and _names_me(_names(account), comment.body)


def _someone_else(pr_author: str | None, account: str) -> str | None:
    return pr_author if pr_author and pr_author.lower() != account.lower() else None


def _later_on_the_pr(threads: Sequence[FetchedThread], account: str,
                     at: str | None) -> bool:
    return any(_mine(comment, account) and (at is None or (comment.created_at or "") > at)
               for thread in threads if thread.kind == KIND_ISSUE
               for comment in thread.comments)


def _in_thread(threads: Sequence[FetchedThread], account: str,
               names: re.Pattern[str]) -> list[Mention]:
    found = []
    for thread in threads:
        for index, comment in enumerate(thread.comments):
            if _mine(comment, account) or not _names_me(names, comment.body):
                continue
            answered = (any(_mine(later, account) for later in thread.comments[index + 1:])
                        if thread.kind == KIND_REVIEW
                        else _later_on_the_pr(threads, account, comment.created_at))
            found.append(Mention(author=comment.author, at=comment.created_at,
                                 kind=thread.kind, thread=thread.key, comment_id=comment.id,
                                 body=comment.body, answered=answered))
    return found


def mentions(threads: Sequence[FetchedThread], *, account: str, pr_body: str,
             pr_author: str | None) -> tuple[Mention, ...]:
    names = _names(account)
    opening = []
    author = _someone_else(pr_author, account)
    if author and _names_me(names, pr_body):
        opening.append(Mention(author=author, at=None, kind=KIND_PR_BODY, thread=PR_BODY_KEY,
                               comment_id=None, body=pr_body,
                               answered=_later_on_the_pr(threads, account, None)))
    return tuple(opening + _in_thread(threads, account, names))


def unanswered_threads(found: Sequence[Mention]) -> frozenset[str]:
    return frozenset(mention.thread for mention in found
                     if not mention.answered and mention.thread is not None)


def mentioning_threads(threads: Sequence[FetchedThread], found: Sequence[Mention], *,
                       account: str, pr_body: str, pr_author: str | None) -> list[FetchedThread]:
    author = _someone_else(pr_author, account)
    if author is None:
        return []
    keys = unanswered_threads(found)
    opening = [FetchedThread(key=PR_BODY_KEY, kind=KIND_PR_BODY,
                             comments=(Comment(author=author, body=pr_body),))
               ] if PR_BODY_KEY in keys else []
    return opening + [thread for thread in threads if thread.key in keys]
