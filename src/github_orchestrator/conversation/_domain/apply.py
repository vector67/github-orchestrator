from dataclasses import replace
from typing import Any

from github_orchestrator.conversation._domain import operations as history
from github_orchestrator.conversation._domain.change import Change
from github_orchestrator.conversation._domain.commands import (
    Approve,
    CheckForFixes,
    Confirm,
    DeclarePlan,
    Defer,
    Discard,
    DropQuestion,
    EditDraft,
    EditPart,
    Enrol,
    Fail,
    MoveBase,
    OpenShell,
    Place,
    PostNow,
    Reject,
    Reply,
    ReportAsk,
    ReportDeclined,
    ReportFiled,
    ReportOpened,
    ReportReady,
    ReportReconciled,
    ReportReply,
    ReportSplit,
    ReportTicket,
    Resolve,
    Retry,
    Rework,
    SessionGone,
    SetCommitVerdict,
    StartSession,
    StepDone,
    Stop,
    Unpark,
    WithdrawFromReview,
    WriteFix,
)
from github_orchestrator.conversation._domain.commit_check import (
    checked,
    commit_reference,
    not_checked_again,
    placed_by_check,
    set_by_hand,
    with_a_check_ask,
)
from github_orchestrator.conversation._domain.conversation import (
    ABSENT,
    ASKING,
    ASSUMED_DONE,
    CONFIRMED,
    DECLINED,
    DEFERRED,
    DISCARDED,
    DRAFT,
    ENROLLED,
    FAILED,
    IN_SESSION,
    LANDED,
    LANDING,
    MAX_ATTEMPTS,
    NOT_MINE,
    OPEN,
    PART_RUNS,
    PROPOSED,
    QUEUED,
    REJECTED,
    REMOVED,
    RESOLVED,
    ROLE_AUTHOR,
    ROLE_REVIEWER,
    RUNNING,
    SESSION_GONE,
    THUMBS_UP,
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
    reacted,
)
from github_orchestrator.conversation._domain.diff import (
    KIND_DRAFT,
    KIND_REQUEST,
    KIND_REVIEW,
    within_cutoff,
)
from github_orchestrator.conversation._domain.effects import (
    GIST_ROOT,
    GIST_THREAD,
    AskCommitCheck,
    AskFixCheck,
    AskVerdict,
    CutWorkspace,
    DeleteComment,
    DropWorkspace,
    MatchDraft,
    OpenLoginShell,
    OpenSession,
    Pick,
    PostDraft,
    PostReply,
    Push,
    React,
    ResetWorkspace,
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
    CheckoutDiverged,
    ClosingCommentDeleted,
    ClosingFailed,
    ClosingReplyPosted,
    CommitCheckDue,
    CommitChecked,
    DraftMatched,
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
    ShellRefused,
    TakenOver,
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
    reports_only_a_split,
    ticket_to_file,
    with_fix,
)
from github_orchestrator.conversation._domain.operations import Asked, joins
from github_orchestrator.conversation._domain.parts import (
    ANSWER,
    FILE,
    MARK_RESOLVED,
    MATCH_DRAFT,
    PICK,
    PUSH,
    Split,
    SplitPart,
    accepting,
    dropped,
    has_run,
    next_part,
    parts,
    reported,
    taken_from_a_report,
)
from github_orchestrator.conversation._domain.parts import (
    OPEN as OPEN_PR,
)
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

FILING_UNREPORTED = ("ended without reporting a filed ticket; look for it in the tracker before "
                     "filing it again")

REOPENED_BY_A_REPLY = (WAITING_ON_REVIEWER, ASSUMED_DONE, NOT_MINE, CONFIRMED, REMOVED,
                       DEFERRED, REJECTED, RESOLVED)

REPLIED_WHILE_ASKING = ("A new reply arrived on the thread while you waited for the "
                        "author to answer your question.")

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
    fixes_allowed: bool = True,
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
    if not fixes_allowed:
        return Accepted(replace(conversation, fix=Fix(state=ABSENT)),
                        (WriteGist(source=GIST_ROOT),))
    return Accepted(replace(conversation, operations=(first,)),
                    (WriteGist(source=GIST_ROOT),))


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


def _taken_over(conversation: Conversation) -> Conversation:
    taken = replace(conversation, role=ROLE_AUTHOR)
    return _my_move(taken) if conversation.state in PLACED_BY_A_VERDICT else taken


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
    placed = placed_by_check(given) or STATE_OF_VERDICT[command.verdict]
    return Accepted(replace(given, state=placed))


def _commit_check_due(conversation: Conversation, command: CommitCheckDue,
                      at: str | None) -> Accepted:
    reference = commit_reference(conversation, command.viewer)
    if reference is None:
        return Accepted(conversation)
    return Accepted(with_a_check_ask(conversation, reference.on, at),
                    (AskCommitCheck(on=reference.on, candidates=reference.candidates),))


def _check_for_fixes(conversation: Conversation, command: CheckForFixes,
                     at: str | None) -> Accepted:
    on = newest_said(conversation)
    base = Sha.parse(conversation.original_commit or "")
    if on is None or base is None or not_checked_again(conversation, command.head, at):
        return Accepted(conversation)
    return Accepted(with_a_check_ask(conversation, on, at),
                    (AskFixCheck(on=on, base=base, head=command.head),))


def _set_commit_verdict(conversation: Conversation, command: SetCommitVerdict) -> Accepted:
    check = conversation.commit_check
    if check is None:
        return Accepted(conversation)
    return Accepted(set_by_hand(conversation, check, command.verdict, command.reason))


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
        line=conversation.line,
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
        line=anchor.line,
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
        ticket=None, split=None, classification=None, question=None, thread_sha=reported, tests=command.tests,
        tests_note=command.tests_note, agent_note=command.agent_note,
        summary=command.summary,
        confidence=(None if command.confidence is None
                    else ConfidenceLevel(command.confidence)),
        confidence_note=command.confidence_note,
        reason=None,
    ))


NO_COMMIT: dict[str, Any] = {
    "question": None, "thread_sha": None, "tests": None, "tests_note": None, "agent_note": None,
    "summary": None, "confidence": None, "confidence_note": None, "reason": None,
    "split": None,
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


def _report_split(conversation: Conversation, command: ReportSplit,
                  at: str | None) -> Accepted:
    fix = conversation.fix
    held = fix.split if fix.kind == ProposalKind.SPLIT else None
    reworked = None if fix.run.brief is None else fix.run.brief.part
    taken = (frozenset(SplitPart) if held is None
             else taken_from_a_report(fix.steps, reworked))
    return Accepted(with_fix(
        _decidable(conversation, at), state=PROPOSED, kind=ProposalKind.SPLIT,
        classification=None,
        **(NO_COMMIT | {
            "split": command.split if held is None else reported(held, command.split, taken),
            "thread_sha": Sha.parse(command.sha) if SplitPart.CHANGES in taken else fix.thread_sha,
            "reply": command.reply if SplitPart.REPLY in taken else fix.reply,
            "ticket": None if held is None else fix.ticket})))


def _split_rework_ended(conversation: Conversation, command: Fail | RunExited | RunTimedOut,
                        at: str | None) -> Accepted:
    effects: tuple[Any, ...]
    match command:
        case Fail():
            reason, effects, when = command.reason, (), at
        case RunTimedOut():
            reason, effects, when = command.reason, (StopRun(),), command.at
        case RunExited():
            reason = _with_detail("the rework ended without reporting a split", command.last_words)
            effects, when = (), command.at
    return Accepted(with_fix(_decidable(conversation, when), state=PROPOSED, reason=reason,
                             started_at=None), effects)


def _report_ask(conversation: Conversation, command: ReportAsk, at: str | None) -> Accepted:
    fix = conversation.fix
    return Accepted(with_fix(_decidable(conversation, at), state=ASKING,
                             question=command.question, session_from=None,
                             attempts=max(fix.attempts - 1, 0), started_at=None))


def _landed_by_a_decline(conversation: Conversation, classification: Classification) -> str:
    if conversation.state == OPEN and classification in ASSUMED_DONE_WHEN_DECLINED_AS:
        return ASSUMED_DONE
    return conversation.state


def _report_declined(conversation: Conversation, command: ReportDeclined,
                     at: str | None) -> Accepted:
    landed = replace(conversation, state=_landed_by_a_decline(conversation, command.classification))
    return Accepted(with_fix(_decidable(landed, at),
                              state=DECLINED, question=None,
                              classification=command.classification,
                              reason=command.reason,
                              plan=(), summary=None, confidence=None,
                              confidence_note=None))


def _run_started(conversation: Conversation, command: RunStarted) -> Accepted:
    fix = conversation.fix
    started = with_fix(conversation, state=RUNNING, started_at=command.at,
                        attempts=fix.attempts + 1, last_words=None)
    return Accepted(started, (StartRun(kind=fix.run.kind, onto=fix.run.onto),))


def _session_refused(conversation: Conversation,
                     command: SessionRefused) -> Accepted:
    return Accepted(with_fix(conversation, state=command.back_to,
                              decision_error=command.reason))


def _session_gone(conversation: Conversation) -> Accepted:
    fix = conversation.fix
    if fix.session_from is not None:
        back = with_fix(conversation, state=fix.session_from)
    elif fix.commits:
        back = with_fix(conversation, state=PROPOSED)
    else:
        back = with_fix(conversation, state=FAILED, reason=SESSION_GONE)
    return Accepted(with_fix(back, session_from=None, decision_error=SESSION_GONE))


def _fail_or_retry(conversation: Conversation, reason: str, at: str | None,
                   effects: tuple[Any, ...] = ()) -> Accepted:
    if conversation.fix.attempts < MAX_ATTEMPTS:
        return Accepted(with_fix(conversation, state=QUEUED, reason=reason,
                                  started_at=None), effects)
    return Accepted(with_fix(_decidable(conversation, at), state=FAILED,
                              reason=reason), effects)


def _proposed_by_exit(conversation: Conversation, head: Sha, note: str,
                      command: RunExited) -> Accepted:
    return Accepted(with_fix(_decidable(conversation, command.at), state=PROPOSED,
                              kind=ProposalKind.COMMIT, reply=None, ticket=None,
                              split=None, thread_sha=head, tests="unverified",
                              tests_note=note, reason=None, last_words=command.last_words))


def _carried_on_with_the_reply(conversation: Conversation) -> Accepted:
    brief = Brief(note=REPLIED_WHILE_ASKING, include=_repliers(conversation))
    return Accepted(with_fix(conversation, state=QUEUED, started_at=None, decision_error=None,
                             run=Run(kind=OperationKind.REWORK, brief=brief, resumes=True)))


def _still_asking(conversation: Conversation) -> Accepted:
    fix = conversation.fix
    return Accepted(with_fix(conversation, state=ASKING, started_at=None,
                             attempts=max(fix.attempts - 1, 0)))


def _run_exited(conversation: Conversation, command: RunExited) -> Accepted:
    fix = conversation.fix
    head = command.head
    if fix.run.resumes and fix.question is not None:
        return _still_asking(conversation)
    if fix.run.is_rebase:
        if head is not None and head != fix.run.onto and command.descends:
            return _proposed_by_exit(
                conversation, head,
                "run exited without reporting; rebased commit found in worktree",
                command)
        return _fail_or_retry(conversation,
                              _with_detail("run exited without rebasing", command.last_words),
                              command.at)
    if head is not None and fix.base_sha and head != fix.base_sha:
        return _proposed_by_exit(
            conversation, head,
            "run exited without reporting; commit found in worktree",
            command)
    return _fail_or_retry(conversation,
                          _with_detail("run exited without reporting", command.last_words),
                          command.at)


def _filing_run_failed(conversation: Conversation) -> bool:
    fix = conversation.fix
    return fix.run.kind == OperationKind.FILE and bool(fix.file_error)


_PART_RUN_BY = {OperationKind.FILE: SplitPart.TICKET, OperationKind.OPEN: SplitPart.NEW_PR}

_RUN_NAMED = {OperationKind.FILE: "the filing run", OperationKind.OPEN: "the run opening the new PR"}


def _part_run_failed(fix: Fix) -> bool:
    return fix.state == LANDING and fix.run.kind in PART_RUNS and bool(fix.file_error)


def _approve(conversation: Conversation, command: Approve) -> Accepted | Deferred:
    fix = conversation.fix
    split = fix.kind == ProposalKind.SPLIT
    if split and _part_run_failed(fix):
        return Accepted(_part_failed(conversation, _PART_RUN_BY[fix.run.kind]))
    if split:
        return _accept_parts(conversation, command)
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


def _the_split(fix: Fix) -> Split:
    if fix.split is None:
        raise ValueError("a split proposal holds no split")
    return fix.split


def _accept_parts(conversation: Conversation, command: Approve) -> Accepted | Deferred:
    fix = conversation.fix
    split = _the_split(fix)
    accepted = with_fix(conversation, split=accepting(split, command.part),
                        resolve_on_land=fix.resolve_on_land or command.resolve)
    if joins(conversation, command):
        return Accepted(accepted)
    return _run_next_part(with_fix(accepted, reason=None, decision_error=None,
                                   file_error=None, push_error=None, reply_error=None),
                          command)


def _run_next_part(conversation: Conversation, command: Approve) -> Accepted | Deferred:
    fix = conversation.fix
    split = _the_split(fix)
    if (command.draft is not None and split.pr_url is not None
            and MATCH_DRAFT not in fix.steps):
        return Accepted(with_fix(conversation, state=LANDING),
                        (MatchDraft(url=split.pr_url, draft=command.draft),))
    if all(has_run(fix.steps, part) for part in parts(split)):
        return _after_the_answer(conversation)
    match next_part(split, fix.steps):
        case SplitPart.TICKET:
            return _file(conversation, command)
        case SplitPart.CHANGES if PICK not in fix.steps:
            return Accepted(with_fix(conversation, state=LANDING),
                            (Pick(message=command.message),))
        case SplitPart.CHANGES:
            return Accepted(with_fix(conversation, state=LANDING), (Push(),))
        case SplitPart.NEW_PR:
            return _open(conversation)
        case SplitPart.REPLY:
            return _answer_the_split(with_fix(conversation, state=LANDING))
    return Accepted(with_fix(conversation, state=PROPOSED))


def _draft_matched(conversation: Conversation, command: DraftMatched) -> Accepted:
    steps = conversation.fix.steps | {MATCH_DRAFT}
    if command.error is None:
        return Accepted(with_fix(conversation, steps=steps))
    return Accepted(with_fix(conversation, steps=steps,
                             reply_note=f"the new PR's draft state was left as the skill set "
                                        f"it: {command.error}"))


def _answer_the_split(conversation: Conversation) -> Accepted:
    if conversation.comment_deleted:
        return _answered(conversation, reply_note="no reply: the comment was deleted")
    fix = conversation.fix
    split = _the_split(fix)
    existing = split.existing_ticket
    links = (split.pr_url, fix.ticket_url if existing is None else existing.url)
    body = "\n\n".join(text for text in (fix.reply, *links) if text)
    return Accepted(conversation, (PostReply(body=body, commit=None),))


def _open(conversation: Conversation) -> Deferred:
    return Deferred(with_fix(conversation, state=QUEUED, run=Run(kind=OperationKind.OPEN),
                             attempts=0, started_at=None, reason=None, decision_error=None),
                    "the approve waits for the new PR to be opened")


def _report_opened(conversation: Conversation, command: ReportOpened) -> Accepted:
    fix = conversation.fix
    return Accepted(with_fix(conversation, state=LANDING, steps=fix.steps | {OPEN_PR},
                             split=replace(_the_split(fix), pr_url=command.url),
                             started_at=None))


def _part_failed(conversation: Conversation, part: SplitPart, **fields: Any) -> Conversation:
    return with_fix(conversation, state=PROPOSED,
                    split=dropped(_the_split(conversation.fix), part), **fields)


def _changes_failed(conversation: Conversation,
                    command: PickRefused | PickConflicted | PushFailed) -> Accepted:
    match command:
        case PushFailed():
            return Accepted(_part_failed(_decidable(conversation, command.at),
                                         SplitPart.CHANGES, push_error=command.error))
        case PickConflicted():
            return Accepted(_part_failed(conversation, SplitPart.CHANGES,
                                         reason=command.conflict + MANUAL_REBASE_ADVICE))
        case PickRefused():
            return Accepted(_part_failed(conversation, SplitPart.CHANGES,
                                         reason=command.reason))


def _report_filed(conversation: Conversation, command: ReportFiled) -> Accepted:
    return Accepted(with_fix(conversation, state=LANDING, steps=conversation.fix.steps | {FILE},
                             ticket_key=command.key, ticket_url=command.url, started_at=None))


def _filing_failed(conversation: Conversation, reason: str, at: str | None,
                   effects: tuple[Any, ...] = ()) -> Accepted:
    return Accepted(with_fix(_decidable(conversation, at), state=LANDING, file_error=reason,
                             started_at=None), effects)


def _unreported(fix: Fix) -> str:
    if fix.run.kind == OperationKind.OPEN:
        return ("ended without reporting the new PR's link; accepting it again first looks "
                f"for a pull request already open from {_the_split(fix).branch}")
    return FILING_UNREPORTED


def _filing_ended(conversation: Conversation, command: Fail | RunExited | RunTimedOut | RunLost,
                  at: str | None) -> Accepted:
    run = _RUN_NAMED[conversation.fix.run.kind]
    unreported = _unreported(conversation.fix)
    match command:
        case Fail():
            return _filing_failed(conversation, command.reason, at)
        case RunTimedOut():
            return _filing_failed(conversation, command.reason, command.at, (StopRun(),))
        case RunExited():
            return _filing_failed(conversation, f"{run} {unreported}", command.at)
        case RunLost():
            return _filing_failed(conversation, f"the board lost {run}, which {unreported}", at)


def _lands_a_commit(fix: Fix) -> bool:
    return fix.kind == ProposalKind.COMMIT


def _land(conversation: Conversation, command: Approve) -> Accepted | Deferred:
    fix = conversation.fix
    if fix.kind == ProposalKind.SPLIT:
        return _run_next_part(conversation, command)
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
    if answered.fix.kind == ProposalKind.SPLIT:
        return Accepted(answered)
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


def _on_the_board_alone(conversation: Conversation) -> bool:
    return conversation.comment_type == KIND_REQUEST


def _answer(conversation: Conversation, command: Approve) -> Accepted:
    if _on_the_board_alone(conversation):
        return _answered(conversation)
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


def _diverged_reason(command: CheckoutDiverged, outcome: str) -> str:
    named = ", ".join(str(sha)[:12] for sha in command.unmatched)
    return (f"origin's PR branch was rewritten: it is at {str(command.origin)[:12]}, and the "
            f"PR worktree at {str(command.head)[:12]} holds commits origin has no equivalent "
            f"of ({named}), so {outcome}")


def _checkout_diverged(conversation: Conversation,
                       command: CheckoutDiverged) -> Accepted | Deferred:
    picked = PICK in conversation.fix.steps
    reason = _diverged_reason(command, "nothing was pushed" if picked else "nothing landed")
    if not command.reconciles_allowed or conversation.state == REMOVED:
        if picked:
            return Accepted(_decidable(with_fix(conversation, push_error=reason), command.at))
        return _handed_back(conversation, reason)
    return Deferred(with_fix(conversation, state=QUEUED, attempts=0, started_at=None,
                             run=Run(kind=OperationKind.RECONCILE, onto=command.origin,
                                     conflict=reason),
                             reason=None, decision_error=None, push_error=None),
                    "the approve waits for the checkout to be reconciled")


def _report_reconciled(conversation: Conversation, command: ReportReconciled) -> Accepted:
    fix = conversation.fix
    if PICK in fix.steps and command.landed_sha is not None:
        return Accepted(with_fix(conversation, state=LANDING, run=Run(), started_at=None,
                                 landed_base=fix.run.onto, landed_sha=command.landed_sha))
    return Accepted(with_fix(conversation, state=PROPOSED, run=Run(), started_at=None,
                             steps=fix.steps - {PICK}, landed_base=None, landed_sha=None))


def _reconcile_ended(conversation: Conversation, reason: str,
                     effects: tuple[Any, ...] = ()) -> Accepted:
    fix = conversation.fix
    said = f"the run reconciling the PR worktree with origin {reason}"
    if PICK in fix.steps:
        return Accepted(with_fix(conversation, state=LANDING, run=Run(), started_at=None,
                                 push_error=said), effects)
    return Accepted(with_fix(conversation, state=PROPOSED, reason=said, run=Run(),
                             started_at=None), effects)


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
                  decision_error=None, reply_note=None, pending_reply=""))


def _answer_in_session(conversation: Conversation) -> Accepted:
    return Accepted(
        with_fix(conversation, state=IN_SESSION, session_from=ASKING, attempts=0,
                 decision_error=None),
        (CutWorkspace(), OpenSession(back_to=ASKING, answers=True)))


def _start_session(conversation: Conversation, command: StartSession) -> Accepted:
    fix = conversation.fix
    if fix.is_asking:
        return _answer_in_session(conversation)
    brief = (Brief(note=command.steer, pointed=command.pointed, include=command.include)
             if command.pointed or command.include else fix.run.brief)
    return Accepted(
        with_fix(conversation, state=IN_SESSION, session_from=fix.state,
                 decision_error=None),
        (CutWorkspace(), OpenSession(back_to=fix.state, steer=command.steer,
                                     skipped=fix.state == DECLINED, brief=brief)),
    )


def _edit_part(conversation: Conversation, command: EditPart) -> Accepted:
    if command.part == SplitPart.TICKET:
        split = replace(_the_split(conversation.fix), ticket=command.ticket)
        return Accepted(with_fix(conversation, split=split, decision_error=None))
    return Accepted(with_fix(conversation, reply=command.reply, decision_error=None))


def _rework(conversation: Conversation, command: Rework) -> Accepted:
    brief = Brief(note=command.note, pointed=command.pointed,
                  include=command.include, part=command.part)
    fix = conversation.fix
    unpicking = fix.state == LANDING and fix.picked
    if fix.state == LANDING and not unpicking:
        conversation = _off_the_branch(conversation)
    return Accepted(
        with_fix(conversation, state=QUEUED, attempts=0, started_at=None,
                  plan=(), decision_error=None, push_error=None, reply_error=None,
                  file_error=None, pending_reply="",
                  run=Run(kind=OperationKind.REWORK, brief=brief)),
        ((Unpick(),) if unpicking else ()) + (CutWorkspace(),),
    )


def _retry(conversation: Conversation) -> Accepted:
    if conversation.fix.state == ABSENT:
        return _first(conversation)
    return Accepted(with_fix(conversation, state=QUEUED, attempts=0,
                              started_at=None, decision_error=None))


QUESTION_DROPPED = "question dropped"


def _drop_question(conversation: Conversation, at: str | None) -> Accepted:
    fix = conversation.fix
    dropped = with_fix(_decidable(conversation, at), question=None, decision_error=None)
    if fix.thread_sha is not None or fix.kind != ProposalKind.COMMIT:
        back_to = fix.thread_sha or fix.base_sha
        return Accepted(with_fix(dropped, state=PROPOSED),
                        () if back_to is None else (ResetWorkspace(to=back_to),))
    failed = with_fix(dropped, state=FAILED, reason=QUESTION_DROPPED)
    return Accepted(failed, () if fix.base_sha is None else (ResetWorkspace(to=fix.base_sha),))


def _landing_withdrawn(conversation: Conversation, reason: str = WITHDRAWN) -> Accepted:
    return Accepted(with_fix(conversation, state=PROPOSED, reason=reason, steps=frozenset(),
                             landed_base=None, landed_sha=None, push_error=None,
                             reply_error=None, file_error=None, decision_error=None,
                             pending_reply=""))


SENT_BACK = "sent back for rework"


def _left_on_the_branch(conversation: Conversation, command: UnpickFailed,
                        done: str = WITHDRAWN) -> str:
    return (f"{done}, but {str(conversation.fix.landed_sha)[:12]} is still on the PR "
            f"branch, unpushed, because {command.error}; take it off by hand before "
            f"approving again")


def _off_the_branch(conversation: Conversation, reason: str | None = None) -> Conversation:
    fields = {} if reason is None else {"reason": reason}
    return with_fix(conversation, steps=frozenset(), landed_base=None, landed_sha=None,
                    **fields)


def _unpicked(conversation: Conversation, command: Unpicked | UnpickFailed) -> Accepted:
    if conversation.fix.state == LANDING:
        if isinstance(command, Unpicked):
            return _landing_withdrawn(conversation)
        return _landing_withdrawn(conversation, _left_on_the_branch(conversation, command))
    if isinstance(command, Unpicked):
        return Accepted(_off_the_branch(conversation))
    return Accepted(_off_the_branch(
        conversation, _left_on_the_branch(conversation, command, SENT_BACK)))


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


def _newest_other_comment(conversation: Conversation, viewer: str) -> Comment | None:
    for comment in reversed(conversation.comments):
        if comment.author != viewer and comment.id is not None:
            return comment
    return None


def _thread_resolved(conversation: Conversation,
                     command: ThreadResolved) -> Accepted:
    return _settled_with_thumbs_up(_github_resolved(conversation, True, None, command.at),
                                   command.viewer)


def _settled_with_thumbs_up(told: Conversation, viewer: str) -> Accepted:
    settled = _settled(told)
    if (told.closing_reply or told.closing_without_thumbs_up
            or told.role != ROLE_REVIEWER or told.comment_type != KIND_REVIEW):
        return settled
    comment = _newest_other_comment(told, viewer)
    if comment is None or comment.id is None:
        return settled
    return Accepted(settled.conversation,
                    (React(comment_id=comment.id, node_id=comment.node_id),)
                    + settled.effects)


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
    if _on_the_board_alone(conversation):
        return _settled(conversation)
    conversation = replace(conversation, closing_on_github=command.resolve,
                           closing_without_thumbs_up=not command.thumbs_up)
    if command.delete_comment:
        if not conversation.comment_deleted:
            return Accepted(conversation, (DeleteComment(),))
        return _settled(conversation)
    if not command.reply:
        if _resolves_on_github(conversation):
            return Accepted(conversation, (ResolveThread(),))
        return _settled_with_thumbs_up(conversation, command.account)
    return Accepted(conversation, (PostReply(body=command.reply),))


def _reject(conversation: Conversation, command: Reject) -> Accepted:
    if _on_the_board_alone(conversation):
        return _settled(conversation, REJECTED)
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
    return Accepted(requeued, (WriteGist(source=GIST_THREAD),))


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
        comment_created_at=comment.created_at, original_commit=command.made_on,
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
        case TakenOver():
            return Accepted(_taken_over(conversation))
        case CommitCheckDue():
            return _commit_check_due(conversation, command, at)
        case CommitChecked():
            return Accepted(checked(conversation, command.check))
        case SetCommitVerdict():
            return _set_commit_verdict(conversation, command)
        case CheckForFixes():
            return _check_for_fixes(conversation, command, at)
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
        case ReportSplit():
            return _report_split(conversation, command, at)
        case ReportAsk():
            return _report_ask(conversation, command, at)
        case ReportFiled():
            return _report_filed(conversation, command)
        case ReportOpened():
            return _report_opened(conversation, command)
        case ReportReconciled():
            return _report_reconciled(conversation, command)
        case Fail() if conversation.fix.run.kind == OperationKind.RECONCILE:
            return _reconcile_ended(conversation, command.reason)
        case RunExited() if conversation.fix.run.kind == OperationKind.RECONCILE:
            return _reconcile_ended(conversation, "ended without reporting")
        case RunTimedOut() if conversation.fix.run.kind == OperationKind.RECONCILE:
            return _reconcile_ended(conversation, command.reason, (StopRun(),))
        case Fail() | RunExited() | RunTimedOut() | RunLost() if (
                conversation.fix.run.kind in PART_RUNS):
            return _filing_ended(conversation, command, at)
        case Fail() | RunExited() | RunTimedOut() if reports_only_a_split(conversation.fix):
            return _split_rework_ended(conversation, command, at)
        case Fail():
            return _fail_or_retry(conversation, command.reason, at)
        case SessionRefused():
            return _session_refused(conversation, command)
        case SessionGone():
            return _session_gone(conversation)
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
        case First() if conversation.fix.is_asking:
            return _carried_on_with_the_reply(conversation)
        case First():
            return _first(conversation)
        case Rebase():
            return _rebase(conversation, command)
        case Picked():
            return _picked(conversation, command)
        case PickRefused() | PickConflicted() | PushFailed() if (
                conversation.fix.kind == ProposalKind.SPLIT):
            return _changes_failed(conversation, command)
        case PickRefused():
            return _handed_back(conversation, command.reason)
        case PickConflicted():
            return _pick_conflicted(conversation, command)
        case CheckoutDiverged():
            return _checkout_diverged(conversation, command)
        case Pushed():
            return Accepted(with_fix(conversation,
                                      steps=conversation.fix.steps | {PUSH},
                                      push_error=None))
        case Unpicked() | UnpickFailed():
            return _unpicked(conversation, command)
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
        case OpenShell():
            return Accepted(conversation, (CutWorkspace(), OpenLoginShell()))
        case ShellRefused():
            return Accepted(conversation)
        case Retry():
            return _retry(conversation)
        case WriteFix():
            return _first(replace(conversation, state=OPEN, wake_on=None,
                                  defer_note=""))
        case Stop():
            return _stop(conversation)
        case DropQuestion():
            return _drop_question(conversation, at)
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
            return Accepted(replace(conversation, comments=tuple(
                reacted(c, THUMBS_UP, True) if c.id == command.comment_id else c
                for c in conversation.comments)))
        case DraftMatched():
            return _draft_matched(conversation, command)
        case ReactionFailed():
            return Accepted(with_fix(
                conversation, reply_note=f"thumbs-up failed: {command.error}"))
        case EditDraft():
            return Accepted(_edited(conversation, command))
        case EditPart():
            return _edit_part(conversation, command)
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
