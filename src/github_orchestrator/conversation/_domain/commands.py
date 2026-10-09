from dataclasses import dataclass

from github_orchestrator.conversation._domain.conversation import (
    WAKE_MANUAL,
    Classification,
    ConversationState,
    PointedLine,
    Ticket,
)
from github_orchestrator.domain import Location


@dataclass(frozen=True)
class Reject:
    reply: str = ""
    delete_comment: bool = False
    account: str = ""


@dataclass(frozen=True)
class Defer:
    wake_on: str = WAKE_MANUAL
    note: str = ""


@dataclass(frozen=True)
class Unpark:
    pass


@dataclass(frozen=True)
class Confirm:
    pass


@dataclass(frozen=True)
class Place:
    to: ConversationState


@dataclass(frozen=True)
class DeclarePlan:
    steps: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True)
class StepDone:
    indexes: tuple[int, ...]


@dataclass(frozen=True)
class ReportReady:
    sha: str
    on_base: bool
    tests: str | None = None
    tests_note: str | None = None
    agent_note: str | None = None
    summary: str | None = None
    confidence: str | None = None
    confidence_note: str | None = None


@dataclass(frozen=True)
class MoveBase:
    sha: str


@dataclass(frozen=True)
class ReportDeclined:
    classification: Classification
    reason: str


@dataclass(frozen=True)
class ReportReply:
    classification: Classification
    body: str


@dataclass(frozen=True)
class ReportTicket:
    ticket: Ticket
    reply: str


def report_without_code(classification: Classification, text: str,
                        ticket: Ticket | None = None) -> ReportDeclined | ReportReply | ReportTicket:
    if ticket is not None:
        return ReportTicket(ticket=ticket, reply=text)
    if classification.asks_a_reply:
        return ReportReply(classification=classification, body=text)
    return ReportDeclined(classification=classification, reason=text)


@dataclass(frozen=True)
class ReportFiled:
    key: str
    url: str


@dataclass(frozen=True)
class Fail:
    reason: str


@dataclass(frozen=True)
class Approve:
    reply: str = ""
    delete_comment: bool = False
    resolve: bool = False
    message: str = ""
    ticket: Ticket | None = None
    run_alive: bool = False
    worktree_clean: bool = True
    filing_allowed: bool = True
    account: str = ""


@dataclass(frozen=True)
class Rework:
    note: str = ""
    pointed: tuple[PointedLine, ...] = ()
    include: tuple[str, ...] = ()
    reworks_allowed: bool = True


@dataclass(frozen=True)
class StartSession:
    steer: str = ""
    pointed: tuple[PointedLine, ...] = ()
    include: tuple[str, ...] = ()
    sessions_allowed: bool = True


@dataclass(frozen=True)
class Retry:
    pass


@dataclass(frozen=True)
class WriteFix:
    pass


@dataclass(frozen=True)
class Stop:
    pass


@dataclass(frozen=True)
class Resolve:
    reply: str = ""
    delete_comment: bool = False
    resolve: bool = False
    thumbs_up: bool = True
    account: str = ""


@dataclass(frozen=True)
class Reply:
    text: str


@dataclass(frozen=True)
class EditDraft:
    body: str
    anchor: Location


@dataclass(frozen=True)
class Enrol:
    pass


@dataclass(frozen=True)
class WithdrawFromReview:
    pass


@dataclass(frozen=True)
class Discard:
    pass


@dataclass(frozen=True)
class PostNow:
    pass


Command = (
      Reject
    | Defer
    | Unpark
    | Confirm
    | Place
    | DeclarePlan
    | StepDone
    | ReportReady
    | MoveBase
    | ReportDeclined
    | ReportReply
    | ReportTicket
    | ReportFiled
    | Fail
    | Approve
    | Rework
    | StartSession
    | Retry
    | WriteFix
    | Stop
    | Resolve
    | Reply
    | EditDraft
    | Enrol
    | WithdrawFromReview
    | Discard
    | PostNow
)
