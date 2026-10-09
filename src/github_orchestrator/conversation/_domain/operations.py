from dataclasses import dataclass, replace
from typing import Any

from github_orchestrator.conversation._domain.change import Change
from github_orchestrator.conversation._domain.commands import (
    Approve,
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
    ABSENT,
    DECLINED,
    DEFERRED,
    FAILED,
    FILE,
    FIX_RUNS,
    IN_SESSION,
    LANDED,
    LANDING,
    PROPOSED,
    QUEUED,
    REJECTED,
    RESOLVED,
    RUN_KINDS,
    RUNNING,
    WAITING_ON_REVIEWER,
    WAKE_PUSH_PREFIX,
    WITHDRAWN,
    Brief,
    Conversation,
    Operation,
    OperationKind,
    OperationState,
    ReasonCode,
)
from github_orchestrator.conversation._domain.effects import (
    DeleteComment,
    PostDraft,
    PostReply,
    ResolveThread,
    UnresolveThread,
)
from github_orchestrator.conversation._domain.events import (
    ClosingCommentDeleted,
    ClosingFailed,
    ClosingReplyPosted,
    DraftPosted,
    DraftPostFailed,
    PickConflicted,
    PickRefused,
    Posted,
    Rebase,
    ReplyFailed,
    ReplyPosted,
    SessionRefused,
    ThreadResolved,
    ThreadResolveFailed,
    ThreadUnresolved,
    ThreadUnresolveFailed,
    Unpicked,
    UnpickFailed,
)
from github_orchestrator.conversation._domain.standing import ErrorCode
from github_orchestrator.conversation._domain.steps import First

FIX_KINDS = (*FIX_RUNS, OperationKind.START_SESSION, OperationKind.APPROVE)

RUNS_AN_APPROVE_WAITS_ON = (OperationKind.REBASE, OperationKind.FILE)

OUTSTANDING = (OperationState.PENDING, OperationState.RUNNING, OperationState.REQUEUED)

SETTLED = (OperationState.APPLIED, OperationState.REFUSED)

PUT_AWAY = (WAITING_ON_REVIEWER, DEFERRED, REJECTED, RESOLVED)

GITHUB_EFFECTS = (PostReply, DeleteComment, ResolveThread, UnresolveThread,
                  PostDraft)

VERB_KINDS: dict[type, OperationKind] = {
    Approve: OperationKind.APPROVE,
    Rework: OperationKind.REWORK,
    Retry: OperationKind.RETRY,
    WriteFix: OperationKind.FIRST,
    StartSession: OperationKind.START_SESSION,
    Stop: OperationKind.STOP,
    Resolve: OperationKind.RESOLVE,
    Reject: OperationKind.REJECT,
    Defer: OperationKind.DEFER,
    Unpark: OperationKind.UNPARK,
    Confirm: OperationKind.CONFIRM,
    Place: OperationKind.PLACE,
    Reply: OperationKind.REPLY,
    EditDraft: OperationKind.EDIT_DRAFT,
    Enrol: OperationKind.ENROL,
    WithdrawFromReview: OperationKind.WITHDRAW_FROM_REVIEW,
    Discard: OperationKind.DISCARD,
    PostNow: OperationKind.POST_NOW,
    Posted: OperationKind.POSTED,
}

REASON_OF_REFUSAL: dict[type, ReasonCode] = {
    PickRefused: ReasonCode.GIT_FAILED,
    PickConflicted: ReasonCode.CONFLICT,
    Stop: ReasonCode.WITHDRAWN,
    Unpicked: ReasonCode.WITHDRAWN,
    UnpickFailed: ReasonCode.WITHDRAWN,
}


@dataclass(frozen=True)
class Asked:
    """The id and the moment a client asked for a verb with, carried to the
    drain so the operation it becomes is the one the `202` named."""

    id: str
    requested_at: str | None = None


@dataclass(frozen=True)
class _Settling:
    kinds: tuple[OperationKind, ...]
    state: OperationState
    reason_code: ReasonCode | None = None
    reason: str | None = None
    posted_comment: int | None = None


def kind_of(command: Change) -> OperationKind | None:
    return VERB_KINDS.get(type(command))


def _minted(conversation: Conversation, operations: list[Operation]) -> str:
    return f"{conversation.key}.{len(operations) + 1}"


def _fix_kind(conversation: Conversation) -> OperationKind:
    fix = conversation.fix
    if fix.state == IN_SESSION:
        return OperationKind.START_SESSION
    if fix.state in (LANDING, LANDED):
        return OperationKind.APPROVE
    return fix.run.kind


def _fix_outcome(operation: Operation, conversation: Conversation) -> tuple[
        OperationState, str | None, ReasonCode | None]:
    fix = conversation.fix
    if operation.kind == OperationKind.FILE and FILE in fix.steps:
        return OperationState.APPLIED, None, None
    if conversation.state in PUT_AWAY and fix.state in (QUEUED, RUNNING):
        return OperationState.REQUEUED, fix.reason, None
    if fix.state == QUEUED:
        if operation.state in (OperationState.RUNNING, OperationState.REQUEUED):
            return OperationState.REQUEUED, fix.reason, None
        return OperationState.PENDING, None, None
    if fix.state in (RUNNING, IN_SESSION):
        return OperationState.RUNNING, None, None
    if fix.state == LANDING:
        if fix.push_error:
            return OperationState.REFUSED, fix.push_error, ReasonCode.PUSH_FAILED
        if fix.reply_error:
            return OperationState.REFUSED, fix.reply_error, ReasonCode.REPLY_FAILED
        if fix.file_error:
            return OperationState.REFUSED, fix.file_error, ReasonCode.FILE_FAILED
        return OperationState.RUNNING, None, None
    if fix.state == LANDED:
        return OperationState.APPLIED, None, None
    if fix.state == PROPOSED:
        if operation.kind == OperationKind.APPROVE:
            return OperationState.REFUSED, fix.reason, None
        return OperationState.APPLIED, None, None
    if fix.state == DECLINED:
        return OperationState.REFUSED, fix.reason, ReasonCode.AGENT_DECLINED
    if fix.state == FAILED:
        return OperationState.REFUSED, fix.reason, (ReasonCode.WITHDRAWN
                                     if fix.reason == WITHDRAWN
                                     else ReasonCode.MAX_ATTEMPTS)
    return operation.state, operation.reason, operation.reason_code


def _settled_at(before: Operation, state: OperationState, at: str | None) -> str | None:
    if before.state in SETTLED:
        return before.settled_at
    return at if state in SETTLED else None


def _synced(operation: Operation, conversation: Conversation,
            at: str | None) -> Operation:
    state, reason, code = _fix_outcome(operation, conversation)
    return replace(
        operation, state=state, reason=reason,
        reason_code=code,
        settled_at=_settled_at(operation, state, at),
        attempts=(conversation.fix.attempts if operation.kind in RUN_KINDS
                  else operation.attempts))


def adopted(conversation: Conversation) -> Conversation:
    """The record with its current fix as an operation, where a record
    written before the history existed has none for it.

    Deterministic, so the id a read hands out for such a record is the one
    the history gives the fix once something moves it.
    """
    if conversation.fix.state == ABSENT or any(
            operation.kind in FIX_KINDS
            for operation in conversation.operations):
        return conversation
    fix = conversation.fix
    operation = _synced(
        Operation(id=_minted(conversation, list(conversation.operations)),
                  kind=_fix_kind(conversation), requested_at=fix.started_at,
                  state=OperationState.RUNNING if fix.state == QUEUED and fix.attempts
                  else OperationState.PENDING),
        conversation, None)
    return replace(conversation,
                   operations=conversation.operations + (operation,))


def _outstanding(operations: list[Operation],
                 kinds: tuple[OperationKind, ...]) -> int | None:
    for index in range(len(operations) - 1, -1, -1):
        operation = operations[index]
        if operation.kind in kinds and operation.state in OUTSTANDING:
            return index
    return None


def in_flight(conversation: Conversation) -> Operation | None:
    operations = list(adopted(conversation).operations)
    index = _outstanding(operations, FIX_KINDS)
    return operations[index] if index is not None else None


def _running(operations: list[Operation],
             kinds: tuple[OperationKind, ...]) -> int | None:
    for index in range(len(operations) - 1, -1, -1):
        operation = operations[index]
        if operation.kind in kinds and operation.state == OperationState.RUNNING:
            return index
    return None


def _index(operations: list[Operation], operation_id: str) -> int | None:
    for index, operation in enumerate(operations):
        if operation.id == operation_id:
            return index
    return None


def _wake_word(wake_on: str) -> str:
    return "push" if wake_on.startswith(WAKE_PUSH_PREFIX) else wake_on


def _carried(command: Change) -> dict[str, Any]:
    match command:
        case Approve() | Resolve() | Reject():
            return {"text": command.reply,
                    "delete_comment": command.delete_comment}
        case Reply():
            return {"text": command.text}
        case StartSession():
            return {"text": command.steer}
        case Rework():
            return {"brief": Brief(note=command.note, pointed=command.pointed,
                                   include=command.include)}
        case Defer():
            return {"text": command.note, "until": _wake_word(command.wake_on)}
        case EditDraft():
            return {"text": command.body, "anchor": command.anchor}
        case Posted():
            return {"review": command.review,
                    "posted_comment": command.comment.id,
                    "github_node_id": command.github_node_id}
    return {}


def _own_id(conversation: Conversation, operations: list[Operation],
            kind: OperationKind, asked: Asked | None) -> str:
    if asked is not None:
        return asked.id
    for operation in reversed(operations):
        if operation.kind == kind and operation.state in (OperationState.PENDING, OperationState.REQUEUED):
            return operation.id
    return _minted(conversation, operations)


def _upserted(operations: list[Operation], operation: Operation) -> None:
    index = _index(operations, operation.id)
    if index is None:
        operations.append(operation)
        return
    kept = operations[index]
    operations[index] = replace(operation, requested_at=kept.requested_at)


def asked_of(conversation: Conversation, command: Change,
             asked: Asked | None, at: str | None) -> Operation:
    """The operation a verb becomes, before anything has settled it."""
    kind = VERB_KINDS[type(command)]
    operations = list(adopted(conversation).operations)
    return Operation(
        id=_own_id(conversation, operations, kind, asked), kind=kind,
        requested_at=asked.requested_at if asked is not None else at,
        **_carried(command))


def blocking(conversation: Conversation, command: Change,
             asked: Asked | None) -> Operation | None:
    """Whatever is still outstanding that this verb must wait behind.

    A run in flight is not in the way: the transition table takes stop,
    defer and reply over one state by state. What is in the way is a verb
    still posting to GitHub, or an approve the drain has not taken yet.
    """
    kind = kind_of(command)
    if kind is None:
        return None
    own = asked_of(conversation, command, asked, None).id
    for operation in conversation.operations:
        if operation.id == own:
            continue
        if operation.kind not in FIX_KINDS and operation.state in (OperationState.PENDING,
                                                                   OperationState.RUNNING):
            return operation
        if operation.kind == OperationKind.APPROVE and operation.state == OperationState.PENDING:
            return operation
    return None


def _settling(command: Change, effects: tuple[Any, ...]) -> _Settling | None:
    posts_again = any(isinstance(effect, ResolveThread) for effect in effects)
    match command:
        case ReplyPosted():
            return _Settling((OperationKind.REPLY,), OperationState.APPLIED, posted_comment=(
                command.comment.id if command.comment else None))
        case ReplyFailed():
            return _Settling((OperationKind.REPLY,), OperationState.REFUSED, ReasonCode.REPLY_FAILED,
                             command.error)
        case ClosingReplyPosted():
            return _Settling((OperationKind.RESOLVE, OperationKind.REJECT),
                             OperationState.RUNNING if posts_again else OperationState.APPLIED,
                             posted_comment=(command.comment.id
                                             if command.comment else None))
        case ClosingCommentDeleted():
            return _Settling((OperationKind.RESOLVE, OperationKind.REJECT), OperationState.APPLIED)
        case ClosingFailed():
            verb = "delete" if command.deleting else "reply"
            return _Settling((OperationKind.RESOLVE, OperationKind.REJECT), OperationState.REFUSED,
                             ReasonCode.GITHUB_REJECTED if command.deleting
                             else ReasonCode.REPLY_FAILED,
                             f"{verb} failed: {command.error}")
        case ThreadResolved():
            return _Settling((OperationKind.RESOLVE,), OperationState.APPLIED)
        case ThreadResolveFailed():
            return _Settling((OperationKind.RESOLVE,), OperationState.REFUSED, ReasonCode.GITHUB_REJECTED,
                             f"resolve failed: {command.error}")
        case ThreadUnresolved():
            return _Settling((OperationKind.UNPARK,), OperationState.APPLIED)
        case ThreadUnresolveFailed():
            return _Settling((OperationKind.UNPARK,), OperationState.REFUSED, ReasonCode.GITHUB_REJECTED,
                             f"reopen failed: {command.error}")
        case DraftPosted():
            return _Settling((OperationKind.POST_NOW,), OperationState.APPLIED,
                             posted_comment=command.comment.id)
        case DraftPostFailed():
            return _Settling((OperationKind.POST_NOW,), OperationState.REFUSED, ReasonCode.GITHUB_REJECTED,
                             f"post failed: {command.error}")
    return None


def _settle(operations: list[Operation], settling: _Settling,
            at: str | None) -> None:
    index = _running(operations, settling.kinds)
    if index is None:
        return
    operation = operations[index]
    operations[index] = replace(
        operation, state=settling.state, reason=settling.reason,
        reason_code=settling.reason_code,
        settled_at=at if settling.state in SETTLED else None,
        posted_comment=(settling.posted_comment
                        if settling.posted_comment is not None
                        else operation.posted_comment))


def _sync_fix(operations: list[Operation], after: Conversation,
              command: Change, at: str | None) -> None:
    index = _outstanding(operations, FIX_KINDS)
    if index is None:
        return
    synced = _synced(operations[index], after, at)
    if isinstance(command, SessionRefused):
        synced = replace(synced, state=OperationState.REFUSED, reason=command.reason,
                         reason_code=ReasonCode.AGENT_UNAVAILABLE,
                         settled_at=_settled_at(operations[index], OperationState.REFUSED,
                                                at))
    override = REASON_OF_REFUSAL.get(type(command))
    if synced.state == OperationState.REFUSED and override is not None:
        synced = replace(synced, reason_code=override)
    operations[index] = synced


def _requeue_the_approve(operations: list[Operation]) -> None:
    index = _outstanding(operations, (OperationKind.APPROVE,))
    if index is not None:
        operations[index] = replace(operations[index], state=OperationState.REQUEUED)


def _queues_a_run_the_approve_waits_on(before: Conversation, after: Conversation,
                                       command: Change) -> bool:
    return (isinstance(command, (Rebase, PickConflicted, Approve))
            and before.fix.state != QUEUED and after.fix.state == QUEUED
            and after.fix.run.kind in RUNS_AN_APPROVE_WAITS_ON)


def _opened(after: Conversation, operations: list[Operation], kind: OperationKind,
            at: str | None) -> None:
    _upserted(operations, _synced(
        Operation(id=_minted(after, operations), kind=kind, requested_at=at),
        after, at))


def _verb(before: Conversation, after: Conversation,
          operations: list[Operation], command: Change,
          effects: tuple[Any, ...], asked: Asked | None, at: str | None,
          stopped: str | None) -> None:
    operation = asked_of(before, command, asked, at)
    if operation.kind in FIX_KINDS:
        _upserted(operations, _synced(operation, after, at))
        return
    if (operation.kind == OperationKind.EDIT_DRAFT and operations
            and operations[-1].kind == OperationKind.EDIT_DRAFT
            and operations[-1].id != operation.id):
        operations.pop()
    posts = any(isinstance(effect, GITHUB_EFFECTS) for effect in effects)
    state = OperationState.RUNNING if posts else OperationState.APPLIED
    _upserted(operations, replace(
        operation, state=state, settled_at=at if state == OperationState.APPLIED else None,
        stopped=stopped))


def _stored(before: Conversation, after: Conversation,
            operations: list[Operation]) -> Conversation:
    if operations == list(adopted(before).operations):
        return after
    return replace(after, operations=tuple(operations))


def accepted(before: Conversation, after: Conversation, command: Change,
             effects: tuple[Any, ...], asked: Asked | None,
             at: str | None) -> Conversation:
    """The history once the domain has taken a command."""
    operations = list(adopted(before).operations)
    stopped_at = _outstanding(operations, FIX_KINDS)
    stopped = (operations[stopped_at].id
               if isinstance(command, Stop) and stopped_at is not None
               else None)
    if _queues_a_run_the_approve_waits_on(before, after, command):
        _requeue_the_approve(operations)
        _opened(after, operations, after.fix.run.kind, at)
    _sync_fix(operations, after, command, at)
    if kind_of(command) is not None:
        _verb(before, after, operations, command, effects, asked, at, stopped)
    if isinstance(command, First) or (
            isinstance(command, Unpark | Place) and after.fix.state == QUEUED
            and before.fix.state != QUEUED):
        _opened(after, operations, OperationKind.FIRST, at)
    settling = _settling(command, effects)
    if settling is not None:
        _settle(operations, settling, at)
    return _stored(before, after, operations)


def refused(before: Conversation, after: Conversation, command: Change,
            reason: str, asked: Asked | None,
            at: str | None) -> Conversation:
    """The history once the domain has turned a command down.

    Only a verb a client asked for is written: its `202` named it, so the
    history has to say what became of it. A verb nobody holds an id for
    leaves nothing behind when it is refused.
    """
    if asked is None or kind_of(command) is None:
        return after
    operations = list(adopted(after).operations)
    _upserted(operations, replace(asked_of(before, command, asked, at),
                                  state=OperationState.REFUSED, reason=reason,
                                  settled_at=at))
    return replace(after, operations=tuple(operations))


def deferred(before: Conversation, after: Conversation, command: Change,
             asked: Asked | None, at: str | None) -> Conversation:
    """The history once the domain has put a command off for a later pass."""
    operations = list(adopted(before).operations)
    if asked is not None and kind_of(command) is not None and _index(
            operations, asked.id) is None:
        operations.append(asked_of(before, command, asked, at))
    if _queues_a_run_the_approve_waits_on(before, after, command):
        _requeue_the_approve(operations)
        _opened(after, operations, after.fix.run.kind, at)
    return _stored(before, after, operations)


def outstanding_refusal(operation: Operation) -> tuple[ErrorCode, str]:
    return (ErrorCode.OPERATION_OUTSTANDING,
            f"the {operation.kind} {operation.id} is still outstanding on "
            f"this thread")
