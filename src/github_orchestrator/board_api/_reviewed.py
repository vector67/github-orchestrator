from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from github_orchestrator.board_api._contract import PullRequestCommit, ReviewedCommits
from github_orchestrator.board_api.interface import REVIEWED, Shelf, ShelfKey
from github_orchestrator.domain import Sha, UtcClock


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
        authored_at=commit.authored_at.astimezone(UTC).strftime(UtcClock.STAMP))


def kept(shelf: Shelf, sha: str) -> ReviewedCommits | None:
    key = ShelfKey.parse(sha)
    document = None if key is None else shelf.list(REVIEWED).get(key)
    return None if document is None else ReviewedCommits.model_validate_json(document)
