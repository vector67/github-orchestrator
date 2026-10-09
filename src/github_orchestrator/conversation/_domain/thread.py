from dataclasses import dataclass

from github_orchestrator.conversation._domain.conversation import (
    Anchor,
    Comment,
    ReviewState,
)


@dataclass(frozen=True)
class FetchedThread:
    key: str
    kind: str
    comments: tuple[Comment, ...] = ()
    anchor: Anchor | None = None
    path: str | None = None
    line: int | None = None
    is_resolved: bool | None = None
    resolved_by: str | None = None
    state: ReviewState | None = None


@dataclass(frozen=True)
class ActiveThread:
    thread: FetchedThread
    new_comments: tuple[Comment, ...]
