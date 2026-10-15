import itertools
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from github_orchestrator.domain import Location, Pr, Repo
from github_orchestrator.github import _pages
from github_orchestrator.github.interface import (
    Check as Check,
)
from github_orchestrator.github.interface import (
    CommentKind,
    Listed,
    PostedComment,
    PullRequestState,
    Relevance,
    Review,
    ReviewComment,
    ReviewState,
    SentReview,
    Thread,
    ThreadComment,
    Verdict,
)
from github_orchestrator.github.interface import (
    GhError as GhError,
)
from github_orchestrator.github.interface import (
    PushEvent as PushEvent,
)
from github_orchestrator.github.interface import (
    ThreadAnchor as ThreadAnchor,
)
from github_orchestrator.github.interface import (
    Whose as Whose,
)

FAKE_NOW = "2026-01-01T00:00:00Z"

SEARCH_REFUSED = ("Invalid search query. The listed users and repositories cannot be "
                  "searched either because the resources do not exist or you do "
                  "not have permission to view them.")

_REVIEW_STATES = {
    Verdict.APPROVE: ReviewState.APPROVED,
    Verdict.REQUEST_CHANGES: ReviewState.CHANGES_REQUESTED,
    Verdict.COMMENT: ReviewState.COMMENTED,
}

_KINDS = (CommentKind.REVIEW, CommentKind.ISSUE, CommentKind.REVIEW_SUMMARY)


@dataclass
class FakePullRequest:
    pr: Pr
    state: PullRequestState
    status: str = "OPEN"
    created_at: str | None = None
    review_requested: bool = False
    viewer_reviewed: bool = False
    mentioned: bool = False
    threads: list[Thread] = field(default_factory=list)
    review_comments: dict[int, list[ReviewComment]] = field(default_factory=dict)
    pending_review: int | None = None


def _as_github_answers(thread: Thread) -> Thread:
    comments = []
    for comment in thread.comments:
        comment = replace(
            comment,
            author=comment.author or "ghost",
            updated_at=comment.updated_at or comment.created_at,
        )
        if thread.kind is CommentKind.ISSUE:
            comment = replace(comment, review_state=None)
        if thread.kind is CommentKind.REVIEW_SUMMARY:
            comment = replace(comment, review_state=thread.state,
                              updated_at=comment.created_at)
        comments.append(comment)
    return replace(thread, comments=tuple(comments),
                   anchor=thread.anchor or ThreadAnchor())


class FakeGitHub:
    def __init__(self, account: str = "octocat") -> None:
        self.account = account
        self.tokens = {account: f"gho_{account}"}
        self.repos: set[Repo] = set()
        self.listed: list[Repo] = []
        self.read_only: set[Repo] = set()
        self.granted: dict[str, tuple[str, ...]] = {account: ("repo",)}
        self.cloned: list[tuple[Repo, Path]] = []
        self.prs: dict[Pr, FakePullRequest] = {}
        self.reactions: dict[int, list[str]] = {}
        self._ids = itertools.count(9001)

    def add_pr(self, pr: Pr,
               state: PullRequestState = PullRequestState(), *,
               status: str = "OPEN", created_at: str | None = None,
               review_requested: bool = False,
               viewer_reviewed: bool = False,
               mentioned: bool = False) -> FakePullRequest:
        self.repos.add(pr.repo)
        record = FakePullRequest(pr, state, status, created_at,
                                 review_requested, viewer_reviewed, mentioned)
        self.prs[pr] = record
        return record

    def add_thread(self, pr: Pr, thread: Thread) -> None:
        self._pr(pr).threads.append(_as_github_answers(thread))

    def clone(self, repo: Repo, into: Path) -> str | None:
        if repo not in self.repos:
            return (f"gh repo clone {repo} failed (exit 1): GraphQL: Could not resolve "
                    f"to a Repository with the name '{repo}'.")
        into.mkdir(parents=True)
        self.cloned.append((repo, into))
        return None

    def check_login(self, account: str) -> str | None:
        if account not in self.tokens:
            return (
                f"gh auth token --user {account} failed (exit 1): no oauth "
                f"token found for github.com account {account} — run `gh auth "
                f"login` as {account}, or set gh_account in config.toml to an "
                f"account `gh auth status` lists"
            )
        return None

    def active_account(self) -> str | None:
        return self.account

    def scopes(self, account: str) -> tuple[str, ...]:
        return self.granted.get(account, ())

    def repos_of(self, account: str) -> list[Listed] | str:
        refused = self.check_login(account)
        if refused is not None:
            return refused
        return [self._listed(repo) for repo in self.listed]

    def repo_of(self, account: str, repo: Repo) -> Listed | str:
        refused = self.check_access(account, repo)
        if refused is not None:
            return refused
        return self._listed(repo)

    def _listed(self, repo: Repo) -> Listed:
        mine = any(record.pr.repo == repo and record.status == "OPEN"
                   and (record.state.author == self.account or record.review_requested)
                   for record in self.prs.values())
        return Listed(repo, repo not in self.read_only, mine, "main")

    def check_access(self, account: str, repo: Repo) -> str | None:
        refused = self.check_login(account)
        if refused is not None:
            return refused
        if repo not in self.repos:
            return (f"gh cannot see {repo} as {account} (exit 1): "
                    f"GraphQL: Could not resolve to a Repository")
        return None

    def search(self, repos: Collection[Repo], whose: Whose) -> list[Pr]:
        return [record.pr for record in self._open_in(repos) if self._found(record, whose)]

    def _found(self, record: FakePullRequest, whose: Whose) -> bool:
        if whose == "author":
            return record.state.author == self.account
        if whose == "mentions":
            return record.mentioned
        return record.review_requested

    def _open_in(self, repos: Collection[Repo]) -> list[FakePullRequest]:
        seen = {repo for repo in repos if repo in self.repos}
        if not seen:
            raise GhError(f"gh search prs failed (exit 1): {SEARCH_REFUSED}")
        return [record for record in self.prs.values()
                if record.status == "OPEN" and record.pr.repo in seen]

    def prefetch(self, prs: Sequence[Pr]) -> None:
        return None

    def pr_state(self, pr: Pr) -> PullRequestState:
        record = self._pr(pr)
        state = record.state
        mine = state.author == self.account
        return replace(
            state,
            ready_for_review_at=(None if state.draft
                                 else state.ready_for_review_at or record.created_at),
            push_events=() if mine else state.push_events,
        )

    def head_branch(self, pr: Pr) -> str | None:
        record = self.prs.get(pr)
        return None if record is None else record.state.branch or None

    def is_closed(self, pr: Pr) -> bool | None:
        record = self.prs.get(pr)
        if record is None:
            return None
        return record.status != "OPEN"

    def close(self, pr: Pr) -> str | None:
        record = self.prs.get(pr)
        if record is None:
            return (f"gh api PATCH repos/{pr.repo}/pulls/{pr.number} failed (exit 1): "
                    "gh: Not Found (HTTP 404)")
        record.status = "CLOSED"
        return None

    def url(self, pr: Pr) -> str:
        return _pages.pr_url(pr)

    def commit_url(self, repo: Repo, sha: str) -> str:
        return _pages.commit_url(repo, sha)

    def comment_url(self, pr: Pr, kind: CommentKind, comment_id: int) -> str:
        return _pages.comment_url(pr, kind, comment_id)

    def too_long(self, body: str) -> str | None:
        return _pages.too_long(body)

    def relevance(self, pr: Pr) -> Relevance | None:
        record = self.prs.get(pr)
        if record is None:
            return None
        return Relevance(state=record.status,
                         viewer_did_author=record.state.author == self.account,
                         viewer_reviewed=record.viewer_reviewed)

    def threads(self, pr: Pr) -> list[Thread]:
        return sorted(
            (thread for thread in self._pr(pr).threads
             if thread.kind is not CommentKind.REVIEW_SUMMARY
             or any(comment.body.strip() for comment in thread.comments)),
            key=lambda thread: _KINDS.index(thread.kind),
        )

    def thread(self, key: str) -> Thread | None:
        found = self._find(key)
        return None if found is None else found[1]

    def reply_to_thread(self, key: str, body: str) -> ThreadComment | None:
        record, thread = self._review_thread(key)
        comment = self._new_comment(body)
        self._put(record, replace(thread, comments=(*thread.comments, comment)))
        return comment

    def comment_on_pr(self, pr: Pr, body: str) -> PostedComment:
        record = self._pr(pr)
        comment = self._new_comment(body)
        key = f"IC_{comment.id}"
        record.threads.append(Thread(key=key, kind=CommentKind.ISSUE, comments=(comment,),
                                     anchor=ThreadAnchor()))
        return PostedComment(comment, key)

    def resolve_thread(self, key: str) -> None:
        record, thread = self._review_thread(key)
        self._put(record, replace(thread, is_resolved=True, resolved_by=self.account))

    def unresolve_thread(self, key: str) -> None:
        record, thread = self._review_thread(key)
        self._put(record, replace(thread, is_resolved=False, resolved_by=None))

    def react(self, repo: Repo, comment_id: int) -> None:
        if not self._holds(repo, None, CommentKind.REVIEW, comment_id):
            raise GhError(f"gh api POST repos/{repo}/pulls/comments/{comment_id}/"
                          f"reactions failed (exit 1): gh: Not Found (HTTP 404)")
        self.reactions.setdefault(comment_id, []).append("+1")

    def post_review_comment(self, pr: Pr, head: str,
                            location: Location, body: str) -> ThreadComment:
        record = self._pr(pr)
        comment = self._new_comment(body)
        record.threads.append(self._draft_thread(location, comment))
        return comment

    def post_review(self, pr: Pr, head: str, verdict: Verdict,
                    body: str | None,
                    comments: Sequence[tuple[Location, str]]) -> SentReview:
        record = self._pr(pr)
        review_id = record.pending_review or self.start_pending_review(pr, [])
        for where, text in comments:
            self.add_to_pending_review(review_id, where, text)
        return self.submit_review(pr, review_id, head, verdict, body)

    def start_pending_review(self, pr: Pr,
                             comments: Sequence[tuple[Location, str]]) -> int:
        record = self._pr(pr)
        review_id = next(self._ids)
        record.pending_review = review_id
        record.review_comments[review_id] = []
        for where, text in comments:
            self.add_to_pending_review(review_id, where, text)
        return review_id

    def add_to_pending_review(self, review_id: int, where: Location,
                              body: str) -> ThreadComment:
        record = next((one for one in self.prs.values()
                       if one.pending_review == review_id), None)
        if record is None:
            raise GhError(f"gh graphql mutation failed: Could not resolve to a "
                          f"node with the global id of 'PRR_{review_id}'")
        comment = replace(self._new_comment(body), review_state=ReviewState.PENDING)
        record.threads.append(self._draft_thread(where, comment))
        record.review_comments[review_id].append(ReviewComment(path=where.path,
                                                               comment=comment))
        return comment

    def submit_review(self, pr: Pr, review_id: int, head: str, verdict: Verdict,
                      body: str | None) -> SentReview:
        record = self._pr(pr)
        state = _REVIEW_STATES[verdict]
        record.pending_review = None
        record.state = replace(record.state, reviews=(
            *record.state.reviews,
            Review(author=self.account, state=state, submitted_at=FAKE_NOW,
                   commit_id=head),
        ))
        if body:
            record.threads.append(_as_github_answers(Thread(
                key=f"PRR_{review_id}", kind=CommentKind.REVIEW_SUMMARY,
                comments=(ThreadComment(id=review_id, author=self.account,
                                        body=body, created_at=FAKE_NOW),),
                state=state,
            )))
        listed = [replace(one, comment=replace(one.comment, review_state=state))
                  for one in record.review_comments[review_id]]
        record.review_comments[review_id] = listed
        submitted = {one.comment.id: one.comment for one in listed}
        record.threads = [
            replace(thread, comments=tuple(submitted.get(c.id, c) for c in thread.comments))
            for thread in record.threads]
        return SentReview(review_id, tuple(listed))

    def review_comments(self, pr: Pr,
                        review_id: int) -> list[ReviewComment]:
        return list(self._pr(pr).review_comments.get(review_id, []))

    def delete_comment(self, pr: Pr, kind: CommentKind,
                       comment_id: int) -> None:
        for record in self._records(pr.repo, pr, kind):
            kept = []
            for thread in record.threads:
                if thread.kind == kind:
                    thread = replace(thread, comments=tuple(
                        c for c in thread.comments if c.id != comment_id))
                if thread.comments:
                    kept.append(thread)
            record.threads = kept

    def comment_exists(self, pr: Pr, kind: CommentKind,
                       comment_id: int) -> bool | None:
        return self._holds(pr.repo, pr, kind, comment_id)

    def _pr(self, pr: Pr) -> FakePullRequest:
        record = self.prs.get(pr)
        if record is None:
            raise GhError(f"gh api /repos/{pr.repo}/pulls/{pr.number} failed (exit 1): "
                          f"gh: Not Found (HTTP 404)")
        return record

    def _records(self, repo: Repo, pr: Pr | None,
                 kind: CommentKind) -> list[FakePullRequest]:
        return [record for record in self.prs.values()
                if record.pr.repo == repo
                and (kind is not CommentKind.REVIEW_SUMMARY or record.pr == pr)]

    def _holds(self, repo: Repo, pr: Pr | None, kind: CommentKind, comment_id: int) -> bool:
        return any(
            comment.id == comment_id
            for record in self._records(repo, pr, kind)
            for thread in record.threads if thread.kind == kind
            for comment in thread.comments
        )

    def _find(self, key: str) -> tuple[FakePullRequest, Thread] | None:
        for record in self.prs.values():
            for thread in record.threads:
                if thread.key == key:
                    return record, thread
        return None

    def _review_thread(self, key: str) -> tuple[FakePullRequest, Thread]:
        found = self._find(key)
        if found is None or found[1].kind is not CommentKind.REVIEW:
            raise GhError(f"gh graphql mutation failed: Could not resolve to a "
                          f"node with the global id of '{key}'")
        return found

    def _put(self, record: FakePullRequest, thread: Thread) -> None:
        record.threads = [thread if one.key == thread.key else one
                          for one in record.threads]

    def _new_comment(self, body: str) -> ThreadComment:
        return ThreadComment(id=next(self._ids), author=self.account, body=body,
                             created_at=FAKE_NOW, updated_at=FAKE_NOW)

    def _draft_thread(self, where: Location, comment: ThreadComment) -> Thread:
        return Thread(
            key=f"PRRT_{comment.id}", kind=CommentKind.REVIEW, comments=(comment,),
            anchor=ThreadAnchor(
                side=where.side,
                start_line=where.line if where.start_line is None else where.start_line,
                start_side=where.side if where.start_side is None else where.start_side,
                original_line=where.line,
                original_start_line=where.start_line,
            ),
            path=where.path, line=where.line, is_resolved=False,
        )
