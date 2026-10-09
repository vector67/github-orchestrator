from dataclasses import replace
from typing import Any

from github_orchestrator.conversation._domain import operations as history
from github_orchestrator.conversation._domain.change import Change
from github_orchestrator.conversation._domain.commands import (
    Approve,
    Confirm,
    DeclarePlan,
    Defer,
    Discard,
    EditDraft,
    Enrol,
    Fail,
    MoveBase,
    Place,
    PostNow,
    Reject,
    Reply,
    ReportDeclined,
    ReportFiled,
    ReportReady,
    ReportReply,
    ReportTicket,
    Resolve,
    Retry,
    Rework,
    StartSession,
    StepDone,
    Stop,
    Unpark,
    WithdrawFromReview,
    WriteFix,
)
from github_orchestrator.conversation._domain.conversation import (
    ABSENT,
    ANSWER,
    ASSUMED_DONE,
    CONFIRMED,
    DECLINED,
    DEFERRED,
    DISCARDED,
    DRAFT,
    ENROLLED,
    FAILED,
    FILE,
    IN_SESSION,
    LANDED,
    LANDING,
    MARK_RESOLVED,
    MAX_ATTEMPTS,
    NOT_MINE,
    OPEN,
    PICK,
    PROPOSED,
    PUSH,
    QUEUED,
    REJECTED,
    REMOVED,
    RESOLVED,
    ROLE_AUTHOR,
    ROLE_REVIEWER,
    RUNNING,
    WAITING_ON_REVIEWER,
    WITHDRAWN,
    Anchor,
    Brief,
    Classification,
    Comment,
    ConfidenceLevel,
    Conversation,
    ConversationState,
    Fix,
    Operation,
    OperationKind,
    OperationState,
    ProposalKind,
    Run,
    Step,
    UnreadableRecord,
)
from github_orchestrator.conversation._domain.diff import (
    KIND_DRAFT,
    KIND_REVIEW,
    within_cutoff,
)
from github_orchestrator.conversation._domain.effects import (
    GIST_ROOT,
    GIST_THREAD,
    AskVerdict,
    CutWorkspace,
    DeleteComment,
    DropWorkspace,
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
    Posted,
    Pushed,
    PushFailed,
    ReactionFailed,
    ReactionPosted,
    Rebase,
    Refresh,
    Reopen,
    ReplyFailed,
    ReplyPosted,
    RootGone,
    RunExited,
    RunLost,
    RunStarted,
    RunTimedOut,
    SessionRefused,
    ThreadResolved,
    ThreadResolveFailed,
    ThreadUnresolved,
    ThreadUnresolveFailed,
    Unpicked,
    UnpickFailed,
    VerdictDue,
    VerdictGiven,
    Wake,
    WorkspaceCut,
)
from github_orchestrator.conversation._domain.gist import fallback_summary
from github_orchestrator.conversation._domain.machine import (
    IDLE_FIX,
    REWORK_ADVICE,
    Accepted,
    Deferred,
    Refused,
    prepared_to_land,
    refusal,
    ticket_to_file,
    with_fix,
)
from github_orchestrator.conversation._domain.operations import Asked
from github_orchestrator.conversation._domain.steps import First, Land
from github_orchestrator.conversation._domain.verdict import (
    PLACED_BY_A_VERDICT,
    STATE_OF_VERDICT,
    newest_said,
    unread_of,
    verdict_due,
    with_an_ask,
)
from github_orchestrator.domain import Location, Sha

PLACED_IN = {
    ConversationState.READY: OPEN,
    ConversationState.WAITING: WAITING_ON_REVIEWER,
    ConversationState.NOT_MINE: NOT_MINE,
}

ASSUMED_DONE_WHEN_DECLINED_AS = (Classification.ACKNOWLEDGEMENT,)

MANUAL_REBASE_ADVICE = f"; {REWORK_ADVICE} and rebase the thread there"

UNDER_WAY = (RUNNING, IN_SESSION, LANDING)

UNREPORTED = ("ended without reporting a filed ticket; look for it in the tracker before "
              "filing it again")

REOPENED_BY_A_REPLY = (WAITING_ON_REVIEWER, ASSUMED_DONE, NOT_MINE, CONFIRMED, REMOVED,
                       DEFERRED, REJECTED, RESOLVED)

FOLLOW_UP_NOTE = ("A new reply arrived on the thread while the last attempt "
                  "was being made. Change the attempt so it answers the "
                  "replies below as well.")

def create(
    *,
    key: str,
    github_node_id: str | None = None,
    comment_id: int | None = None,
    comment_type: str = "",
    author: str = "",
    path: str | None = None,
    line: int | None = None,
    body: str = "",
    comments: tuple[Comment, ...] = (),
    comment_created_at: str | None = None,
    created_at: str | None = None,
    anchor: Anchor = Anchor(),
    role: str = ROLE_AUTHOR,
    resolved: bool = False,
) -> Accepted:
    root = comments[0] if comments else Comment()
    conversation = Conversation(
        key=key,
        github_node_id=github_node_id,
        role=role,
        comment_id=comment_id,
        comment_type=comment_type,
        author=author,
        reviewer_name=root.author_name,
        review_state=root.review_state,
        path=path,
        line=line,
        start_line=anchor.start_line,
        start_side=anchor.start_side,
        side=anchor.side,
        body=body,
        comments=tuple(comments),
        comment_created_at=comment_created_at,
        created_at=created_at,
        gist=fallback_summary(body),
        is_outdated=anchor.is_outdated,
        original_line=anchor.original_line,
        original_start_line=anchor.original_start_line,
        original_commit=anchor.original_commit,
        fix=Fix(),
    )
    first = Operation(id=f"{key}.1", kind=OperationKind.FIRST, requested_at=created_at)
    if resolved:
        return Accepted(replace(conversation, state=RESOLVED,
                                fix=Fix(state=ABSENT), github_resolved=True))
    if role == ROLE_REVIEWER:
        return _read_and_asked(Accepted(replace(conversation, fix=Fix(state=ABSENT)),
                                        (WriteGist(source=GIST_ROOT),)), created_at)
    return Accepted(replace(conversation, operations=(first,)),
                    (CutWorkspace(), WriteGist(source=GIST_ROOT)))


def create_draft(*, key: str, body: str, anchor: Location, author: str,
                 role: str, at: str, operation: str) -> Conversation:
    """A comment of the viewer's own, before GitHub has anything for it.

    `operation` is the id the create is recorded under: the one the route
    handed the client, or the domain's own for a draft the board made.
    """
    return Conversation(
        key=key,
        state=DRAFT,
        role=role,
        comment_type=KIND_DRAFT,
        author=author,
        path=anchor.path,
        line=anchor.line,
        start_line=anchor.start_line,
        start_side=anchor.start_side,
        side=anchor.side,
        body=body,
        comments=(Comment(author=author, body=body),),
        created_at=at,
        state_changed_at=at,
        gist=fallback_summary(body),
        fix=Fix(state=ABSENT),
        operations=(Operation(id=operation, kind=OperationKind.CREATE_DRAFT, state=OperationState.APPLIED,
                              requested_at=at, settled_at=at, text=body,
                              anchor=anchor),),
    )


def _my_move(conversation: Conversation) -> Conversation:
    return replace(conversation, state=OPEN, verdict=None, verdict_for=None,
                   verdict_asked_for=None, verdict_asks=0, verdict_asked_at=None)


def _read_and_asked(outcome: Accepted, at: str | None) -> Accepted:
    conversation = replace(outcome.conversation, unread=unread_of(outcome.conversation))
    if not verdict_due(conversation, at):
        return Accepted(conversation, outcome.effects)
    return Accepted(with_an_ask(conversation, at), outcome.effects + (AskVerdict(),))


def _verdict_given(conversation: Conversation, command: VerdictGiven) -> Accepted:
    if conversation.role != ROLE_REVIEWER or command.on != newest_said(conversation):
        return Accepted(conversation)
    given = replace(conversation, verdict=command.verdict, verdict_for=command.on)
    if conversation.state not in PLACED_BY_A_VERDICT:
        return Accepted(given)
    return Accepted(replace(given, state=STATE_OF_VERDICT[command.verdict]))


def _decidable(conversation: Conversation, at: str | None) -> Conversation:
    return replace(conversation, decidable_at=at)


def _with_transcript(conversation: Conversation, comment: Comment | None,
                     posted_key: str | None) -> Conversation:
    return replace(
        conversation,
        comments=conversation.comments + ((comment,) if comment else ()),
        posted_comment_keys=(conversation.posted_comment_keys
                             + ((posted_key,) if posted_key else ())),
    )


def _anchor_of(conversation: Conversation) -> Anchor:
    return Anchor(
        is_outdated=conversation.is_outdated,
        start_line=conversation.start_line,
        start_side=conversation.start_side,
        original_line=conversation.original_line,
        original_start_line=conversation.original_start_line,
        original_commit=conversation.original_commit,
        side=conversation.side,
    )


def _posted_since(conversation: Conversation, command: Refresh | Reopen) -> tuple[Comment, ...]:
    listed = {comment.id for comment in command.comments}
    return tuple(comment for comment in conversation.comments
                 if comment.id not in listed and not within_cutoff(comment, command.as_of))


def _in_step(conversation: Conversation, command: Refresh | Reopen) -> Conversation:
    comments = tuple(command.comments) + _posted_since(conversation, command)
    root = comments[0] if comments else Comment()
    anchor = (_anchor_of(conversation) if command.anchor is None
              else command.anchor)
    return replace(
        conversation,
        comments=comments,
        body=root.body if comments else conversation.body,
        reviewer_name=root.author_name or conversation.reviewer_name,
        review_state=root.review_state or conversation.review_state,
        is_outdated=anchor.is_outdated,
        start_line=anchor.start_line,
        start_side=anchor.start_side,
        original_line=anchor.original_line,
        original_start_line=anchor.original_start_line,
        original_commit=anchor.original_commit,
        side=anchor.side,
    )


def _github_resolved(conversation: Conversation, resolved: bool | None,
                     as_of: str | None, at: str | None) -> Conversation:
    if resolved is None:
        return conversation
    if (as_of is not None and conversation.github_resolved_at is not None
            and as_of < conversation.github_resolved_at):
        return conversation
    told = replace(conversation, github_resolved=resolved,
                   github_resolved_at=at or conversation.github_resolved_at)
    if resolved == bool(conversation.github_resolved):
        return told
    if resolved:
        if conversation.state in PLACED_BY_A_VERDICT + (DEFERRED,):
            return replace(told, state=RESOLVED, wake_on=None)
        return told
    if conversation.state != RESOLVED:
        return told
    return _my_move(told)


def _refreshed(conversation: Conversation,
               command: Refresh) -> Conversation:
    return _github_resolved(_in_step(conversation, command), command.resolved,
                            command.as_of, command.as_of)


def _viewer_spoke(conversation: Conversation, viewer: str) -> bool:
    return bool(conversation.panel_reply_ids) or any(
        comment.author == viewer for comment in conversation.comments)


def _had_spoken(conversation: Conversation) -> bool:
    return bool(conversation.panel_reply_ids
                or conversation.approved_reply_id
                or conversation.closing_reply_id
                or conversation.fix.state in (LANDING, LANDED)
                or conversation.state == REJECTED)


def _reopen_as_reviewer(conversation: Conversation,
                        command: Reopen) -> Accepted:
    reopened = replace(_my_move(_in_step(conversation, command)),
                       wake_on=None, defer_note="",
                       reopened=_viewer_spoke(conversation, command.viewer))
    return Accepted(reopened, (WriteGist(source=GIST_THREAD),))


def _reopen(conversation: Conversation, command: Reopen) -> Accepted:
    outcome = _reopen_into(conversation, command)
    return Accepted(_github_resolved(outcome.conversation, command.resolved,
                                     command.as_of, command.as_of),
                    outcome.effects)


def _with_detail(outcome: str, detail: str | None) -> str:
    return f"{outcome}: {detail}" if detail else outcome


def _how_it_ended_up(conversation: Conversation) -> str:
    fix = conversation.fix
    if conversation.state in (REJECTED, RESOLVED):
        return _with_detail(conversation.state, conversation.closing_reply)
    if conversation.state == DEFERRED:
        return _with_detail(DEFERRED, conversation.defer_note)
    if fix.state == LANDED:
        return "pushed"
    if fix.state in (FAILED, DECLINED):
        return _with_detail(fix.state, fix.reason)
    return fix.state


def _reopen_into(conversation: Conversation, command: Reopen) -> Accepted:
    if conversation.state == DISCARDED:
        return Accepted(conversation)
    if conversation.role == ROLE_REVIEWER:
        return _reopen_as_reviewer(conversation, command)
    reopened = replace(
        _in_step(conversation, command),
        state=OPEN if conversation.state in REOPENED_BY_A_REPLY
        else conversation.state,
        wake_on=None, defer_note="",
        reopened=_had_spoken(conversation),
        before_reply=_how_it_ended_up(conversation),
        replied_during_run=(conversation.replied_during_run
                            or conversation.fix.state in UNDER_WAY))
    return Accepted(reopened, (WriteGist(source=GIST_THREAD),))


def _unfinished(conversation: Conversation) -> bool:
    fix = conversation.fix
    if fix.state == LANDING:
        return PUSH not in fix.steps
    return fix.state not in (RUNNING, LANDED)


def _root_gone(conversation: Conversation) -> Accepted:
    gone = replace(conversation, comment_deleted=True)
    if conversation.state == OPEN and _unfinished(conversation):
        gone = replace(gone, state=REMOVED)
    return Accepted(gone)


def _gist_written(conversation: Conversation, command: GistWritten) -> Accepted:
    return Accepted(replace(conversation, gist=command.gist))


def _declare_plan(conversation: Conversation, command: DeclarePlan) -> Accepted:
    return Accepted(with_fix(conversation,
                              plan=tuple(Step(text=text, file=file)
                                         for text, file in command.steps)))


def _step_done(conversation: Conversation, command: StepDone) -> Accepted:
    plan = conversation.fix.plan
    marked = set(command.indexes)
    return Accepted(with_fix(conversation, plan=tuple(
        replace(step, done=True) if number in marked else step
        for number, step in enumerate(plan, start=1))))


def _report_ready(conversation: Conversation, command: ReportReady,
                  at: str | None) -> Accepted:
    reported = Sha.parse(command.sha)
    return Accepted(with_fix(
        _decidable(conversation, at), state=PROPOSED, kind=ProposalKind.COMMIT, reply=None,
        ticket=None, classification=None, thread_sha=reported, tests=command.tests,
        tests_note=command.tests_note, agent_note=command.agent_note,
        summary=command.summary,
        confidence=(None if command.confidence is None
                    else ConfidenceLevel(command.confidence)),
        confidence_note=command.confidence_note,
        reason=None,
    ))


NO_COMMIT: dict[str, Any] = {
    "thread_sha": None, "tests": None, "tests_note": None, "agent_note": None,
    "summary": None, "confidence": None, "confidence_note": None, "reason": None,
}


def _report_reply(conversation: Conversation, command: ReportReply,
                  at: str | None) -> Accepted:
    return Accepted(with_fix(
        _decidable(conversation, at), state=PROPOSED, kind=ProposalKind.REPLY,
        reply=command.body, ticket=None, classification=command.classification,
        **NO_COMMIT))


def _report_ticket(conversation: Conversation, command: ReportTicket,
                   at: str | None) -> Accepted:
    return Accepted(with_fix(
        _decidable(conversation, at), state=PROPOSED, kind=ProposalKind.TICKET,
        reply=command.reply, ticket=command.ticket,
        classification=Classification.OUT_OF_SCOPE, **NO_COMMIT))


def _landed_by_a_decline(conversation: Conversation, classification: Classification) -> str:
    if conversation.state == OPEN and classification in ASSUMED_DONE_WHEN_DECLINED_AS:
        return ASSUMED_DONE
    return conversation.state


def _report_declined(conversation: Conversation, command: ReportDeclined,
                     at: str | None) -> Accepted:
    landed = replace(conversation, state=_landed_by_a_decline(conversation, command.classification))
    return Accepted(with_fix(_decidable(landed, at),
                              state=DECLINED,
                              classification=command.classification,
                              reason=command.reason,
                              plan=(), summary=None, confidence=None,
                              confidence_note=None))


def _run_started(conversation: Conversation, command: RunStarted) -> Accepted:
    fix = conversation.fix
    started = with_fix(conversation, state=RUNNING, started_at=command.at,
                        attempts=fix.attempts + 1)
    return Accepted(started, (StartRun(kind=fix.run.kind, onto=fix.run.onto),))


def _session_refused(conversation: Conversation,
                     command: SessionRefused) -> Accepted:
    return Accepted(with_fix(conversation, state=command.back_to,
                              decision_error=command.reason))


def _fail_or_retry(conversation: Conversation, reason: str, at: str | None,
                   effects: tuple[Any, ...] = ()) -> Accepted:
    if conversation.fix.attempts < MAX_ATTEMPTS:
        return Accepted(with_fix(conversation, state=QUEUED, reason=reason,
                                  started_at=None), effects)
    return Accepted(with_fix(_decidable(conversation, at), state=FAILED,
                              reason=reason), effects)


def _proposed_by_exit(conversation: Conversation, head: Sha, note: str,
                      at: str) -> Accepted:
    return Accepted(with_fix(_decidable(conversation, at), state=PROPOSED,
                              kind=ProposalKind.COMMIT, reply=None, ticket=None,
                              thread_sha=head, tests="unverified",
                              tests_note=note, reason=None))


def _run_exited(conversation: Conversation, command: RunExited) -> Accepted:
    fix = conversation.fix
    head = command.head
    if fix.run.is_rebase:
        if head is not None and head != fix.run.onto and command.descends:
            return _proposed_by_exit(
                conversation, head,
                "run exited without reporting; rebased commit found in worktree",
                command.at)
        return _fail_or_retry(conversation, "run exited without rebasing",
                              command.at)
    if head is not None and fix.base_sha and head != fix.base_sha:
        return _proposed_by_exit(
            conversation, head,
            "run exited without reporting; commit found in worktree",
            command.at)
    return _fail_or_retry(conversation, "run exited without reporting",
                          command.at)


def _filing_run_failed(conversation: Conversation) -> bool:
    fix = conversation.fix
    return fix.run.kind == OperationKind.FILE and bool(fix.file_error)


def _approve(conversation: Conversation, command: Approve) -> Accepted | Deferred:
    if _filing_run_failed(conversation):
        return Accepted(with_fix(conversation, run=Run()))
    prepared = prepared_to_land(conversation, command)
    if prepared.fix.kind == ProposalKind.TICKET and not prepared.fix.filed:
        return _file(prepared, command)
    return _land(prepared, command)


def _file(conversation: Conversation, command: Approve) -> Deferred:
    return Deferred(with_fix(conversation, state=QUEUED, run=Run(kind=OperationKind.FILE),
                             attempts=0, started_at=None, reason=None, decision_error=None,
                             ticket=ticket_to_file(conversation, command)),
                    "the approve waits for the ticket to be filed")


def _report_filed(conversation: Conversation, command: ReportFiled) -> Accepted:
    return Accepted(with_fix(conversation, state=LANDING, steps=conversation.fix.steps | {FILE},
                             ticket_key=command.key, ticket_url=command.url, started_at=None))


def _filing_failed(conversation: Conversation, reason: str, at: str | None,
                   effects: tuple[Any, ...] = ()) -> Accepted:
    return Accepted(with_fix(_decidable(conversation, at), state=LANDING, file_error=reason,
                             started_at=None), effects)


def _filing_ended(conversation: Conversation, command: Fail | RunExited | RunTimedOut | RunLost,
                  at: str | None) -> Accepted:
    match command:
        case Fail():
            return _filing_failed(conversation, command.reason, at)
        case RunTimedOut():
            return _filing_failed(conversation, command.reason, command.at, (StopRun(),))
        case RunExited():
            return _filing_failed(conversation, f"the filing run {UNREPORTED}", command.at)
        case RunLost():
            return _filing_failed(conversation, f"the board lost the filing run, which {UNREPORTED}",
                                  at)


def _lands_a_commit(fix: Fix) -> bool:
    return fix.kind == ProposalKind.COMMIT


def _land(conversation: Conversation, command: Approve) -> Accepted:
    fix = conversation.fix
    if _lands_a_commit(fix) and PICK not in fix.steps:
        return Accepted(conversation, (Pick(message=command.message),))
    if _lands_a_commit(fix) and PUSH not in fix.steps:
        return Accepted(conversation, (Push(),))
    if command.delete_comment and not conversation.comment_deleted:
        return Accepted(conversation, (DeleteComment(),))
    if ANSWER not in fix.steps:
        return _answer(conversation, command)
    return _after_the_answer(conversation)


def _after_the_answer(conversation: Conversation) -> Accepted:
    fix = conversation.fix
    if fix.resolve_on_land and MARK_RESOLVED not in fix.steps:
        return Accepted(conversation, (ResolveThread(),))
    return Accepted(with_fix(conversation, state=LANDED), (DropWorkspace(),))


def _answered(conversation: Conversation, **fields: Any) -> Accepted:
    answered = with_fix(conversation, steps=conversation.fix.steps | {ANSWER},
                         reply_error=None, pending_reply="", **fields)
    if _lands_a_commit(answered.fix) and PUSH not in answered.fix.steps:
        return Accepted(answered)
    return _after_the_answer(answered)


def _resolved_on_landing(conversation: Conversation,
                         command: ThreadResolved) -> Accepted:
    told = _github_resolved(conversation, True, None, command.at)
    return Accepted(with_fix(replace(told, state=RESOLVED, wake_on=None),
                              state=LANDED, reply_error=None,
                              steps=told.fix.steps | {MARK_RESOLVED}),
                    (DropWorkspace(),))


def _answer(conversation: Conversation, command: Approve) -> Accepted:
    if conversation.comment_deleted:
        if command.delete_comment:
            return _answered(conversation)
        return _answered(conversation,
                         reply_note="no reply: the comment was deleted")
    return Accepted(
        conversation,
        (PostReply(body=_with_the_ticket(conversation.fix, command.reply),
                   commit=conversation.fix.landed_sha),),
    )


def _with_the_ticket(fix: Fix, reply: str) -> str:
    if fix.ticket_url is None:
        return reply
    return f"{reply}\n\n{fix.ticket_url}" if reply else fix.ticket_url


def _answer_posted(conversation: Conversation, command: AnswerPosted) -> Accepted:
    answered = _answered(_with_transcript(conversation, command.comment,
                                          command.posted_key))
    if not command.reply:
        return answered
    return Accepted(
        replace(answered.conversation, approved_reply=command.reply,
                approved_reply_id=(command.comment.id if command.comment
                                   else None)),
        answered.effects)


def _picked(conversation: Conversation, command: Picked) -> Accepted:
    return Accepted(with_fix(
        conversation, state=LANDING, steps=conversation.fix.steps | {PICK},
        landed_base=command.landed_base, landed_sha=command.landed_sha,
        reason=None, decision_error=None, run=Run(kind=OperationKind.FIRST),
    ))


def _handed_back(conversation: Conversation, reason: str,
                 **fields: Any) -> Accepted:
    return Accepted(with_fix(conversation, state=PROPOSED, reason=reason,
                              **fields))


def _pick_conflicted(conversation: Conversation, command: PickConflicted) -> Accepted | Deferred:
    if conversation.fix.run.onto == command.head:
        return _handed_back(
            conversation,
            f"the rebased fix still conflicts with {str(command.head)[:12]} — "
            f"{command.diagnostic}{MANUAL_REBASE_ADVICE}",
            run=Run(kind=OperationKind.FIRST),
        )
    if not command.rebases_allowed or conversation.state == REMOVED:
        return _handed_back(conversation,
                            command.conflict + MANUAL_REBASE_ADVICE)
    return Deferred(_rebased(conversation, command.head, command.conflict),
                    "the approve waits for the rebase")


def _rebased(conversation: Conversation, onto: Sha,
             conflict: str | None) -> Conversation:
    return with_fix(conversation, state=QUEUED, attempts=0, started_at=None,
                     run=Run(kind=OperationKind.REBASE, onto=onto, conflict=conflict),
                     base_sha=onto, thread_sha=None, tests=None,
                     tests_note=None, agent_note=None, reason=None,
                     decision_error=None)


def _rebase(conversation: Conversation, command: Rebase) -> Accepted:
    return Accepted(_rebased(conversation, command.onto, command.conflict))


def _decision_failed(conversation: Conversation, reason: str) -> Accepted:
    return Accepted(with_fix(conversation, decision_error=reason))


def _first(conversation: Conversation) -> Accepted:
    return Accepted(
        with_fix(conversation, state=QUEUED, run=Run(kind=OperationKind.FIRST), attempts=0,
                  started_at=None, steps=frozenset(), landed_base=None,
                  landed_sha=None, push_error=None, reply_error=None,
                  decision_error=None, reply_note=None, pending_reply=""),
        (CutWorkspace(),))


def _start_session(conversation: Conversation, command: StartSession) -> Accepted:
    fix = conversation.fix
    brief = (Brief(note=command.steer, pointed=command.pointed, include=command.include)
             if command.pointed or command.include else fix.run.brief)
    return Accepted(
        with_fix(conversation, state=IN_SESSION, decision_error=None),
        (CutWorkspace(), OpenSession(back_to=fix.state, steer=command.steer,
                                     skipped=fix.state == DECLINED, brief=brief)),
    )


def _rework(conversation: Conversation, command: Rework) -> Accepted:
    brief = Brief(note=command.note, pointed=command.pointed,
                  include=command.include)
    return Accepted(
        with_fix(conversation, state=QUEUED, attempts=0, started_at=None,
                  plan=(), decision_error=None,
                  run=Run(kind=OperationKind.REWORK, brief=brief)),
        (CutWorkspace(),),
    )


def _retry(conversation: Conversation) -> Accepted:
    return Accepted(with_fix(conversation, state=QUEUED, attempts=0,
                              started_at=None, decision_error=None))


def _landing_withdrawn(conversation: Conversation, reason: str = WITHDRAWN) -> Accepted:
    return Accepted(with_fix(conversation, state=PROPOSED, reason=reason, steps=frozenset(),
                             landed_base=None, landed_sha=None, push_error=None,
                             reply_error=None, file_error=None, decision_error=None,
                             pending_reply=""))


def _left_on_the_branch(conversation: Conversation, command: UnpickFailed) -> str:
    return (f"{WITHDRAWN}, but {str(conversation.fix.landed_sha)[:12]} is still on the PR "
            f"branch, unpushed, because {command.error}; take it off by hand before "
            f"approving again")


def _stop(conversation: Conversation) -> Accepted:
    if conversation.fix.state == LANDING and conversation.fix.picked:
        return Accepted(conversation, (Unpick(),))
    if conversation.fix.state == LANDING:
        return _landing_withdrawn(conversation)
    return Accepted(
        with_fix(replace(conversation, replied_during_run=False),
                  state=FAILED, reason=WITHDRAWN, decision_error=None),
        (StopRun(),))


def _resolves_on_github(conversation: Conversation) -> bool:
    return (conversation.closing_on_github and not conversation.comment_deleted
            and conversation.comment_type == KIND_REVIEW)


def _unresolves_on_github(conversation: Conversation) -> bool:
    return (conversation.role == ROLE_REVIEWER and conversation.github_resolved is True
            and conversation.comment_type == KIND_REVIEW)


def _newest_other_comment(conversation: Conversation) -> int | None:
    for comment in reversed(conversation.comments):
        if comment.author != conversation.author and comment.id is not None:
            return comment.id
    return None


def _thread_resolved(conversation: Conversation,
                     command: ThreadResolved) -> Accepted:
    told = _github_resolved(conversation, True, None, command.at)
    settled = _settled(told)
    if (told.closing_reply or told.closing_without_thumbs_up
            or told.role != ROLE_REVIEWER):
        return settled
    comment_id = _newest_other_comment(told)
    if comment_id is None:
        return settled
    return Accepted(settled.conversation,
                    (React(comment_id=comment_id),) + settled.effects)


def _thread_unresolved(conversation: Conversation,
                       command: ThreadUnresolved) -> Accepted:
    told = _github_resolved(conversation, False, None, command.at)
    back = replace(_my_move(told), wake_on=None, defer_note="",
                   decidable_at=command.at)
    return Accepted(with_fix(back, decision_error=None))


def _settled(conversation: Conversation, state: str = RESOLVED,
             **fields: Any) -> Accepted:
    settled = replace(conversation, state=state, closing_into=None,
                      closing_on_github=False,
                      closing_without_thumbs_up=False, **fields)
    return Accepted(with_fix(settled, decision_error=None),
                    (DropWorkspace(),))


def _closing(conversation: Conversation, command: Resolve) -> Accepted:
    conversation = replace(conversation, closing_on_github=command.resolve,
                           closing_without_thumbs_up=not command.thumbs_up)
    if command.delete_comment:
        if not conversation.comment_deleted:
            return Accepted(conversation, (DeleteComment(),))
        return _settled(conversation)
    if not command.reply:
        if _resolves_on_github(conversation):
            return Accepted(conversation, (ResolveThread(),))
        return _settled(conversation)
    return Accepted(conversation, (PostReply(body=command.reply),))


def _reject(conversation: Conversation, command: Reject) -> Accepted:
    if command.delete_comment and not conversation.comment_deleted:
        return Accepted(replace(conversation, closing_into=REJECTED),
                        (DeleteComment(),))
    if command.reply:
        return Accepted(replace(conversation, closing_into=REJECTED),
                        (PostReply(body=command.reply),))
    return _settled(conversation, REJECTED)


def _defer(conversation: Conversation, command: Defer) -> Accepted:
    fix = conversation.fix
    parked = replace(conversation, state=DEFERRED, wake_on=command.wake_on,
                     defer_note=command.note)
    effects = (StopRun(),) if fix.state == RUNNING else ()
    return Accepted(with_fix(parked, decision_error=None), effects)


def _wake(conversation: Conversation, command: Wake) -> Accepted:
    woken = replace(_my_move(conversation), wake_on=None, defer_note="",
                    decidable_at=command.at)
    return Accepted(with_fix(woken,
                              reply_note=f"woken: {command.reason}"))


def _unpark(conversation: Conversation, at: str | None) -> Accepted:
    landed = conversation.state == OPEN and conversation.fix.state == LANDED
    if conversation.state == RESOLVED and _unresolves_on_github(conversation):
        return Accepted(conversation, (UnresolveThread(),))
    if conversation.state == DISCARDED:
        return Accepted(replace(conversation, state=DRAFT,
                                decidable_at=at))
    back = replace(_my_move(conversation), wake_on=None, defer_note="",
                   decidable_at=at)
    if conversation.state != REJECTED and not landed:
        return Accepted(back)
    requeued = with_fix(back, state=QUEUED, attempts=0, started_at=None,
                         steps=frozenset(), thread_sha=None, base_sha=None,
                         landed_base=None, landed_sha=None, push_error=None,
                         reply_error=None, decision_error=None,
                         reply_note=None)
    return Accepted(requeued, (CutWorkspace(), WriteGist(source=GIST_THREAD)))


def _closing_reply_posted(conversation: Conversation,
                          command: ClosingReplyPosted) -> Accepted:
    replied = _with_transcript(conversation, command.comment,
                               command.posted_key)
    reply_id = command.comment.id if command.comment else None
    if conversation.closing_into is None and _resolves_on_github(conversation):
        return Accepted(replace(replied, closing_reply=command.reply,
                                closing_reply_id=reply_id),
                        (ResolveThread(),))
    return _settled(replied, conversation.closing_into or RESOLVED,
                    closing_reply=command.reply, closing_reply_id=reply_id)


def _reply_posted(conversation: Conversation, command: ReplyPosted) -> Accepted:
    replied = _with_transcript(conversation, command.comment,
                               command.posted_key)
    if command.comment is not None and command.comment.id is not None:
        replied = replace(
            replied,
            panel_reply_ids=replied.panel_reply_ids + (command.comment.id,))
    if conversation.state in (DEFERRED, ASSUMED_DONE, NOT_MINE) or (
            command.parks and conversation.state == OPEN):
        replied = replace(replied, state=WAITING_ON_REVIEWER, wake_on=None,
                          defer_note="")
    return Accepted(with_fix(replied, reply_error=None))


def _edited(conversation: Conversation, command: EditDraft) -> Conversation:
    anchor = command.anchor
    return replace(conversation, body=command.body,
                   comments=(replace(conversation.comments[0],
                                     body=command.body),),
                   path=anchor.path, line=anchor.line,
                   start_line=anchor.start_line, start_side=anchor.start_side,
                   side=anchor.side, gist=fallback_summary(command.body))


def _draft_posted(conversation: Conversation,
                  command: DraftPosted | Posted) -> Accepted:
    comment = command.comment
    return Accepted(replace(
        conversation, comment_type=KIND_REVIEW,
        github_node_id=command.github_node_id, state=WAITING_ON_REVIEWER,
        comment_id=comment.id, comments=(comment,),
        comment_created_at=comment.created_at,
        panel_reply_ids=(conversation.panel_reply_ids
                         + ((comment.id,) if comment.id is not None else ()))))


CLEARS_THE_REOPENED_MARK = (Approve, Rework, StartSession, Retry, WriteFix, Resolve,
                            Reject, Defer, ReplyPosted, Unpark, Confirm, Place)


def _repliers(conversation: Conversation) -> tuple[str, ...]:
    return tuple(dict.fromkeys(comment.author
                               for comment in conversation.comments[1:]))


def _follow_up(conversation: Conversation) -> Conversation:
    if conversation.fix.state == LANDED:
        return _first(conversation).conversation
    brief = Brief(note=FOLLOW_UP_NOTE, include=_repliers(conversation))
    return with_fix(conversation, state=QUEUED, attempts=0, started_at=None,
                     plan=(), run=Run(kind=OperationKind.REWORK, brief=brief))


def _followed_up(outcome: Accepted) -> Accepted:
    conversation = outcome.conversation
    if not (conversation.replied_during_run and conversation.state == OPEN
            and conversation.fix.state in IDLE_FIX + (LANDED,)):
        return outcome
    return Accepted(replace(_follow_up(conversation),
                            replied_during_run=False),
                    outcome.effects + (CutWorkspace(),))


def _moved(before: Conversation, after: Conversation) -> bool:
    try:
        return before.standing != after.standing
    except UnreadableRecord:
        return False


def apply(conversation: Conversation, command: Change, at: str | None = None,
          asked: Asked | None = None) -> Accepted | Refused | Deferred:
    """`at` is the board's clock and `asked` the id a client asked with.

    Without `at` the thread moves unstamped and its operations settle with
    no time on them; only a dry run that throws the answer away should leave
    it out.
    """
    outcome = (refusal(conversation, command, asked)
               or _dispatch(conversation, command, at))
    if isinstance(outcome, Refused):
        return replace(outcome, conversation=history.refused(
            conversation, outcome.conversation, command, outcome.reason,
            asked, at))
    if isinstance(outcome, Deferred):
        return replace(outcome, conversation=history.deferred(
            conversation, outcome.conversation, command, asked, at))
    followed = _read_and_asked(_followed_up(outcome), at)
    settled = followed.conversation
    if isinstance(command, CLEARS_THE_REOPENED_MARK):
        settled = replace(settled, reopened=False)
    if at is not None and _moved(conversation, settled):
        settled = replace(settled, state_changed_at=at)
    return Accepted(history.accepted(conversation, settled, command,
                                     followed.effects, asked, at),
                    followed.effects)


def _dispatch(conversation: Conversation, command: Change,
              at: str | None) -> Accepted | Deferred:
    match command:
        case Refresh():
            return Accepted(_refreshed(conversation, command))
        case Reopen():
            return _reopen(conversation, command)
        case RootGone():
            return _root_gone(conversation)
        case GistWritten():
            return _gist_written(conversation, command)
        case VerdictGiven():
            return _verdict_given(conversation, command)
        case VerdictDue():
            return Accepted(conversation)
        case WorkspaceCut():
            return Accepted(with_fix(conversation, base_sha=command.base_sha))
        case DeclarePlan():
            return _declare_plan(conversation, command)
        case StepDone():
            return _step_done(conversation, command)
        case ReportReady():
            return _report_ready(conversation, command, at)
        case MoveBase():
            return Accepted(with_fix(conversation, base_sha=Sha.parse(command.sha)))
        case ReportDeclined():
            return _report_declined(conversation, command, at)
        case ReportReply():
            return _report_reply(conversation, command, at)
        case ReportTicket():
            return _report_ticket(conversation, command, at)
        case ReportFiled():
            return _report_filed(conversation, command)
        case Fail() | RunExited() | RunTimedOut() | RunLost() if (
                conversation.fix.run.kind == OperationKind.FILE):
            return _filing_ended(conversation, command, at)
        case Fail():
            return _fail_or_retry(conversation, command.reason, at)
        case SessionRefused():
            return _session_refused(conversation, command)
        case RunStarted():
            return _run_started(conversation, command)
        case RunExited():
            return _run_exited(conversation, command)
        case RunTimedOut():
            return _fail_or_retry(conversation, command.reason, command.at,
                                  (StopRun(),))
        case RunLost():
            return Accepted(with_fix(conversation, state=QUEUED, started_at=None))
        case Land():
            return _land(conversation, command)
        case Approve():
            return _approve(conversation, command)
        case First():
            return _first(conversation)
        case Rebase():
            return _rebase(conversation, command)
        case Picked():
            return _picked(conversation, command)
        case PickRefused():
            return _handed_back(conversation, command.reason)
        case PickConflicted():
            return _pick_conflicted(conversation, command)
        case Pushed():
            return Accepted(with_fix(conversation,
                                      steps=conversation.fix.steps | {PUSH},
                                      push_error=None))
        case Unpicked():
            return _landing_withdrawn(conversation)
        case UnpickFailed():
            return _landing_withdrawn(conversation, _left_on_the_branch(conversation, command))
        case PushFailed():
            return Accepted(
                _decidable(with_fix(conversation, push_error=command.error),
                           command.at))
        case AnswerPosted():
            return _answer_posted(conversation, command)
        case AnswerDeleted():
            return _answered(replace(conversation, comment_deleted=True,
                                     deleted_by_board=True))
        case AnswerFailed():
            return Accepted(
                _decidable(with_fix(conversation, reply_error=command.error),
                           command.at))
        case Rework():
            return _rework(conversation, command)
        case StartSession():
            return _start_session(conversation, command)
        case Retry():
            return _retry(conversation)
        case WriteFix():
            return _first(replace(conversation, state=OPEN, wake_on=None,
                                  defer_note=""))
        case Stop():
            return _stop(conversation)
        case Resolve():
            return _closing(conversation, command)
        case Reject():
            return _reject(conversation, command)
        case Defer():
            return _defer(conversation, command)
        case Wake():
            return _wake(conversation, command)
        case Unpark():
            return _unpark(conversation, at)
        case Confirm():
            return Accepted(replace(conversation, state=CONFIRMED))
        case Place(to=ConversationState.QUEUED):
            return _first(replace(conversation, state=OPEN))
        case Place():
            return Accepted(replace(conversation, state=PLACED_IN[command.to]))
        case ClosingReplyPosted():
            return _closing_reply_posted(conversation, command)
        case ClosingCommentDeleted():
            return _settled(conversation, conversation.closing_into or RESOLVED,
                            comment_deleted=True, deleted_by_board=True)
        case ClosingFailed():
            verb = "delete" if command.deleting else "reply"
            return _decision_failed(replace(conversation, closing_into=None),
                                    f"{verb} failed: {command.error}")
        case ThreadResolved():
            if conversation.fix.state == LANDING:
                return _resolved_on_landing(conversation, command)
            return _thread_resolved(conversation, command)
        case ThreadResolveFailed():
            if conversation.fix.state == LANDING:
                return Accepted(with_fix(
                    conversation, reply_error=f"resolve failed: {command.error}"))
            return _decision_failed(conversation,
                                    f"resolve failed: {command.error}")
        case ThreadUnresolved():
            return _thread_unresolved(conversation, command)
        case ThreadUnresolveFailed():
            return _decision_failed(conversation,
                                    f"reopen failed: {command.error}")
        case ReactionPosted():
            return Accepted(conversation)
        case ReactionFailed():
            return Accepted(with_fix(
                conversation, reply_note=f"thumbs-up failed: {command.error}"))
        case EditDraft():
            return Accepted(_edited(conversation, command))
        case Enrol():
            return Accepted(replace(conversation, state=ENROLLED))
        case WithdrawFromReview():
            return Accepted(replace(conversation, state=DRAFT))
        case Discard():
            return Accepted(replace(conversation, state=DISCARDED))
        case PostNow():
            return Accepted(conversation, (PostDraft(),))
        case DraftPosted():
            return _draft_posted(conversation, command)
        case DraftPostFailed():
            return Accepted(conversation)
        case Posted():
            return _draft_posted(conversation, command)
        case Reply():
            return Accepted(conversation, (PostReply(body=command.text),))
        case ReplyPosted():
            return _reply_posted(conversation, command)
        case ReplyFailed():
            return Accepted(with_fix(conversation, reply_error=command.error))
    raise NotImplementedError(type(command).__name__)
