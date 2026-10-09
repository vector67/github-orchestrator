from collections.abc import Callable
from dataclasses import dataclass, replace
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
    IN_SESSION,
    LANDED,
    LANDING,
    NOT_MINE,
    OPEN,
    PICK,
    PROPOSED,
    QUEUED,
    REJECTED,
    REMOVED,
    RESOLVED,
    ROLE_AUTHOR,
    ROLE_REVIEWER,
    RUNNING,
    WAITING_ON_REVIEWER,
    Brief,
    ConfidenceLevel,
    Conversation,
    ConversationState,
    OperationKind,
    ProposalKind,
    Run,
    Ticket,
)
from github_orchestrator.conversation._domain.diff import KIND_ISSUE, KIND_REVIEW
from github_orchestrator.conversation._domain.events import (
    GistWritten,
    Posted,
    Rebase,
    Reopen,
    RunExited,
    RunLost,
    RunStarted,
    RunTimedOut,
    SessionRefused,
    Wake,
)
from github_orchestrator.conversation._domain.operations import Asked
from github_orchestrator.conversation._domain.standing import ErrorCode
from github_orchestrator.conversation._domain.steps import First, Land
from github_orchestrator.domain import Sha

REWORK_ADVICE = "send back for rework"

NOTHING_TO_POST = "the reply is empty, so there is nothing to post"

PARKED = (WAITING_ON_REVIEWER, DEFERRED, REJECTED, RESOLVED, DISCARDED, CONFIRMED)

CLOSED = (REJECTED, RESOLVED, DISCARDED, CONFIRMED)

DRAFTING = (DRAFT, ENROLLED)

IN_FLIGHT = (QUEUED, RUNNING, IN_SESSION, LANDING)

IDLE_FIX = (PROPOSED, DECLINED, FAILED)

DELETABLE_KINDS = (KIND_REVIEW, KIND_ISSUE)

PLACED_BY_HAND_FROM = (ASSUMED_DONE, NOT_MINE)

OUTCOMES_BY_HAND = {
    ROLE_REVIEWER: (ConversationState.READY, ConversationState.WAITING,
                    ConversationState.NOT_MINE),
    ROLE_AUTHOR: (ConversationState.READY, ConversationState.WAITING,
                  ConversationState.QUEUED),
}

_CODE_OF_STATE = {
    DRAFT: ErrorCode.STILL_A_DRAFT,
    ENROLLED: ErrorCode.STILL_A_DRAFT,
    WAITING_ON_REVIEWER: ErrorCode.PARKED,
    ASSUMED_DONE: ErrorCode.PARKED,
    NOT_MINE: ErrorCode.PARKED,
    DEFERRED: ErrorCode.PARKED,
    REJECTED: ErrorCode.ALREADY_CLOSED,
    RESOLVED: ErrorCode.ALREADY_CLOSED,
}

_CODE_OF_FIX = {
    QUEUED: ErrorCode.OPERATION_OUTSTANDING,
    RUNNING: ErrorCode.OPERATION_OUTSTANDING,
    IN_SESSION: ErrorCode.OPERATION_OUTSTANDING,
    LANDING: ErrorCode.OPERATION_OUTSTANDING,
    PROPOSED: ErrorCode.PROPOSAL_EXISTS,
    DECLINED: ErrorCode.NO_PROPOSAL,
    FAILED: ErrorCode.NO_PROPOSAL,
    ABSENT: ErrorCode.NO_PROPOSAL,
    LANDED: ErrorCode.ALREADY_CLOSED,
}


@dataclass(frozen=True)
class Accepted:
    conversation: Conversation
    effects: tuple[Any, ...] = ()


@dataclass(frozen=True)
class Refused:
    conversation: Conversation
    code: ErrorCode
    reason: str


@dataclass(frozen=True)
class Deferred:
    conversation: Conversation
    reason: str = ""


Rule = Callable[[Conversation, Any], Refused | Deferred | None]


def with_fix(conversation: Conversation, **fields: Any) -> Conversation:
    return replace(conversation, fix=replace(conversation.fix, **fields))


def _state_code(conversation: Conversation) -> ErrorCode:
    return _CODE_OF_STATE.get(conversation.state, ErrorCode.ALREADY_CLOSED)


def _fix_code(conversation: Conversation) -> ErrorCode:
    return _CODE_OF_FIX.get(conversation.fix.state, ErrorCode.NO_PROPOSAL)


def _refuse_decision(conversation: Conversation, code: ErrorCode,
                     reason: str) -> Refused:
    return Refused(with_fix(conversation, decision_error=reason), code,
                   reason)


def landing_under_way(conversation: Conversation) -> bool:
    fix = conversation.fix
    return (fix.state == LANDING and not fix.push_error
            and not fix.reply_error and not fix.file_error)


def _may_land(conversation: Conversation) -> bool:
    return conversation.fix.state == PROPOSED or conversation.state == REMOVED


def _planning(states: tuple[str, ...], refusing: str) -> Rule:
    def planning(conversation: Conversation, change: Any) -> Refused | None:
        if conversation.state != OPEN:
            return Refused(conversation, _state_code(conversation),
                           f"a {conversation.state} conversation {refusing}")
        if conversation.fix.state not in states:
            return Refused(conversation, ErrorCode.NOTHING_IN_FLIGHT,
                           f"nobody is working on a {conversation.fix.state} fix")
        return None
    return planning


def _step_in_the_plan(conversation: Conversation, command: StepDone) -> Refused | None:
    plan = conversation.fix.plan
    outside = [index for index in command.indexes
               if not 1 <= index <= len(plan)]
    if outside:
        return Refused(conversation, ErrorCode.INTERNAL_REFUSAL,
                       f"step {outside[0]} is outside a plan of {len(plan)}")
    return None


def _reported_on(states: tuple[str, ...], nobody: str) -> Rule:
    def reported_on(conversation: Conversation, change: Any) -> Refused | None:
        fix = conversation.fix
        if conversation.state != OPEN:
            return Refused(conversation, _state_code(conversation),
                           f"a {conversation.state} conversation takes no report")
        if fix.state not in states:
            return Refused(conversation, ErrorCode.NOTHING_IN_FLIGHT,
                           f"{nobody} a {fix.state} fix")
        return None
    return reported_on


def _a_commit(conversation: Conversation, command: ReportReady | MoveBase) -> Refused | None:
    if Sha.parse(command.sha) is None:
        return Refused(conversation, ErrorCode.INTERNAL_REFUSAL,
                       f"{command.sha!r} is not a commit hash; pass the full or "
                       f"abbreviated hash of the commit")
    return None


def _on_the_base(conversation: Conversation, command: ReportReady) -> Refused | None:
    if command.on_base:
        return None
    base = conversation.fix.base_sha
    return Refused(conversation, ErrorCode.INTERNAL_REFUSAL,
                   f"you cannot propose {command.sha}: this thread's base {base} "
                   f"is not an ancestor of {command.sha}. If your commit sits on a "
                   f"newer tip of the PR branch than {base}, and that tip is where "
                   f"it should merge, move this thread's base to that tip with "
                   f"`cli thread base --sha <tip>` (same --repo, --pr and "
                   f"--thread-id), then run this command again. Otherwise rebase "
                   f"your commit onto {base} and run this command again with the "
                   f"new sha")


def _a_known_confidence(conversation: Conversation,
                        command: ReportReady) -> Refused | None:
    if (command.confidence is not None
            and command.confidence not in frozenset(ConfidenceLevel)):
        return Refused(conversation, ErrorCode.INTERNAL_REFUSAL,
                       f"{command.confidence!r} is no confidence this board "
                       f"knows")
    return None


def _the_gist_of_this_body(conversation: Conversation,
                           event: GistWritten) -> Refused | None:
    if event.body != conversation.body:
        return Refused(conversation, ErrorCode.INTERNAL_REFUSAL,
                       "the comment changed while the gist was written")
    return None


def _queued_for_a_run(conversation: Conversation, event: RunStarted) -> Refused | None:
    fix = conversation.fix
    if conversation.state != OPEN:
        return Refused(conversation, _state_code(conversation),
                       f"a {conversation.state} conversation wants no agent")
    if fix.state != QUEUED:
        return Refused(conversation, ErrorCode.NOTHING_IN_FLIGHT,
                       f"the fix is {fix.state}, not queued")
    return None


def _a_session_opening(conversation: Conversation,
                       event: SessionRefused) -> Refused | None:
    if conversation.fix.state != IN_SESSION:
        return Refused(conversation, ErrorCode.NOTHING_IN_FLIGHT,
                       f"no session is opening on a {conversation.fix.state} fix")
    return None


def _a_filing_run(conversation: Conversation, command: ReportFiled) -> Refused | None:
    if conversation.fix.run.kind != OperationKind.FILE:
        return Refused(conversation, ErrorCode.NOTHING_IN_FLIGHT,
                       f"a {conversation.fix.run.kind} run files no ticket")
    return None


def _running_only(conversation: Conversation, change: Any) -> Refused | None:
    if conversation.state != OPEN:
        return Refused(conversation, _state_code(conversation),
                       f"a {conversation.state} conversation has no run")
    if conversation.fix.state != RUNNING:
        return Refused(conversation, ErrorCode.NOTHING_IN_FLIGHT,
                       f"no run is under way on a {conversation.fix.state} fix")
    return None


def _rebase_gate(conversation: Conversation, command: Approve) -> Refused | Deferred | None:
    fix = conversation.fix
    if not fix.run.is_rebase:
        return None
    if fix.state in (QUEUED, RUNNING):
        return Deferred(conversation, "its rebase run is still in flight")
    if fix.state == FAILED:
        return Refused(conversation, ErrorCode.NO_PROPOSAL,
                       "its rebase run failed")
    if fix.state == PROPOSED and fix.kind == ProposalKind.REPLY:
        reason = ("the rebase found the work already done and proposes a reply "
                  "instead; read it and accept it if it stands")
        return Refused(with_fix(conversation, reason=reason,
                                run=Run(kind=OperationKind.FIRST)),
                       ErrorCode.CONFIRM_AGAIN, reason)
    if fix.state == PROPOSED and fix.tests != "passed":
        reason = (f"the rebased fix reports tests {fix.tests}; approve again "
                  "to land it anyway")
        return Refused(with_fix(conversation, reason=reason,
                                run=Run(kind=OperationKind.FIRST)),
                       ErrorCode.CONFIRM_AGAIN, reason)
    return None


def _unready(conversation: Conversation, command: Approve) -> Deferred | None:
    if command.run_alive:
        return Deferred(conversation, "an agent run is alive")
    if not command.worktree_clean:
        return Deferred(conversation, "the PR worktree is not clean")
    return None


def _not_parked_to_land(conversation: Conversation, command: Approve) -> Refused | None:
    if conversation.state in PARKED:
        return Refused(conversation, _state_code(conversation),
                       f"a {conversation.state} conversation cannot be landed")
    return None


def _no_landing_under_way(conversation: Conversation, command: Approve) -> Refused | None:
    if landing_under_way(conversation):
        return Refused(conversation, ErrorCode.OPERATION_OUTSTANDING,
                       "a landing is already under way")
    return None


def _a_commit_to_land(conversation: Conversation, command: Approve) -> Refused | None:
    fix = conversation.fix
    if fix.kind == ProposalKind.COMMIT and fix.state != LANDING and not fix.thread_sha:
        reason = ("the agent finished without committing a fix, so there "
                  f"is nothing to land; {REWORK_ADVICE}")
        return Refused(with_fix(conversation, reason=reason),
                       ErrorCode.NO_PROPOSAL, reason)
    return None


def _a_reply_to_post(conversation: Conversation, command: Approve) -> Refused | None:
    fix = conversation.fix
    if fix.kind == ProposalKind.REPLY and fix.state != LANDING and not command.reply.strip():
        return _refuse_decision(conversation, ErrorCode.EMPTY_BODY,
                                NOTHING_TO_POST)
    return None


def _filing(conversation: Conversation, command: Approve) -> Deferred | None:
    fix = conversation.fix
    if fix.run.kind == OperationKind.FILE and fix.state in (QUEUED, RUNNING):
        return Deferred(conversation, "the ticket is still being filed")
    return None


def ticket_to_file(conversation: Conversation, command: Approve) -> Ticket | None:
    return command.ticket or conversation.fix.ticket


def _a_ticket_to_file(conversation: Conversation, command: Approve) -> Refused | None:
    fix = conversation.fix
    if fix.kind != ProposalKind.TICKET or fix.filed:
        return None
    if not command.filing_allowed:
        return _refuse_decision(
            conversation, ErrorCode.AGENTS_DISABLED,
            "Agents are disabled (agents_enabled=false), and an agent files the ticket, "
            "so nothing was filed or posted")
    ticket = ticket_to_file(conversation, command)
    if ticket is None or not all(part.strip() for part in (ticket.project, ticket.title,
                                                            ticket.body)):
        return _refuse_decision(conversation, ErrorCode.EMPTY_BODY,
                                "the ticket needs a project, a title and a body to be filed")
    if not command.reply.strip():
        return _refuse_decision(conversation, ErrorCode.EMPTY_BODY,
                                NOTHING_TO_POST)
    return None


def _a_fix_to_land(conversation: Conversation, command: Approve) -> Refused | None:
    fix = conversation.fix
    if fix.state != LANDING and not _may_land(conversation):
        return Refused(conversation, _fix_code(conversation),
                       f"a {fix.state} fix cannot be landed")
    return None


def _resolvable(conversation: Conversation, command: Approve) -> Refused | None:
    if conversation.fix.state == LANDING or not command.resolve:
        return None
    if conversation.comment_type != KIND_REVIEW:
        return _refuse_decision(conversation, ErrorCode.MALFORMED_REQUEST,
                                "only a review thread can be marked resolved")
    if command.delete_comment:
        return _refuse_decision(
            conversation, ErrorCode.MALFORMED_REQUEST,
            "a deleted comment leaves no thread to mark resolved")
    return None


def _why_not_deletable(conversation: Conversation, account: str) -> str | None:
    if conversation.comment_type not in DELETABLE_KINDS:
        return f"GitHub deletes no {conversation.comment_type or KIND_REVIEW} comment"
    if conversation.author != account:
        return f"{conversation.author} wrote that comment, so it is not yours to delete"
    if not conversation.comment_id:
        return "the comment has no id on GitHub to delete it by"
    others = [one.author for one in conversation.comments if one.author != account]
    if others:
        return (f"{others[0]} has replied in the thread, so the comment is not "
                "yours to delete")
    return None


def _yours_to_delete(conversation: Conversation,
                     command: Approve | Resolve | Reject) -> Refused | None:
    if not command.delete_comment:
        return None
    why = _why_not_deletable(conversation, command.account)
    if why is None:
        return None
    return _refuse_decision(conversation, ErrorCode.NOT_DELETABLE, why)


def prepared_to_land(conversation: Conversation, command: Approve) -> Conversation:
    fix = conversation.fix
    return with_fix(
        conversation, state=LANDING, push_error=None, reply_error=None, file_error=None,
        pending_reply=(fix.pending_reply if ANSWER in fix.steps
                       else command.reply),
        resolve_on_land=(fix.resolve_on_land if fix.state == LANDING
                         else command.resolve))


def _ready_to_pick(conversation: Conversation, command: Approve) -> Deferred | None:
    fix = conversation.fix
    if fix.kind != ProposalKind.COMMIT:
        return None
    if fix.state != LANDING:
        return _unready(conversation, command)
    if PICK not in fix.steps:
        return _unready(prepared_to_land(conversation, command), command)
    return None


def _landing(conversation: Conversation, step: Land) -> Refused | None:
    fix = conversation.fix
    if fix.state != LANDING:
        return Refused(conversation, _fix_code(conversation),
                       f"a {fix.state} fix is not landing")
    return None


def _ready_to_pick_while_landing(conversation: Conversation,
                                 step: Land) -> Deferred | None:
    fix = conversation.fix
    if fix.kind == ProposalKind.COMMIT and PICK not in fix.steps:
        return _unready(conversation, step)
    return None


def _wanting_a_first_run(conversation: Conversation, step: First) -> Refused | None:
    fix = conversation.fix
    if conversation.state not in (OPEN, REMOVED):
        return Refused(conversation, _state_code(conversation),
                       f"a {conversation.state} conversation wants no run")
    if fix.state in IN_FLIGHT:
        return Refused(conversation, _fix_code(conversation),
                       f"a {fix.state} fix wants no second run")
    return None


def _waiting_to_be_caught_up(conversation: Conversation, event: Rebase) -> Refused | None:
    fix = conversation.fix
    if conversation.state in PARKED:
        return Refused(conversation, _state_code(conversation),
                       f"a {conversation.state} conversation rebases nothing")
    if fix.state in (QUEUED, RUNNING, IN_SESSION, LANDED) or (
            fix.state == LANDING and PICK in fix.steps):
        return Refused(conversation, _fix_code(conversation),
                       f"a {fix.state} fix is not waiting to be caught up")
    if fix.state not in (PROPOSED, LANDING):
        return Refused(conversation, ErrorCode.NO_PROPOSAL,
                       f"a {fix.state} fix left nothing to rebase")
    return None


def _agents_enabled_for_a_session(conversation: Conversation,
                                  command: StartSession) -> Refused | None:
    if not command.sessions_allowed:
        return _refuse_decision(
            conversation, ErrorCode.AGENTS_DISABLED,
            "Agents are disabled (agents_enabled=false) — no rework session "
            "started.")
    return None


def _agents_enabled_for_a_rework(conversation: Conversation,
                                 command: Rework) -> Refused | None:
    if not command.reworks_allowed:
        return _refuse_decision(
            conversation, ErrorCode.AGENTS_DISABLED,
            "Agents are disabled (agents_enabled=false) — nothing was sent back "
            "for rework.")
    return None


def _open_to(refusing: str) -> Rule:
    def open_to(conversation: Conversation, command: Any) -> Refused | None:
        if conversation.state != OPEN:
            return _refuse_decision(
                conversation, _state_code(conversation),
                f"a {conversation.state} conversation {refusing}")
        return None
    return open_to


def _a_fix_in(states: tuple[str, ...], refusing: str) -> Rule:
    def a_fix_in(conversation: Conversation, command: Any) -> Refused | None:
        fix = conversation.fix
        if fix.state not in states:
            return _refuse_decision(
                conversation, _fix_code(conversation),
                f"a {fix.state} fix {refusing}")
        return None
    return a_fix_in


def _a_brief(conversation: Conversation, command: Rework) -> Refused | None:
    brief = Brief(note=command.note, pointed=command.pointed,
                  include=command.include)
    if brief.is_empty:
        return _refuse_decision(
            conversation, ErrorCode.EMPTY_BRIEF,
            "an autonomous rework needs a note or a pointed line to work from")
    return None


def _open_to_a_fix(conversation: Conversation, command: WriteFix) -> Refused | None:
    if conversation.state not in (OPEN, WAITING_ON_REVIEWER):
        return _refuse_decision(
            conversation, _state_code(conversation),
            f"a {conversation.state} conversation wants no fix written")
    return None


def _not_closed_to_stop(conversation: Conversation, command: Stop) -> Refused | None:
    if conversation.state in CLOSED or conversation.fix.state == LANDED:
        return _refuse_decision(
            conversation, ErrorCode.NOTHING_IN_FLIGHT,
            "a closed conversation has nothing in flight to stop")
    return None


def _in_flight_to_stop(conversation: Conversation, command: Stop) -> Refused | None:
    fix = conversation.fix
    if fix.state in IN_FLIGHT:
        return None
    if fix.state == PROPOSED:
        return _refuse_decision(
            conversation, ErrorCode.PROPOSAL_EXISTS,
            "the run has finished and left a proposal; reject turns it down")
    return _refuse_decision(
        conversation, ErrorCode.NOTHING_IN_FLIGHT,
        f"a {fix.state} fix has nothing in flight to stop")


def _not_pushed_to_stop(conversation: Conversation, command: Stop) -> Refused | None:
    if conversation.fix.state == LANDING and conversation.fix.pushed:
        return _refuse_decision(
            conversation, ErrorCode.NOTHING_IN_FLIGHT,
            "the fix is already pushed to the PR branch, so there is no landing left to "
            "stop; approve again to post the reply")
    if conversation.fix.state == LANDING and conversation.fix.filed:
        return _refuse_decision(
            conversation, ErrorCode.NOTHING_IN_FLIGHT,
            f"the ticket is already filed as {conversation.fix.ticket_key}, so there is no "
            "landing left to stop; approve again to post the reply")
    return None


def _still_open_to_resolve(conversation: Conversation, command: Resolve) -> Refused | None:
    if conversation.state not in (OPEN, REMOVED, WAITING_ON_REVIEWER, DEFERRED,
                                  ASSUMED_DONE, NOT_MINE):
        return _refuse_decision(
            conversation, _state_code(conversation),
            f"a {conversation.state} conversation is already closed")
    return None


def _the_operators_to_resolve(conversation: Conversation,
                              command: Resolve) -> Refused | None:
    fix = conversation.fix
    if fix.state in (RUNNING, LANDING, LANDED) or (
            conversation.state != REMOVED
            and fix.state in (QUEUED, IN_SESSION)):
        return _refuse_decision(
            conversation, _fix_code(conversation),
            f"a {fix.state} fix is not the operator's to close")
    return None


def _a_comment_to_answer_on_resolving(conversation: Conversation,
                                      command: Resolve) -> Refused | None:
    if (not command.delete_comment and command.reply
            and conversation.comment_deleted):
        return _refuse_decision(
            conversation, ErrorCode.COMMENT_GONE,
            "no reply posted: the comment was deleted from GitHub")
    return None


def _a_thread_left_to_resolve(conversation: Conversation,
                              command: Resolve) -> Refused | None:
    if command.resolve and command.delete_comment:
        return _refuse_decision(
            conversation, ErrorCode.MALFORMED_REQUEST,
            "a deleted comment leaves no thread to mark resolved")
    return None


def _still_open_to_reject(conversation: Conversation, command: Reject) -> Refused | None:
    if conversation.state not in (OPEN, REMOVED):
        return _refuse_decision(
            conversation, _state_code(conversation),
            f"a {conversation.state} conversation is already closed")
    return None


def _a_fix_to_turn_down(conversation: Conversation, command: Reject) -> Refused | None:
    fix = conversation.fix
    if fix.state == LANDED:
        return _refuse_decision(
            conversation, ErrorCode.ALREADY_CLOSED,
            "a landed fix is not the operator's to reject")
    if fix.state in IN_FLIGHT:
        return _refuse_decision(
            conversation, ErrorCode.WORK_IN_FLIGHT,
            f"a {fix.state} fix is still in flight; stop it first")
    if fix.state not in IDLE_FIX:
        return _refuse_decision(
            conversation, ErrorCode.NO_PROPOSAL,
            f"a {fix.state} fix left nothing to turn down")
    return None


def _a_comment_to_answer_on_rejecting(conversation: Conversation,
                                      command: Reject) -> Refused | None:
    if command.reply and conversation.comment_deleted:
        return _refuse_decision(
            conversation, ErrorCode.COMMENT_GONE,
            "no reply posted: the comment was deleted from GitHub")
    return None


def _open_to_park(conversation: Conversation, command: Defer) -> Refused | None:
    if conversation.state not in (OPEN, WAITING_ON_REVIEWER, DEFERRED, ASSUMED_DONE,
                                  NOT_MINE):
        return _refuse_decision(
            conversation, _state_code(conversation),
            f"a {conversation.state} conversation is not open to park")
    return None


def _the_operators_to_park(conversation: Conversation, command: Defer) -> Refused | None:
    fix = conversation.fix
    if fix.state in (LANDING, LANDED):
        return _refuse_decision(
            conversation, _fix_code(conversation),
            f"a {fix.state} fix is not the operator's to park")
    return None


def _deferred_to_wake(conversation: Conversation, event: Wake) -> Refused | None:
    if conversation.state != DEFERRED:
        return Refused(conversation, ErrorCode.NOT_PARKED,
                       f"a {conversation.state} conversation is not deferred")
    return None


def _parked_to_unpark(conversation: Conversation, command: Unpark) -> Refused | None:
    landed = conversation.state == OPEN and conversation.fix.state == LANDED
    if conversation.state not in PARKED and not landed:
        return _refuse_decision(
            conversation, ErrorCode.NOT_PARKED,
            f"a {conversation.state} conversation is not parked")
    return None


def _assumed_done_to_confirm(conversation: Conversation,
                             command: Confirm) -> Refused | None:
    if conversation.state != ASSUMED_DONE:
        return _refuse_decision(
            conversation, ErrorCode.NOT_PARKED,
            f"a {conversation.state} conversation is not assumed done")
    return None


def _an_outcome_of_the_role(conversation: Conversation, command: Place) -> Refused | None:
    if command.to not in OUTCOMES_BY_HAND[conversation.role]:
        return _refuse_decision(
            conversation, ErrorCode.MALFORMED_REQUEST,
            f"no outcome on this pull request places a thread in {command.to}")
    return None


def _placed_by_an_agent(conversation: Conversation, command: Place) -> Refused | None:
    if conversation.state not in PLACED_BY_HAND_FROM:
        return _refuse_decision(
            conversation, ErrorCode.NOT_PARKED,
            f"a {conversation.state} conversation was not placed by an agent")
    return None


def _drafting(*wanted: str) -> Rule:
    def drafting(conversation: Conversation, change: Any) -> Refused | None:
        if conversation.state in wanted:
            return None
        if conversation.state == ENROLLED:
            return Refused(conversation, ErrorCode.ALREADY_ENROLLED,
                           "the draft is in the outgoing review; withdraw it first")
        if conversation.state == DRAFT:
            return Refused(conversation, ErrorCode.NOTHING_ENROLLED,
                           "the draft is not in the outgoing review")
        if conversation.standing == ConversationState.DONE:
            return Refused(conversation, ErrorCode.ALREADY_CLOSED,
                           "a closed thread is no draft to work on")
        return Refused(conversation, ErrorCode.NOT_A_DRAFT,
                       "the thread is on GitHub already, not a draft")
    return drafting


def _not_closed_to_reply(conversation: Conversation, command: Reply) -> Refused | None:
    if conversation.state in CLOSED or conversation.fix.state == LANDED:
        return _refuse_decision(
            conversation, ErrorCode.ALREADY_CLOSED,
            "a closed conversation takes no reply")
    return None


def _something_said(conversation: Conversation, command: Reply) -> Refused | None:
    if not command.text.strip():
        return _refuse_decision(conversation, ErrorCode.EMPTY_BODY,
                                "nothing was said, so nothing was "
                                "posted")
    return None


RULES: dict[type, tuple[Rule, ...]] = {
    GistWritten: (_the_gist_of_this_body,),
    DeclarePlan: (_planning((QUEUED, RUNNING, IN_SESSION), "takes no plan"),),
    StepDone: (_planning((QUEUED, RUNNING, IN_SESSION, PROPOSED), "marks no step"),
               _step_in_the_plan),
    ReportReady: (_reported_on((RUNNING, IN_SESSION, PROPOSED), "nobody is working on"),
                  _a_commit, _on_the_base, _a_known_confidence),
    MoveBase: (_reported_on((RUNNING, IN_SESSION, PROPOSED), "nobody is working on"),
               _a_commit),
    ReportDeclined: (_reported_on((QUEUED, RUNNING, IN_SESSION), "no agent holds"),),
    ReportReply: (_reported_on((RUNNING, IN_SESSION, PROPOSED), "nobody is working on"),),
    ReportTicket: (_reported_on((RUNNING, IN_SESSION, PROPOSED), "nobody is working on"),),
    ReportFiled: (_reported_on((RUNNING,), "nobody is filing a ticket for"), _a_filing_run),
    Fail: (_running_only,),
    SessionRefused: (_a_session_opening,),
    RunStarted: (_queued_for_a_run,),
    RunExited: (_running_only,),
    RunTimedOut: (_running_only,),
    RunLost: (_running_only,),
    Land: (_landing, _ready_to_pick_while_landing),
    Approve: (_not_parked_to_land, _no_landing_under_way, _rebase_gate, _filing,
              _a_commit_to_land, _a_fix_to_land, _a_ticket_to_file, _a_reply_to_post,
              _resolvable, _yours_to_delete, _ready_to_pick),
    First: (_wanting_a_first_run,),
    Rebase: (_waiting_to_be_caught_up,),
    Rework: (_agents_enabled_for_a_rework, _open_to("sends nothing back"),
             _a_fix_in((PROPOSED, DECLINED, FAILED), "is not yours to send back"), _a_brief),
    StartSession: (_agents_enabled_for_a_session, _open_to("opens no session"),
                   _a_fix_in((PROPOSED, DECLINED, FAILED), "is not waiting for anyone")),
    Retry: (_open_to("retries nothing"), _a_fix_in((DECLINED, FAILED), "is not failed")),
    WriteFix: (_open_to_a_fix, _a_fix_in((ABSENT,), "has a fix already")),
    Stop: (_not_closed_to_stop, _in_flight_to_stop, _not_pushed_to_stop),
    Resolve: (_still_open_to_resolve, _the_operators_to_resolve,
              _a_comment_to_answer_on_resolving, _a_thread_left_to_resolve,
              _yours_to_delete),
    Reject: (_still_open_to_reject, _a_fix_to_turn_down, _a_comment_to_answer_on_rejecting,
             _yours_to_delete),
    Defer: (_open_to_park, _the_operators_to_park),
    Wake: (_deferred_to_wake,),
    Unpark: (_parked_to_unpark,),
    Confirm: (_assumed_done_to_confirm,),
    Place: (_an_outcome_of_the_role, _placed_by_an_agent),
    EditDraft: (_drafting(DRAFT, ENROLLED),),
    Enrol: (_drafting(DRAFT),),
    WithdrawFromReview: (_drafting(ENROLLED),),
    Discard: (_drafting(DRAFT),),
    PostNow: (_drafting(DRAFT),),
    Posted: (_drafting(ENROLLED),),
    Reply: (_not_closed_to_reply, _something_said),
}

_REFUSED_ON_A_DRAFT: dict[type, ErrorCode] = {
    First: ErrorCode.STILL_A_DRAFT,
    Rebase: ErrorCode.STILL_A_DRAFT,
    Rework: ErrorCode.NO_PROPOSAL,
    Retry: ErrorCode.STILL_A_DRAFT,
    WriteFix: ErrorCode.STILL_A_DRAFT,
    StartSession: ErrorCode.STILL_A_DRAFT,
    Approve: ErrorCode.NO_PROPOSAL,
    Land: ErrorCode.NO_PROPOSAL,
    Stop: ErrorCode.NOTHING_IN_FLIGHT,
    Resolve: ErrorCode.STILL_A_DRAFT,
    Reject: ErrorCode.NO_PROPOSAL,
    Defer: ErrorCode.STILL_A_DRAFT,
    Unpark: ErrorCode.NOT_PARKED,
    Reply: ErrorCode.STILL_A_DRAFT,
    Reopen: ErrorCode.NOT_FOUND,
}


def _thread_verb_on_a_draft(conversation: Conversation, change: Change) -> Refused | None:
    if conversation.state not in DRAFTING:
        return None
    code = _REFUSED_ON_A_DRAFT.get(type(change))
    if code is None:
        return None
    return Refused(conversation, code,
                   f"a {conversation.state} comment is not on GitHub yet")


def _outstanding(conversation: Conversation, change: Change,
                 asked: Asked | None) -> Refused | None:
    waiting_on = history.blocking(conversation, change, asked)
    if waiting_on is None:
        return None
    code, reason = history.outstanding_refusal(waiting_on)
    return Refused(conversation, code, reason)


def refusal(conversation: Conversation, change: Change,
            asked: Asked | None) -> Refused | Deferred | None:
    """Whether the rules let this change happen to this conversation now: a
    thread's verb is refused on a draft, nothing is taken while an earlier
    operation waits, and each kind of change has its own rules, asked in
    order."""
    found = (_thread_verb_on_a_draft(conversation, change)
             or _outstanding(conversation, change, asked))
    if found is not None:
        return found
    for rule in RULES.get(type(change), ()):
        answered = rule(conversation, change)
        if answered is not None:
            return answered
    return None
