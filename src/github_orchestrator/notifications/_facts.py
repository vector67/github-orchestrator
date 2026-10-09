from dataclasses import dataclass
from enum import Enum

from github_orchestrator.desktop import Badge
from github_orchestrator.domain import Pr


@dataclass(frozen=True)
class Posted:
    pr: Pr | None
    badge: Badge
    title: str
    body: str


@dataclass(frozen=True)
class FixReady:
    pr: Pr
    key: str
    gist: str
    comments: tuple[tuple[str, str], ...]
    fix_summary: str


@dataclass(frozen=True)
class AgentSkipped:
    pr: Pr
    event_type: str


class Arrival(Enum):
    NEW_THREAD = "New thread"
    REPLY = "Reply"
    REOPENED = "Reopened"


@dataclass(frozen=True)
class CommentArrived:
    pr: Pr
    key: str
    comment_id: int | None
    author: str
    body: str
    created_at: str
    arrival: Arrival
    review_comment: bool


Gathered = FixReady | AgentSkipped | CommentArrived
