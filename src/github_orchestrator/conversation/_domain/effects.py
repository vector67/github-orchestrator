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
    answers: bool = False


@dataclass(frozen=True)
class OpenLoginShell:
    pass


@dataclass(frozen=True)
class CutWorkspace:
    pass


@dataclass(frozen=True)
class DropWorkspace:
    cut_at: Sha | None = None


@dataclass(frozen=True)
class ResetWorkspace:
    to: Sha


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
class MatchDraft:
    url: str
    draft: bool


@dataclass(frozen=True)
class UnresolveThread:
    pass


@dataclass(frozen=True)
class React:
    comment_id: int
    node_id: str


@dataclass(frozen=True)
class PostDraft:
    pass


@dataclass(frozen=True)
class WriteGist:
    source: str = GIST_ROOT


@dataclass(frozen=True)
class AskVerdict:
    pass


@dataclass(frozen=True)
class AskCommitCheck:
    on: str
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class AskFixCheck:
    on: str
    base: Sha
    head: Sha


Effect = (
      StartRun
    | MatchDraft
    | StopRun
    | OpenSession
    | OpenLoginShell
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
    | AskCommitCheck
    | AskFixCheck
)
