from dataclasses import dataclass

from github_orchestrator.conversation._domain.conversation import Brief
from github_orchestrator.domain import Sha

GIST_ROOT = "root"
GIST_THREAD = "thread"


@dataclass(frozen=True)
class StartRun:
    kind: str
    onto: Sha | None = None


@dataclass(frozen=True)
class StopRun:
    pass


@dataclass(frozen=True)
class OpenSession:
    back_to: str
    steer: str | None = None
    skipped: bool = False
    brief: Brief | None = None


@dataclass(frozen=True)
class CutWorkspace:
    pass


@dataclass(frozen=True)
class DropWorkspace:
    pass


@dataclass(frozen=True)
class Pick:
    message: str = ""


@dataclass(frozen=True)
class Push:
    pass


@dataclass(frozen=True)
class Unpick:
    pass


@dataclass(frozen=True)
class PostReply:
    body: str = ""
    commit: Sha | None = None


@dataclass(frozen=True)
class DeleteComment:
    pass


@dataclass(frozen=True)
class ResolveThread:
    pass


@dataclass(frozen=True)
class UnresolveThread:
    pass


@dataclass(frozen=True)
class React:
    comment_id: int


@dataclass(frozen=True)
class PostDraft:
    pass


@dataclass(frozen=True)
class WriteGist:
    source: str = GIST_ROOT


@dataclass(frozen=True)
class AskVerdict:
    pass


Effect = (
      StartRun
    | StopRun
    | OpenSession
    | CutWorkspace
    | DropWorkspace
    | Pick
    | Push
    | Unpick
    | PostReply
    | DeleteComment
    | PostDraft
    | WriteGist
    | AskVerdict
)
