import secrets
from collections.abc import Iterable
from dataclasses import dataclass, replace

from github_orchestrator.conversation._application.drafts import off_the_diff
from github_orchestrator.conversation._application.ports import (
    Intent,
    Ports,
    Update,
)
from github_orchestrator.conversation._application.settings import ThreadsConfig
from github_orchestrator.conversation._domain.apply import apply
from github_orchestrator.conversation._domain.commands import (
    Approve,
    Command,
    Confirm,
    Defer,
    Discard,
    EditDraft,
    Enrol,
    Place,
    PostNow,
    Reject,
    Reply,
    Resolve,
    Retry,
    Rework,
    StartSession,
    Stop,
    Unpark,
    WithdrawFromReview,
    WriteFix,
)
from github_orchestrator.conversation._domain.conversation import (
    ENROLLED,
    LANDING,
    RUNNING,
    WAKE_MANUAL,
    Brief,
    Conversation,
    Operation,
    OperationKind,
    OperationState,
)
from github_orchestrator.conversation._domain.machine import Refused
from github_orchestrator.conversation._domain.operations import (
    Asked,
    adopted,
    in_flight,
)
from github_orchestrator.conversation._domain.review import Review, Verdict
from github_orchestrator.conversation._domain.standing import ErrorCode
from github_orchestrator.domain import Sha
from github_orchestrator.working_copies import FileDiff


@dataclass(frozen=True)
class Denied:
    code: ErrorCode
    reason: str


KIND_OF_DECISION = {
    "approve": OperationKind.APPROVE,
    "rework": OperationKind.REWORK,
    "session": OperationKind.START_SESSION,
    "resolve": OperationKind.RESOLVE,
    "retry": OperationKind.RETRY,
    "fix": OperationKind.FIRST,
    "stop": OperationKind.STOP,
    "reject": OperationKind.REJECT,
    "not_fixed": OperationKind.REPLY,
    "reply": OperationKind.REPLY,
    "defer": OperationKind.DEFER,
    "unpark": OperationKind.UNPARK,
    "confirm": OperationKind.CONFIRM,
    "place": OperationKind.PLACE,
    "edit-draft": OperationKind.EDIT_DRAFT,
    "enrol": OperationKind.ENROL,
    "withdraw-from-review": OperationKind.WITHDRAW_FROM_REVIEW,
    "discard": OperationKind.DISCARD,
    "post-now": OperationKind.POST_NOW,
}


def _minted(conversation: Conversation) -> str:
    return f"{conversation.key}.{len(conversation.operations) + 1}"


def _asked_for(conversation: Conversation, intent: Intent) -> Operation:
    kind = KIND_OF_DECISION[intent.decision]
    running = in_flight(conversation)
    return Operation(
        id=intent.operation or _minted(conversation),
        kind=kind,
        requested_at=intent.requested_at,
        text=intent.payload or "",
        delete_comment=intent.delete_comment,
        until=(intent.modifier or WAKE_MANUAL if kind == OperationKind.DEFER else None),
        stopped=(running.id if kind == OperationKind.STOP and running else None),
        brief=(Brief(note=intent.payload or "", pointed=intent.pointed,
                     include=intent.include)
               if kind == OperationKind.REWORK else None),
        anchor=intent.anchor,
    )


def _with(conversation: Conversation, operation: Operation) -> Conversation:
    if any(one.id == operation.id for one in conversation.operations):
        return conversation
    return replace(conversation, operations=conversation.operations + (operation,))


def pending_of(conversation: Conversation, intent: Intent | None,
               reply: str | None) -> Conversation:
    """The record with whatever pending decisions it has drawn as pending work.

    A verb is written as a pending decision and answered before the drain takes it,
    so until then the record knows nothing of it. Drawn here, it is on the
    thread's operations the moment it is accepted.
    """
    drawn = adopted(conversation)
    if intent is not None and intent.decision in KIND_OF_DECISION:
        drawn = _with(drawn, _asked_for(drawn, intent))
    if reply is not None:
        drawn = _with(drawn, Operation(id=_minted(drawn), kind=OperationKind.REPLY, text=reply))
    return drawn


def _intent_of(command: Command) -> Intent:
    match command:
        case Approve():
            return Intent(decision="approve", payload=command.reply or None,
                          delete_comment=command.delete_comment,
                          resolve=command.resolve, message=command.message,
                          ticket=command.ticket)
        case Rework():
            return Intent(decision="rework", payload=command.note,
                          pointed=command.pointed, include=command.include)
        case StartSession():
            return Intent(decision="session", payload=command.steer or None,
                          pointed=command.pointed, include=command.include)
        case Resolve():
            return Intent(decision="resolve", payload=command.reply or None,
                          delete_comment=command.delete_comment,
                          resolve=command.resolve,
                          thumbs_up=command.thumbs_up)
        case Reject():
            return Intent(decision="reject", payload=command.reply or None,
                          delete_comment=command.delete_comment)
        case Defer():
            return Intent(decision="defer", payload=command.note or None,
                          modifier=command.wake_on)
        case Reply():
            return Intent(decision="reply", payload=command.text)
        case EditDraft():
            return Intent(decision="edit-draft", payload=command.body,
                          anchor=command.anchor)
        case Stop():
            return Intent(decision="stop")
        case Retry():
            return Intent(decision="retry")
        case WriteFix():
            return Intent(decision="fix")
        case Unpark():
            return Intent(decision="unpark")
        case Confirm():
            return Intent(decision="confirm")
        case Place():
            return Intent(decision="place", modifier=command.to.value)
        case Enrol():
            return Intent(decision="enrol")
        case WithdrawFromReview():
            return Intent(decision="withdraw-from-review")
        case Discard():
            return Intent(decision="discard")
        case PostNow():
            return Intent(decision="post-now")
    raise NotImplementedError(type(command).__name__)


def _allowed(command: Command, config: ThreadsConfig) -> Command:
    if isinstance(command, Rework):
        return replace(command, reworks_allowed=config.agents_enabled)
    if isinstance(command, StartSession):
        return replace(command, sessions_allowed=config.agents_enabled)
    if isinstance(command, Approve):
        return replace(command, account=config.gh_account,
                       filing_allowed=config.agents_enabled)
    if isinstance(command, Resolve | Reject):
        return replace(command, account=config.gh_account)
    return command


def pr_diff(ports: Ports) -> tuple[FileDiff, ...] | None:
    head = Sha.parse(ports.pull_requests.head_sha())
    if head is None:
        return None
    diff = ports.git.pr_diff(ports.pull_requests.base_branch(), head)
    return None if diff is None else diff.files


def _off_the_diff(ports: Ports, conversation: Conversation) -> Denied | None:
    """GitHub refuses a comment on a line outside the pull request's diff,
    and a review goes out as one call, so a bad anchor found at send would
    fail every draft in it."""
    missing = ports.git.no_worktree()
    if missing is not None:
        return Denied(ErrorCode.GIT_FAILED,
                      f"the anchor cannot be checked against the pull request's diff: "
                      f"{missing}")
    files = pr_diff(ports)
    if files is None:
        return Denied(ErrorCode.GIT_FAILED,
                      "git could not produce the pull request's diff to check the "
                      "anchor against")
    anchor = conversation.location
    if anchor is None:
        return Denied(ErrorCode.ANCHOR_NOT_IN_DIFF, "the draft hangs off no line of the diff")
    off = off_the_diff(files, anchor)
    return None if off is None else Denied(ErrorCode.ANCHOR_NOT_IN_DIFF, off)


def _anchor_to_check(conversation: Conversation, command: Command,
                     accepted: Conversation) -> Conversation | None:
    if isinstance(command, Enrol | PostNow):
        return conversation
    if (isinstance(command, EditDraft) and conversation.state == ENROLLED
            and accepted.location != conversation.location):
        return accepted
    return None


def _going_out(reviews: Iterable[Review]) -> bool:
    return any(review.state in (OperationState.PENDING, RUNNING) for review in reviews)


def _operation_id() -> str:
    return f"op_{secrets.token_hex(6)}"


def _asked_again_next(held: Update, command: Command) -> None:
    if held.conversation is None:
        return
    refused = apply(held.conversation, command)
    if isinstance(refused, Refused) and refused.code is ErrorCode.CONFIRM_AGAIN:
        held.conversation = refused.conversation


def _stops_a_landing(conversation: Conversation, command: Command, intent: Intent) -> bool:
    return (isinstance(command, Stop) and intent.decision == "approve"
            and conversation.fix.state == LANDING)


def ask(ports: Ports, conversation: Conversation, command: Command,
        held: Update) -> Conversation | Denied:
    """The refusals the rules can give now, the write into the pending decisions
    the drain reads, and the thread as the drain will leave it.

    `apply` is asked first, with the id and the moment the drain will apply
    the verb with: a state that forbids the verb is knowable on the request,
    and what it accepts is the thread the drain will save before any effect
    reaches GitHub or git. That projection is stamped with the moment of the
    request, so a copy saved before it reads as older and the drain's save
    as not older.
    """
    key = conversation.key
    records = ports.records
    pending = records.pending_on(key)
    if pending.reply is not None or (pending.intent is not None
                                     and not _stops_a_landing(conversation, command, pending.intent)):
        return Denied(ErrorCode.OPERATION_OUTSTANDING,
                      f"thread {key} already has an operation waiting for the board "
                      f"to take it")
    command = _allowed(command, ports.config)
    operation, requested_at = _operation_id(), ports.clock.now()
    asked = replace(_intent_of(command), operation=operation, requested_at=requested_at)
    outcome = apply(conversation, command, requested_at,
                    Asked(id=operation, requested_at=requested_at))
    if isinstance(outcome, Refused):
        if outcome.code is ErrorCode.CONFIRM_AGAIN:
            _asked_again_next(held, command)
        return Denied(outcome.code, outcome.reason)
    if (isinstance(command, EditDraft) and conversation.state == ENROLLED
            and _going_out(records.reviews())):
        return Denied(ErrorCode.REVIEW_IN_FLIGHT,
                      "the draft is in a review on its way to GitHub")
    checked = _anchor_to_check(conversation, command, outcome.conversation)
    if checked is not None:
        off = _off_the_diff(ports, checked)
        if off is not None:
            return off
    records.post(key, asked)
    return replace(outcome.conversation, updated_at=requested_at)


_SAID_AS = {Verdict.APPROVE: "approval", Verdict.REQUEST_CHANGES: "change request",
            Verdict.COMMENT: "comment"}


def send_review(ports: Ports, verdict: Verdict, body: str | None) -> Review | Denied:
    if not ports.github.takes_review(verdict, body):
        return Denied(ErrorCode.EMPTY_BODY,
                      f"GitHub takes no {_SAID_AS[verdict]} without a summary")
    records = ports.records
    with records.update_reviews() as held:
        if _going_out(held.reviews):
            return Denied(ErrorCode.REVIEW_IN_FLIGHT, "a review is already going out")
        review = Review(
            id=_operation_id(), verdict=verdict, body=body,
            requested_at=ports.clock.now(),
            drafts=tuple(conversation.key for conversation in records.list()
                         if conversation.state == ENROLLED))
        held.save(review)
    return review
