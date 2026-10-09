from collections.abc import Sequence

from github_orchestrator.conversation._application.ports import (
    PostedDraft,
    PostedReply,
    PostedReview,
)
from github_orchestrator.conversation._domain.conversation import (
    Anchor,
    Comment,
    Conversation,
    ReviewState,
)
from github_orchestrator.conversation._domain.diff import (
    BOT_MARKER,
    KIND_ISSUE,
    KIND_REVIEW,
    KIND_REVIEW_SUMMARY,
)
from github_orchestrator.conversation._domain.mentions import KIND_PR_BODY
from github_orchestrator.conversation._domain.review import Verdict
from github_orchestrator.conversation._domain.thread import FetchedThread
from github_orchestrator.domain import Location, Pr, Repo, Sha
from github_orchestrator.github import (
    CommentKind,
    PullRequests,
    Reviews,
    Thread,
    ThreadComment,
    Threads,
)
from github_orchestrator.github import (
    ReviewState as GitHubReviewState,
)
from github_orchestrator.github import (
    Verdict as GitHubVerdict,
)

_KIND_WORDS = {
    CommentKind.REVIEW: KIND_REVIEW,
    CommentKind.ISSUE: KIND_ISSUE,
    CommentKind.REVIEW_SUMMARY: KIND_REVIEW_SUMMARY,
}

_KINDS = {word: kind for kind, word in _KIND_WORDS.items()}

_STATES = {
    GitHubReviewState.APPROVED: ReviewState.APPROVED,
    GitHubReviewState.CHANGES_REQUESTED: ReviewState.CHANGES_REQUESTED,
    GitHubReviewState.COMMENTED: ReviewState.COMMENTED,
    GitHubReviewState.DISMISSED: ReviewState.DISMISSED,
    GitHubReviewState.PENDING: ReviewState.PENDING,
}

_VERDICTS = {
    Verdict.APPROVE: GitHubVerdict.APPROVE,
    Verdict.REQUEST_CHANGES: GitHubVerdict.REQUEST_CHANGES,
    Verdict.COMMENT: GitHubVerdict.COMMENT,
}


def _state_word(state: GitHubReviewState | None) -> ReviewState | None:
    return None if state is None else _STATES[state]


def _domain_comment(comment: ThreadComment) -> Comment:
    return Comment(id=comment.id, author=comment.author, body=comment.body,
                   created_at=comment.created_at, updated_at=comment.updated_at,
                   author_name=comment.author_name,
                   review_state=_state_word(comment.review_state))


def _anchor_of(thread: Thread) -> Anchor | None:
    anchor = thread.anchor
    if anchor is None:
        return None
    return Anchor(is_outdated=anchor.is_outdated, side=anchor.side,
                  start_line=anchor.start_line, start_side=anchor.start_side,
                  original_line=anchor.original_line,
                  original_start_line=anchor.original_start_line,
                  original_commit=anchor.original_commit)


def fetched_thread(thread: Thread) -> FetchedThread:
    return FetchedThread(
        key=thread.key,
        kind=_KIND_WORDS[thread.kind],
        comments=tuple(_domain_comment(c) for c in thread.comments),
        anchor=_anchor_of(thread),
        path=thread.path,
        line=thread.line,
        is_resolved=thread.is_resolved,
        resolved_by=thread.resolved_by,
        state=_state_word(thread.state),
    )


def fetch_threads(github: Threads, pr: Pr) -> list[FetchedThread]:
    return [fetched_thread(thread) for thread in github.threads(pr)]


def reply_body(prs: PullRequests, repo: Repo, body: str, commit: str | None) -> str:
    if not commit:
        return body
    link = f"[{commit[:7]}]({prs.commit_url(repo, commit)})"
    return f"{body}\n\n{link}" if body else f"{BOT_MARKER} {link}"


def quoted_pr_reply(author: str, comment: str, reply: str) -> str:
    """A reply to a comment with no thread: its author tagged, it quoted, the reply."""
    mention = f"@{author}" if author else ""
    quoted = "\n".join(f"> {line}".rstrip() for line in comment.splitlines())
    return "\n\n".join(part for part in (mention, quoted, reply) if part)


def _posted_comment(comment: ThreadComment) -> Comment:
    return Comment(id=comment.id, author=comment.author, body=comment.body,
                   created_at=comment.created_at, updated_at=comment.updated_at)


def _thread_id(conversation: Conversation) -> str:
    """GitHub's name for the thread. A record the poller opened is keyed by
    it; a posted draft keeps the board's key and carries GitHub's beside it."""
    return conversation.github_node_id or conversation.key


def _draft_of(conversation: Conversation) -> tuple[Location, str]:
    location = conversation.location
    if location is None:
        raise ValueError(f"draft {conversation.key} hangs off no line")
    return location, conversation.body


class GitHubThreads:
    def __init__(self, prs: PullRequests, github: Threads, reviews: Reviews,
                 pr: Pr) -> None:
        self._prs = prs
        self._github = github
        self._reviews = reviews
        self._pr = pr

    def post_reply(self, conversation: Conversation, body: str,
                   commit: Sha | None) -> PostedReply:
        reply = reply_body(self._prs, self._pr.repo, body,
                           None if commit is None else str(commit))
        if conversation.comment_type == KIND_REVIEW:
            posted = self._github.reply_to_thread(_thread_id(conversation), reply)
            return PostedReply(None if posted is None else _posted_comment(posted), None)
        quoted = "" if conversation.comment_type == KIND_PR_BODY else conversation.body
        on_pr = self._github.comment_on_pr(
            self._pr, quoted_pr_reply(conversation.author, quoted, reply))
        return PostedReply(_posted_comment(on_pr.comment), on_pr.key)

    def resolve_thread(self, conversation: Conversation) -> None:
        self._github.resolve_thread(_thread_id(conversation))

    def unresolve_thread(self, conversation: Conversation) -> None:
        self._github.unresolve_thread(_thread_id(conversation))

    def react(self, conversation: Conversation, comment_id: int) -> None:
        self._github.react(self._pr.repo, comment_id)

    def post_review_comment(self, conversation: Conversation,
                            head: str) -> PostedDraft:
        created = self._reviews.post_review_comment(self._pr, head,
                                                    *_draft_of(conversation))
        comment = _posted_comment(created)
        key = (self.thread_key_of_comment(comment.id)
               if comment.id is not None else None)
        return PostedDraft(comment, key)

    def post_review(self, verdict: Verdict, body: str | None,
                    drafts: Sequence[Conversation],
                    head: str) -> PostedReview:
        """The review, and each draft's comment and thread in it.

        The review's answer names neither, so its comments are listed and
        matched to the drafts by path and body in the order they were sent,
        and each comment's thread is looked for once. A thread GitHub does
        not list yet is left null; the poller finds it by the comment later.
        """
        sent = self._reviews.post_review(self._pr, head, _VERDICTS[verdict],
                                         body, [_draft_of(d) for d in drafts])
        if not drafts or sent.id is None:
            return PostedReview(sent.id, ())
        unclaimed = list(sent.comments)
        roots = {thread.comments[0].id: thread.key
                 for thread in self._github.threads(self._pr)
                 if thread.comments}
        posted = []
        for draft in drafts:
            match = next((one for one in unclaimed
                          if one.path == draft.path
                          and one.comment.body == draft.body), None)
            if match is None:
                posted.append(PostedDraft(Comment(author=draft.author,
                                                  body=draft.body)))
                continue
            unclaimed.remove(match)
            comment = _posted_comment(match.comment)
            posted.append(PostedDraft(comment, roots.get(comment.id)))
        return PostedReview(sent.id, tuple(posted))

    def thread_key_of_comment(self, comment_id: int) -> str | None:
        """The thread a REST comment opened, by the databaseId both sides share."""
        for thread in self._github.threads(self._pr):
            if thread.comments and thread.comments[0].id == comment_id:
                return thread.key
        return None

    def delete_comment(self, conversation: Conversation) -> None:
        kind = _KINDS.get(conversation.comment_type)
        if kind is None:
            raise ValueError(f"a {conversation.comment_type!r} comment cannot be deleted")
        self._github.delete_comment(self._pr, kind, conversation.comment_id or 0)

    def comment_exists(self, conversation: Conversation) -> bool | None:
        kind = _KINDS.get(conversation.comment_type)
        if kind is None:
            return None
        return self._github.comment_exists(self._pr, kind,
                                           conversation.comment_id or 0)

    def takes_review(self, verdict: Verdict, body: str | None) -> bool:
        return _VERDICTS[verdict].takes(body)

    def page(self) -> str:
        return self._prs.url(self._pr)

    def comment_page(self, conversation: Conversation, comment_id: int) -> str:
        kind = _KINDS.get(conversation.comment_type or KIND_REVIEW)
        if kind is None:
            return self.page()
        return self._github.comment_url(self._pr, kind, comment_id)

    def too_long(self, text: str) -> str | None:
        return self._github.too_long(text)
