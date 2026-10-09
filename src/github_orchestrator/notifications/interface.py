from collections.abc import Sequence
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol

from github_orchestrator.change_detection import (
    BecameMergeable,
    BecameUnmergeable,
    CiFailed,
    CiSucceeded,
    PrClosed,
    PushedSinceReview,
    ReviewDecisionChanged,
)
from github_orchestrator.domain import Pr


class FixProgress(Enum):
    NONE = "none"
    QUEUED = "queued"
    STARTED = "started"


class Standing(Protocol):
    def fix_still_news(self, pr: Pr, key: str) -> bool: ...

    def comment_still_news(self, pr: Pr, key: str, since: str) -> bool: ...

    def fix_progress(self, pr: Pr, key: str) -> FixProgress: ...


class Settling(Protocol):
    def settling(self, pr: Pr) -> bool: ...


class BoardPages(Protocol):
    def board_of(self, pr: Pr) -> str: ...


class ThreadNews(Protocol):
    def fix_ready(self, pr: Pr, key: str, *, gist: str,
                  comments: Sequence[tuple[str, str]], fix_summary: str | None) -> None: ...

    def comment_arrived(self, pr: Pr, key: str, *, comment_id: int | None, author: str,
                        body: str, created_at: str, opens_thread: bool, reopens: bool,
                        review_comment: bool) -> None: ...

    def needs_your_call(self, pr: Pr, *, author: str, classification: str | None,
                        reason: str | None) -> None: ...

    def fix_failed(self, pr: Pr, *, gist: str, author: str, reason: str | None) -> None: ...


class Runs(Protocol):
    def run_failed(self, pr: Pr, kind: str, exit_code: int | None) -> None: ...

    def agent_skipped(self, pr: Pr, kind: str) -> None: ...


class Worktrees(Protocol):
    def blocked(self, pr: Pr) -> None: ...

    def fetch_failed(self, pr: Pr, branch: str) -> None: ...

    def init_timed_out(self, worktree: Path, seconds: int) -> None: ...

    def init_failed(self, worktree: Path, exit_code: int) -> None: ...

    def wrong_branch(self, pr: Pr, kept_as: str) -> None: ...

    def shared(self, pr: Pr, worktree: Path, other: Pr) -> None: ...

    def still_shared(self, pr: Pr, worktree: Path, other: Pr, minutes: int) -> None: ...


StatusChange = (CiSucceeded | CiFailed | BecameUnmergeable | BecameMergeable
                | ReviewDecisionChanged | PushedSinceReview | PrClosed)


class PrStatus(Protocol):
    def changed(self, pr: Pr, change: StatusChange) -> None: ...


class Polling(Protocol):
    def failed(self, consecutive: int | None, error: str, log_file: Path) -> None: ...


class Courier(Protocol):
    def deliver(self, woke_at: datetime, polled_at: datetime | None) -> None: ...
