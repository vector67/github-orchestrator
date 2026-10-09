import logging
from dataclasses import dataclass, replace

from github_orchestrator.conversation._application.ports import Intent, Ports
from github_orchestrator.conversation._application.reviews import send_reviews
from github_orchestrator.conversation._application.runner import resume, run
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
    WAKE_MANUAL,
    WAKE_PUSH_PREFIX,
    Conversation,
    ConversationState,
)
from github_orchestrator.conversation._domain.machine import Accepted, Deferred, Refused
from github_orchestrator.conversation._domain.operations import Asked
from github_orchestrator.conversation._domain.standing import ErrorCode
from github_orchestrator.domain import Pr

log = logging.getLogger(__name__)


def decide(pr: Pr, ports: Ports) -> None:
    try:
        _drain(pr, ports)
    except Exception:
        log.exception("The board's decisions could not be drained for %s",
                      pr)


def _drain(pr: Pr, ports: Ports) -> None:
    pending = ports.records.pending()
    for key in [key for key, entry in pending.items() if entry.reply is not None]:
        try:
            _reply(pr, key, ports)
        except Exception:
            log.exception("The panel reply for %s thread %s failed; it "
                          "will be retried on the next drain", pr, key)
    for key in [key for key, entry in pending.items()
                if entry.intent is not None or entry.garbled]:
        try:
            _intent(pr, key, ports)
        except Exception:
            log.exception("The intent for %s thread %s failed; it will be "
                          "retried on the next drain", pr, key)
    send_reviews(pr, ports)


def _reply(pr: Pr, key: str, ports: Ports) -> None:
    with ports.records.update(key) as update:
        text = ports.records.pending_on(key).reply
        if text is None:
            return
        conversation = update.conversation
        outcome = None
        if conversation is not None:
            outcome = run(ports, conversation, Reply(text))
            if outcome.conversation != conversation:
                update.conversation = outcome.conversation
                ports.records.save(outcome.conversation)
        if outcome is None:
            log.warning("Clearing the reply for %s thread %s: no record",
                        pr, key)
        elif isinstance(outcome, Refused):
            log.warning("The panel reply for %s thread %s was refused; it "
                        "will be retried on the next drain: %s",
                        pr, key, outcome.reason)
            return
        if ports.records.pending_on(key).reply != text:
            log.info("Keeping the reply for %s thread %s: it was rewritten "
                     "while it was being posted", pr, key)
            return
        ports.records.clear(key, "reply")


def _intent(pr: Pr, key: str, ports: Ports) -> None:
    with ports.records.update(key) as update:
        intent = ports.records.pending_on(key).intent
        if intent is None:
            log.warning("Clearing a garbage intent for %s thread %s",
                        pr, key)
            ports.records.clear(key, "intent")
            return
        conversation = update.conversation
        outcome = None
        if conversation is not None:
            outcome = _decided(ports, conversation, intent)
            if outcome.conversation != conversation:
                update.conversation = outcome.conversation
        if outcome is None:
            log.warning("Clearing the %s intent for %s thread %s: no record",
                        intent.decision, pr, key)
        elif isinstance(outcome, Deferred):
            log.info("Deferring the %s for %s thread %s: %s",
                     intent.decision, pr, key, outcome.reason)
            return
        elif isinstance(outcome, Refused):
            log.warning("Refusing the %s for %s thread %s: %s",
                        intent.decision, pr, key, outcome.reason)
        if ports.records.pending_on(key).intent != intent:
            log.info("Keeping the %s intent for %s thread %s: it was "
                     "replaced while it was being decided",
                     intent.decision, pr, key)
            return
        ports.records.clear(key, "intent")


@dataclass(frozen=True)
class _Refusal:
    code: ErrorCode
    reason: str


def _refused(conversation: Conversation, code: ErrorCode,
             reason: str) -> Refused:
    return Refused(replace(conversation,
                           fix=replace(conversation.fix,
                                       decision_error=reason)),
                   code, reason)


def _asked(intent: Intent) -> Asked | None:
    if intent.operation is None:
        return None
    return Asked(id=intent.operation, requested_at=intent.requested_at)


def _decided(ports: Ports, conversation: Conversation,
             intent: Intent) -> Accepted | Refused | Deferred:
    command = _command(ports, intent)
    if isinstance(command, _Refusal):
        return _refused(conversation, command.code, command.reason)
    if isinstance(command, Approve):
        return resume(ports, conversation, command, _asked(intent))
    return run(ports, conversation, command, _asked(intent))


def _command(ports: Ports, intent: Intent) -> Command | _Refusal:
    payload = intent.payload or ""
    match intent.decision:
        case "approve":
            return Approve(
                reply=payload,
                delete_comment=intent.delete_comment,
                resolve=intent.resolve,
                message=intent.message,
                ticket=intent.ticket,
                run_alive=ports.agents.run_alive(),
                worktree_clean=ports.git.is_clean(),
                filing_allowed=ports.config.agents_enabled,
                account=ports.config.gh_account,
            )
        case "rework":
            return Rework(
                note=payload,
                pointed=intent.pointed,
                include=intent.include,
                reworks_allowed=ports.config.agents_enabled)
        case "session":
            return StartSession(
                steer=payload,
                pointed=intent.pointed,
                include=intent.include,
                sessions_allowed=ports.config.agents_enabled)
        case "resolve":
            return Resolve(reply=payload,
                           delete_comment=intent.delete_comment,
                           resolve=intent.resolve,
                           thumbs_up=intent.thumbs_up,
                           account=ports.config.gh_account)
        case "retry":
            return Retry()
        case "fix":
            return WriteFix()
        case "stop":
            return Stop()
        case "reject":
            return Reject(reply=payload,
                          delete_comment=intent.delete_comment,
                          account=ports.config.gh_account)
        case "not_fixed" | "reply":
            return Reply(text=payload)
        case "defer":
            if intent.modifier == "push":
                head = ports.pull_requests.head_sha()
                if head is None:
                    return _Refusal(ErrorCode.BAD_WAKE_CONDITION,
                                    "no head to wait on")
                return Defer(wake_on=f"{WAKE_PUSH_PREFIX}{head}",
                             note=payload)
            return Defer(wake_on=intent.modifier or WAKE_MANUAL,
                         note=payload)
        case "unpark":
            return Unpark()
        case "confirm":
            return Confirm()
        case "place":
            return Place(to=ConversationState(intent.modifier))
        case "edit-draft":
            if intent.anchor is None:
                return _Refusal(ErrorCode.MALFORMED_REQUEST,
                                "the edit names nowhere to hang the draft")
            return EditDraft(body=payload, anchor=intent.anchor)
        case "enrol":
            return Enrol()
        case "withdraw-from-review":
            return WithdrawFromReview()
        case "discard":
            return Discard()
        case "post-now":
            return PostNow()
    raise NotImplementedError(intent.decision)
