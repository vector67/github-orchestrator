from dataclasses import dataclass

from github_orchestrator.conversation._domain.conversation import (
    Anchor,
    Comment,
    ThreadVerdict,
)
from github_orchestrator.domain import Sha


@dataclass(frozen=True)
class Refresh:
    comments: tuple[Comment, ...] = ()
    anchor: Anchor | None = None
    resolved: bool | None = None
    as_of: str | None = None


@dataclass(frozen=True)
class Wake:
    reason: str
    at: str


@dataclass(frozen=True)
class Reopen:
    viewer: str
    comments: tuple[Comment, ...] = ()
    anchor: Anchor | None = None
    resolved: bool | None = None
    as_of: str | None = None


@dataclass(frozen=True)
class RootGone:
    pass


@dataclass(frozen=True)
class SessionRefused:
    reason: str
    back_to: str


@dataclass(frozen=True)
class RunStarted:
    at: str


@dataclass(frozen=True)
class RunExited:
    at: str
    head: Sha | None = None
    descends: bool = False


@dataclass(frozen=True)
class RunTimedOut:
    reason: str
    at: str


@dataclass(frozen=True)
class RunLost:
    pass


@dataclass(frozen=True)
class Rebase:
    onto: Sha
    conflict: str | None = None


@dataclass(frozen=True)
class WorkspaceCut:
    base_sha: Sha | None


@dataclass(frozen=True)
class Picked:
    landed_base: Sha
    landed_sha: Sha


@dataclass(frozen=True)
class PickRefused:
    reason: str


@dataclass(frozen=True)
class PickConflicted:
    head: Sha
    conflict: str
    diagnostic: str
    rebases_allowed: bool = True


@dataclass(frozen=True)
class Pushed:
    pass


@dataclass(frozen=True)
class PushFailed:
    error: str
    at: str


@dataclass(frozen=True)
class Unpicked:
    pass


@dataclass(frozen=True)
class UnpickFailed:
    error: str


@dataclass(frozen=True)
class AnswerPosted:
    comment: Comment | None = None
    posted_key: str | None = None
    reply: str = ""


@dataclass(frozen=True)
class AnswerDeleted:
    pass


@dataclass(frozen=True)
class AnswerFailed:
    error: str
    at: str


@dataclass(frozen=True)
class ClosingReplyPosted:
    comment: Comment | None = None
    posted_key: str | None = None
    reply: str = ""


@dataclass(frozen=True)
class ClosingCommentDeleted:
    pass


@dataclass(frozen=True)
class ClosingFailed:
    error: str
    deleting: bool = False


@dataclass(frozen=True)
class ReplyPosted:
    parks: bool
    comment: Comment | None = None
    posted_key: str | None = None


@dataclass(frozen=True)
class ReplyFailed:
    error: str


@dataclass(frozen=True)
class GistWritten:
    gist: str
    body: str


@dataclass(frozen=True)
class VerdictGiven:
    verdict: ThreadVerdict
    on: str | None


@dataclass(frozen=True)
class VerdictDue:
    pass


@dataclass(frozen=True)
class ThreadResolved:
    at: str


@dataclass(frozen=True)
class ThreadResolveFailed:
    error: str


@dataclass(frozen=True)
class ThreadUnresolved:
    at: str


@dataclass(frozen=True)
class ThreadUnresolveFailed:
    error: str


@dataclass(frozen=True)
class ReactionPosted:
    pass


@dataclass(frozen=True)
class ReactionFailed:
    error: str


@dataclass(frozen=True)
class DraftPosted:
    comment: Comment
    github_node_id: str | None = None


@dataclass(frozen=True)
class DraftPostFailed:
    error: str


@dataclass(frozen=True)
class Posted:
    comment: Comment
    github_node_id: str | None
    review: str


Event = (
      Refresh
    | Wake
    | Reopen
    | RootGone
    | SessionRefused
    | RunStarted
    | RunExited
    | RunTimedOut
    | RunLost
    | Rebase
    | WorkspaceCut
    | Picked
    | PickRefused
    | PickConflicted
    | Pushed
    | PushFailed
    | Unpicked
    | UnpickFailed
    | AnswerPosted
    | AnswerDeleted
    | AnswerFailed
    | ClosingReplyPosted
    | ClosingCommentDeleted
    | ClosingFailed
    | ReplyPosted
    | ReplyFailed
    | GistWritten
    | VerdictGiven
    | VerdictDue
    | ThreadResolved
    | ThreadResolveFailed
    | ThreadUnresolved
    | ThreadUnresolveFailed
    | ReactionPosted
    | ReactionFailed
    | DraftPosted
    | DraftPostFailed
    | Posted
)
