import logging
from collections.abc import Callable
from dataclasses import dataclass, replace

from github_orchestrator.conversation._application.ports import (
    Ports,
    WorkspaceRefused,
    thread_workspace,
)
from github_orchestrator.conversation._domain.apply import apply
from github_orchestrator.conversation._domain.change import Change
from github_orchestrator.conversation._domain.commands import (
    Approve,
    Fail,
    Reject,
    Reply,
    Resolve,
)
from github_orchestrator.conversation._domain.conversation import (
    Conversation,
    ThreadVerdict,
)
from github_orchestrator.conversation._domain.effects import (
    AskVerdict,
    CutWorkspace,
    DeleteComment,
    DropWorkspace,
    Effect,
    OpenSession,
    Pick,
    PostDraft,
    PostReply,
    Push,
    React,
    ResolveThread,
    StartRun,
    StopRun,
    Unpick,
    UnresolveThread,
    WriteGist,
)
from github_orchestrator.conversation._domain.events import (
    AnswerDeleted,
    AnswerFailed,
    AnswerPosted,
    ClosingCommentDeleted,
    ClosingFailed,
    ClosingReplyPosted,
    DraftPosted,
    DraftPostFailed,
    GistWritten,
    PickConflicted,
    Picked,
    PickRefused,
    Pushed,
    PushFailed,
    ReactionFailed,
    ReactionPosted,
    ReplyFailed,
    ReplyPosted,
    SessionRefused,
    ThreadResolved,
    ThreadResolveFailed,
    ThreadUnresolved,
    ThreadUnresolveFailed,
    Unpicked,
    UnpickFailed,
    VerdictGiven,
    WorkspaceCut,
)
from github_orchestrator.conversation._domain.machine import (
    REWORK_ADVICE,
    Accepted,
    Deferred,
    Refused,
    landing_under_way,
)
from github_orchestrator.conversation._domain.operations import Asked
from github_orchestrator.conversation._domain.standing import ErrorCode
from github_orchestrator.conversation._domain.steps import Land
from github_orchestrator.conversation._domain.verdict import newest_said

MAX_RESUME_PASSES = 8

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Pass:
    outcome: Accepted | Refused | Deferred
    finished: bool
    saved: Conversation


def _failed(conversation: Conversation, effect: Effect, exc: Exception) -> str:
    log.warning("%s failed for conversation %s", type(effect).__name__,
                conversation.key, exc_info=exc)
    return str(exc) or type(exc).__name__


def _pick_outcome(ports: Ports, conversation: Conversation,
                  effect: Pick) -> Change:
    fix = conversation.fix
    picked = thread_workspace(ports, conversation).pick(fix.thread_sha, effect.message)
    if picked.landed_base is not None and picked.landed_sha is not None:
        return Picked(landed_base=picked.landed_base, landed_sha=picked.landed_sha)
    if picked.conflict_head is not None and picked.conflict is not None:
        return PickConflicted(head=picked.conflict_head, conflict=picked.conflict,
                              diagnostic=picked.diagnostic,
                              rebases_allowed=ports.config.agents_enabled)
    if picked.not_commits:
        return PickRefused(
            f"this thread names {None if fix.base_sha is None else str(fix.base_sha)!r}.."
            f"{None if fix.thread_sha is None else str(fix.thread_sha)!r}, which is not "
            f"a pair of commit hashes, so there is nothing safe to land; "
            f"{REWORK_ADVICE}"
        )
    if picked.missing_branch is not None:
        return PickRefused(
            f"the thread's branch {picked.missing_branch} could not be resolved, so "
            f"there is nothing to land; {REWORK_ADVICE} — {picked.diagnostic}"
        )
    if picked.changed_since_review:
        return PickRefused(
            f"the fix was changed after the board reviewed it, so approving "
            f"would land something you have not seen; re-report it with "
            f"`cli thread ready --sha <new sha>`, or {REWORK_ADVICE}"
        )
    return PickRefused(picked.refusal or "git gave no reason")


def _reply_outcome(ports: Ports, conversation: Conversation,
                   effect: PostReply, verb: Change | None) -> Change:
    try:
        posted = ports.github.post_reply(conversation, effect.body,
                                         effect.commit)
    except Exception as exc:
        match verb:
            case Approve():
                return AnswerFailed(_failed(conversation, effect, exc), at=ports.clock.now())
            case Resolve() | Reject():
                return ClosingFailed(_failed(conversation, effect, exc), deleting=False)
            case Reply():
                return ReplyFailed(_failed(conversation, effect, exc))
        raise
    match verb:
        case Approve():
            return AnswerPosted(comment=posted.comment,
                                posted_key=posted.posted_key,
                                reply=effect.body)
        case Resolve() | Reject():
            return ClosingReplyPosted(comment=posted.comment,
                                      posted_key=posted.posted_key,
                                      reply=effect.body)
        case Reply():
            return ReplyPosted(parks=conversation.awaits_you,
                               comment=posted.comment,
                               posted_key=posted.posted_key)
    raise NotImplementedError(type(verb).__name__)


def _delete_outcome(ports: Ports, conversation: Conversation,
                    effect: DeleteComment, verb: Change | None) -> Change:
    try:
        ports.github.delete_comment(conversation)
    except Exception as exc:
        match verb:
            case Approve():
                return AnswerFailed(_failed(conversation, effect, exc), at=ports.clock.now())
            case Resolve() | Reject():
                return ClosingFailed(_failed(conversation, effect, exc), deleting=True)
        raise
    match verb:
        case Approve():
            return AnswerDeleted()
        case Resolve() | Reject():
            return ClosingCommentDeleted()
    raise NotImplementedError(type(verb).__name__)


def _post_outcome(ports: Ports, conversation: Conversation,
                  effect: PostDraft) -> Change:
    head = ports.pull_requests.head_sha()
    if head is None:
        return DraftPostFailed("the pull request has no head to post against")
    try:
        posted = ports.github.post_review_comment(conversation, head)
    except Exception as exc:
        return DraftPostFailed(_failed(conversation, effect, exc))
    return DraftPosted(comment=posted.comment, github_node_id=posted.key)


def _gist_recorder(ports: Ports,
                   conversation: Conversation) -> Callable[[str], None]:
    key, body = conversation.key, conversation.body

    def record(gist: str) -> None:
        with ports.records.update(key) as update:
            stored = update.conversation
            if stored is None:
                return
            outcome = run(ports, stored, GistWritten(gist=gist, body=body))
            if outcome.conversation != stored:
                update.conversation = outcome.conversation

    return record


def _verdict_recorder(ports: Ports,
                      conversation: Conversation) -> Callable[[ThreadVerdict], None]:
    key, on = conversation.key, newest_said(conversation)

    def record(verdict: ThreadVerdict) -> None:
        with ports.records.update(key) as update:
            stored = update.conversation
            if stored is None:
                return
            outcome = run(ports, stored, VerdictGiven(verdict=verdict, on=on))
            if outcome.conversation != stored:
                update.conversation = outcome.conversation

    return record


def _unpick_outcome(ports: Ports, conversation: Conversation) -> Change:
    fix = conversation.fix
    if fix.landed_base is None or fix.landed_sha is None:
        return UnpickFailed("the record names no commit it picked")
    error = ports.git.unpick(fix.landed_base, fix.landed_sha)
    return Unpicked() if error is None else UnpickFailed(error)


def _perform(ports: Ports, conversation: Conversation, effect: Effect,
             verb: Change | None) -> Change | None:
    match effect:
        case CutWorkspace():
            cut = thread_workspace(ports, conversation).ensure()
            if cut.workspace is None:
                raise WorkspaceRefused(cut.failure)
            return WorkspaceCut(base_sha=cut.workspace.base_sha)
        case OpenSession():
            refused = ports.agents.open_session(thread_workspace(ports, conversation).path,
                                                conversation, effect.steer, effect.skipped,
                                                effect.brief)
            return (None if refused is None
                    else SessionRefused(reason=refused, back_to=effect.back_to))
        case Pick():
            return _pick_outcome(ports, conversation, effect)
        case Push():
            error = ports.git.push()
            return (Pushed() if error is None
                    else PushFailed(error, at=ports.clock.now()))
        case Unpick():
            return _unpick_outcome(ports, conversation)
        case PostReply():
            return _reply_outcome(ports, conversation, effect, verb)
        case DeleteComment():
            return _delete_outcome(ports, conversation, effect, verb)
        case PostDraft():
            return _post_outcome(ports, conversation, effect)
        case ResolveThread():
            try:
                ports.github.resolve_thread(conversation)
            except Exception as exc:
                return ThreadResolveFailed(_failed(conversation, effect, exc))
            return ThreadResolved(at=ports.clock.now())
        case UnresolveThread():
            try:
                ports.github.unresolve_thread(conversation)
            except Exception as exc:
                return ThreadUnresolveFailed(_failed(conversation, effect, exc))
            return ThreadUnresolved(at=ports.clock.now())
        case React():
            try:
                ports.github.react(conversation, effect.comment_id)
            except Exception as exc:
                return ReactionFailed(_failed(conversation, effect, exc))
            return ReactionPosted()
        case DropWorkspace():
            failure = thread_workspace(ports, conversation).drop()
            if failure is not None:
                raise WorkspaceRefused(failure)
            return None
        case StartRun():
            try:
                refused = ports.agents.start_run(conversation,
                                                 thread_workspace(ports, conversation).path,
                                                 effect.kind, effect.onto)
            except Exception as exc:
                _failed(conversation, effect, exc)
                return Fail("failed to launch the agent run")
            if refused is not None:
                log.warning("StartRun failed for conversation %s: %s",
                            conversation.key, refused)
                return Fail("failed to launch the agent run")
            return None
        case StopRun():
            ports.agents.stop_run(conversation.key)
            return None
        case WriteGist():
            ports.summaries.write_gist(conversation, effect.source,
                                       _gist_recorder(ports, conversation))
            return None
        case AskVerdict():
            ports.summaries.ask_verdict(conversation, _verdict_recorder(ports, conversation))
            return None
    raise NotImplementedError(type(effect).__name__)


def _drive(ports: Ports, outcome: Accepted | Refused | Deferred,
           verb: Change | None,
           saved: Conversation) -> _Pass:
    while isinstance(outcome, Accepted) and outcome.effects:
        conversation = outcome.conversation
        asked_for = outcome.effects
        yielded = False
        for effect in asked_for:
            if conversation != saved:
                ports.records.save(conversation)
                saved = conversation
            result = _perform(ports, conversation, effect, verb)
            if result is None:
                continue
            yielded = True
            outcome = apply(conversation, result, ports.clock.now())
            if not isinstance(outcome, Accepted):
                return _Pass(outcome, True, saved)
            conversation = outcome.conversation
        if not yielded:
            return _Pass(outcome, True, saved)
    return _Pass(outcome, not isinstance(outcome, Accepted), saved)


def _once(ports: Ports, conversation: Conversation, command: Change,
          saved: Conversation, asked: Asked | None = None) -> _Pass:
    return _drive(ports, apply(conversation, command, ports.clock.now(),
                               asked),
                  command, saved)


def run(ports: Ports, conversation: Conversation, command: Change,
        asked: Asked | None = None) -> Accepted | Refused | Deferred:
    return _once(ports, conversation, command, conversation, asked).outcome


def perform(ports: Ports,
            outcome: Accepted) -> Accepted | Refused | Deferred:
    return _drive(ports, outcome, None, outcome.conversation).outcome


def _carried_on(command: Approve) -> Land:
    return Land(reply=command.reply, delete_comment=command.delete_comment,
                resolve=command.resolve, message=command.message,
                run_alive=command.run_alive,
                worktree_clean=command.worktree_clean)


def resume(ports: Ports, conversation: Conversation, command: Approve,
           asked: Asked | None = None) -> Accepted | Refused | Deferred:
    """An approve, carried through every step the drain can take now.

    The first pass asks; every pass after drives the landing that ask
    started. A landing a restart interrupted is driven from the first pass,
    because asking again for one already under way is refused.
    """
    saved = conversation
    step_with: Approve = (_carried_on(command)
                          if landing_under_way(conversation) else command)
    for _ in range(MAX_RESUME_PASSES):
        step = _once(ports, conversation, step_with, saved, asked)
        if step.finished or not landing_under_way(step.outcome.conversation):
            return step.outcome
        conversation = step.outcome.conversation
        saved = step.saved
        step_with, asked = _carried_on(command), None
    reason = f"the decision did not settle in {MAX_RESUME_PASSES} passes"
    return Refused(
        replace(conversation,
                fix=replace(conversation.fix, decision_error=reason)),
        ErrorCode.INTERNAL_REFUSAL,
        reason,
    )
