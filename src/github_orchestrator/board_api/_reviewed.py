import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from github_orchestrator.board_api._contract import PullRequestCommit, ReviewedCommits
from github_orchestrator.board_api.interface import Shelf, Shelves
from github_orchestrator.domain import Pr, Sha
from github_orchestrator.working_copies import WorkingCopies

log = logging.getLogger(__name__)

REVIEWED = "reviewed"
AT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class Commit(Protocol):
    @property
    def sha(self) -> Sha: ...

    @property
    def parents(self) -> Sequence[Sha]: ...

    @property
    def subject(self) -> str: ...

    @property
    def author(self) -> str: ...

    @property
    def authored_at(self) -> datetime: ...


def commit_of(commit: Commit) -> PullRequestCommit:
    return PullRequestCommit(
        sha=str(commit.sha), parents=[str(parent) for parent in commit.parents],
        subject=commit.subject, author=commit.author,
        authored_at=commit.authored_at.astimezone(UTC).strftime(AT_FORMAT))


def kept(shelf: Shelf, sha: str) -> ReviewedCommits | None:
    document = shelf.list(REVIEWED).get(sha)
    return None if document is None else ReviewedCommits.model_validate_json(document)


class ShelvedReviews:
    def __init__(self, working_copies: WorkingCopies, shelves: Shelves) -> None:
        self._working_copies = working_copies
        self._shelves = shelves

    def keep(self, pr: Pr, sha: str, base_branch: str | None) -> None:
        shelf = self._shelves.of(pr)
        head = Sha.parse(sha)
        if head is None or sha in shelf.list(REVIEWED):
            return
        history = self._working_copies.checkout(pr).pr_commits(base_branch, head)
        if history is None:
            log.warning("Could not list the commits %s's review of %s saw", pr, sha)
            return
        saw = ReviewedCommits(sha=sha, fork=str(history.fork),
                              commits=[commit_of(commit) for commit in history.commits])
        shelf.save(REVIEWED, sha, saw.model_dump_json().encode())
