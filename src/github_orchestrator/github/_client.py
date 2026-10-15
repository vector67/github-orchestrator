import logging
import subprocess
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Any

from github_orchestrator.domain import Location, Pr, Repo
from github_orchestrator.github import _fetch_ahead, _pages, _pull_requests, _threads
from github_orchestrator.github._gh_cli import Gh, Run
from github_orchestrator.github.interface import (
    CommentKind,
    GhError,
    Listed,
    PostedComment,
    PullRequestState,
    Relevance,
    SentReview,
    Thread,
    ThreadComment,
    Verdict,
    Whose,
)

log = logging.getLogger(__name__)

_SEARCHES: dict[Whose, str] = {
    "author": "--author=@me",
    "review-requested": "--review-requested=@me",
    "mentions": "--mentions=@me",
}

_LISTED = "user/repos?per_page=100&sort=pushed&affiliation=owner,collaborator,organization_member"


class GhCliGitHub:
    def __init__(self, account: str, run: Run) -> None:
        self._account = account
        self._run = run
        self._gh = Gh(account, run)
        self._states_ahead: dict[Pr, PullRequestState] = {}
        self._threads_ahead: dict[Pr, list[Thread]] = {}

    def prefetch(self, prs: Sequence[Pr]) -> None:
        try:
            self._states_ahead, self._threads_ahead = _fetch_ahead.fetch_ahead(
                self._gh, self._account, list(prs))
        except (GhError, subprocess.TimeoutExpired, ValueError) as refused:
            log.warning("could not fetch %d PRs ahead, so each is read on its own: %s",
                        len(prs), refused)
            self._states_ahead, self._threads_ahead = {}, {}

    def check_login(self, account: str) -> str | None:
        try:
            self._gh.check_login(account)
        except GhError as refused:
            return str(refused)
        return None

    def active_account(self) -> str | None:
        return self._gh.active_account()

    def scopes(self, account: str) -> tuple[str, ...]:
        try:
            return Gh(account, self._run).scopes()
        except (GhError, subprocess.TimeoutExpired):
            return ()

    def repos_of(self, account: str) -> list[Listed] | str:
        gh = Gh(account, self._run)
        try:
            found = gh.api(_LISTED, paginate=True)
            mine = self._mine(gh, ())
        except (GhError, subprocess.TimeoutExpired) as refused:
            return str(refused)
        return [_listed(one, mine) for one in found]

    def repo_of(self, account: str, repo: Repo) -> Listed | str:
        gh = Gh(account, self._run)
        try:
            found = gh.api(f"repos/{repo}")
            mine = self._mine(gh, (repo,))
        except (GhError, subprocess.TimeoutExpired) as refused:
            return f"{account} cannot see {repo}: {refused}"
        return _listed(found, mine)

    def _mine(self, gh: Gh, repos: Collection[Repo]) -> set[Repo]:
        return {pr.repo for whose in ("author", "review-requested")
                for pr in gh.search_prs(_SEARCHES[whose], repos)}

    def check_access(self, account: str, repo: Repo) -> str | None:
        try:
            self._gh.check_access(account, repo)
        except GhError as refused:
            return str(refused)
        return None

    def clone(self, repo: Repo, into: Path) -> str | None:
        try:
            self._gh.clone(repo, into)
        except GhError as refused:
            return str(refused)
        return None

    def search(self, repos: Collection[Repo], whose: Whose) -> list[Pr]:
        return self._gh.search_prs(_SEARCHES[whose], repos)

    def pr_state(self, pr: Pr) -> PullRequestState:
        ahead = self._states_ahead.pop(pr, None)
        if ahead is not None:
            return ahead
        return _pull_requests.pr_state(self._gh, self._account, pr)

    def head_branch(self, pr: Pr) -> str | None:
        return _pull_requests.head_branch(self._gh, pr)

    def is_closed(self, pr: Pr) -> bool | None:
        return _pull_requests.is_closed(self._gh, pr)

    def close(self, pr: Pr) -> str | None:
        try:
            self._gh.api_json(f"repos/{pr.repo}/pulls/{pr.number}", {"state": "closed"},
                              method="PATCH")
        except GhError as refused:
            return str(refused)
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
        return _pull_requests.relevance(self._gh, pr)

    def threads(self, pr: Pr) -> list[Thread]:
        ahead = self._threads_ahead.pop(pr, None)
        if ahead is not None:
            return ahead
        return _threads.threads(self._gh, pr)

    def reply_to_thread(self, key: str, body: str) -> ThreadComment | None:
        return _threads.reply_to_thread(self._gh, key, body)

    def comment_on_pr(self, pr: Pr, body: str) -> PostedComment:
        return _threads.comment_on_pr(self._gh, pr, body)

    def resolve_thread(self, key: str) -> None:
        _threads.resolve_thread(self._gh, key)

    def unresolve_thread(self, key: str) -> None:
        _threads.unresolve_thread(self._gh, key)

    def react(self, repo: Repo, comment_id: int) -> None:
        _threads.react(self._gh, repo, comment_id)

    def post_review_comment(self, pr: Pr, head: str, location: Location,
                            body: str) -> ThreadComment:
        return _threads.post_review_comment(self._gh, pr, head, location, body)

    def post_review(self, pr: Pr, head: str, verdict: Verdict,
                    body: str | None,
                    comments: Sequence[tuple[Location, str]]) -> SentReview:
        return _threads.post_review(self._gh, pr, head, verdict, body, comments)

    def delete_comment(self, pr: Pr, kind: CommentKind,
                       comment_id: int) -> None:
        _threads.delete_comment(self._gh, pr, kind, comment_id)

    def comment_exists(self, pr: Pr, kind: CommentKind,
                       comment_id: int) -> bool | None:
        return _threads.comment_exists(self._gh, pr, kind, comment_id)


def _listed(found: dict[str, Any], mine: set[Repo]) -> Listed:
    repo = Repo.parse(found["full_name"])
    return Listed(repo, bool((found.get("permissions") or {}).get("push")), repo in mine,
                  found.get("default_branch") or "")
