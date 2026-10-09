from dataclasses import dataclass, field
from enum import Enum, StrEnum

from github_orchestrator.domain import Location, Sha, Side


class OperationKind(StrEnum):
    """What kind of work this is. `first`, `rebase` and `file` are the board's
    own: a thread gets a run when it appears, another when the pull request's
    head moves under a proposal, and one that files the ticket when a ticket
    is accepted. The rest are asked for, and each has a custom method of its
    own."""

    FIRST = "first"
    REBASE = "rebase"
    FILE = "file"
    REWORK = "rework"
    RETRY = "retry"
    START_SESSION = "start-session"
    APPROVE = "approve"
    STOP = "stop"
    RESOLVE = "resolve"
    REJECT = "reject"
    DEFER = "defer"
    UNPARK = "unpark"
    CONFIRM = "confirm"
    PLACE = "place"
    REPLY = "reply"
    CREATE_DRAFT = "create-draft"
    EDIT_DRAFT = "edit-draft"
    ENROL = "enrol"
    WITHDRAW_FROM_REVIEW = "withdraw-from-review"
    DISCARD = "discard"
    POST_NOW = "post-now"
    SEND_REVIEW = "send-review"
    POSTED = "posted"


class OperationState(StrEnum):
    """`pending` until the board picks it up, `running` while it works,
    `requeued` when the board put it back for the next pass. `requeued`
    rather than `deferred`, which now means something a thread can be."""

    PENDING = "pending"
    RUNNING = "running"
    APPLIED = "applied"
    REFUSED = "refused"
    REQUEUED = "requeued"


class ReasonCode(StrEnum):
    """Why a piece of work settled refused or was put back.

    An `ErrorCode` answers a request the domain would not take; one of these
    is written onto an operation the domain did take, when git, GitHub or the
    agent later said no. GIT_FAILED is git refusing the pick itself rather
    than conflicting.
    """

    WITHDRAWN = "withdrawn"
    AGENT_DECLINED = "agent-declined"
    MAX_ATTEMPTS = "max-attempts"
    AGENT_UNAVAILABLE = "agent-unavailable"
    CONFLICT = "conflict"
    NOTHING_COMMITTED = "nothing-committed"
    PUSH_FAILED = "push-failed"
    REPLY_FAILED = "reply-failed"
    FILE_FAILED = "file-failed"
    COMMENT_GONE = "comment-gone"
    GITHUB_REJECTED = "github-rejected"
    GIT_FAILED = "git-failed"
    ANCHOR_NOT_IN_DIFF = "anchor-not-in-diff"
    SUPERSEDED = "superseded"
    WORKTREE_MISSING = "worktree-missing"


class Classification(StrEnum):
    """How the agent classified a comment it made no commit for. A closed
    vocabulary because the board branches on it, unlike the sentence in the
    reason."""

    RISKY = "risky"
    UNCLEAR = "unclear"
    OUT_OF_SCOPE = "out-of-scope"
    ALREADY_DONE = "already-done"
    ACKNOWLEDGEMENT = "acknowledgement"
    QUESTION = "question"
    NEEDS_HUMAN = "needs-human"

    @property
    def asks_a_reply(self) -> bool:
        return self in ANSWERED_WITH_A_REPLY


ANSWERED_WITH_A_REPLY = frozenset({Classification.ALREADY_DONE, Classification.QUESTION,
                                   Classification.UNCLEAR, Classification.OUT_OF_SCOPE})


class ProposalKind(StrEnum):
    COMMIT = "commit"
    REPLY = "reply"
    TICKET = "ticket"


@dataclass(frozen=True)
class Ticket:
    project: str
    title: str
    body: str


class ThreadVerdict(StrEnum):
    MY_MOVE = "my-move"
    THEIR_MOVE = "their-move"
    ASSUMED_DONE = "assumed-done"
    NOT_MINE = "not-mine"


class ConfidenceLevel(StrEnum):
    """How sure the agent is of the fix it proposes."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConversationState(StrEnum):
    """Where the state machine puts this thread. Computed here rather than in
    the browser: it folds a whole operation history through a dozen compound
    conditions, and a card under the wrong heading is worse than a field the
    client could in principle have derived.

    The transition table, with a refusal code on every disallowed edge, is
    the machine's own document. This enum is its state set. Its triggers are
    of three sorts: an operation someone asked for, an operation changing
    state of its own accord as the board drains it, and a comment arriving
    from the poller. Only the first sort can be refused.

    `enrolled` rather than `pending`, because `pending` already means an
    operation the board has not picked up, and `PENDING` already means
    GitHub's unsubmitted review.
    """

    DRAFT = "draft"
    ENROLLED = "enrolled"
    QUEUED = "queued"
    WORKING = "working"
    IN_SESSION = "in-session"
    REWORK = "rework"
    LANDING = "landing"
    READY = "ready"
    WAITING = "waiting"
    ASSUMED_DONE = "assumed-done"
    NOT_MINE = "not-mine"
    DEFERRED = "deferred"
    DONE = "done"


OPEN = "open"
WAITING_ON_REVIEWER = "waiting_on_reviewer"
ASSUMED_DONE = "assumed_done"
NOT_MINE = "not_mine"
CONFIRMED = "confirmed"
DEFERRED = "deferred"
REJECTED = "rejected"
RESOLVED = "resolved"
REMOVED = "removed"
UNREADABLE = "unreadable"
DRAFT = "draft"
ENROLLED = "enrolled"
DISCARDED = "discarded"

ROLE_AUTHOR = "author"
ROLE_REVIEWER = "reviewer"

WAKE_MANUAL = "manual"
WAKE_CI = "ci"
WAKE_PR_PREFIX = "pr:"
WAKE_PUSH_PREFIX = "push:"

QUEUED = "queued"
RUNNING = "running"
DECLINED = "declined"
FAILED = "failed"
PROPOSED = "proposed"
IN_SESSION = "in_session"
LANDING = "landing"
LANDED = "landed"
ABSENT = "absent"

WITHDRAWN = "stopped before it finished"

FILE = "file"
PICK = "pick"
PUSH = "push"
ANSWER = "answer"
MARK_RESOLVED = "resolve"

MAX_ATTEMPTS = 3

RUN_KINDS = (OperationKind.FIRST, OperationKind.REBASE, OperationKind.REWORK, OperationKind.RETRY)

FIX_RUNS = (*RUN_KINDS, OperationKind.FILE)

IN_FLIGHT = (OperationState.PENDING, OperationState.RUNNING)

SETTLED = (PROPOSED, LANDING, LANDED)


class UnreadableRecord(Exception):
    """A record the domain cannot interpret.

    Raised by the records adapter for a file that will not parse, and by
    state_of for one that parses into a shape the state machine has no
    answer for. One type, because the collection read answers for both the
    same way: the key goes in its unreadable array and the board draws
    what it likes for it.
    """


@dataclass(frozen=True)
class Step:
    text: str
    file: str | None = None
    done: bool = False


@dataclass(frozen=True)
class Anchor:
    is_outdated: bool = False
    side: Side | None = None
    start_line: int | None = None
    start_side: Side | None = None
    original_line: int | None = None
    original_start_line: int | None = None
    original_commit: str | None = None


class ReviewState(Enum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes-requested"
    COMMENTED = "commented"
    DISMISSED = "dismissed"
    PENDING = "pending"

    @property
    def is_verdict(self) -> bool:
        return self is ReviewState.APPROVED or self is ReviewState.CHANGES_REQUESTED


@dataclass(frozen=True)
class Comment:
    id: int | None = None
    author: str = ""
    body: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    author_name: str = ""
    review_state: ReviewState | None = None


@dataclass(frozen=True)
class PointedLine:
    file: str = ""
    line: int | None = None
    text: str = ""


@dataclass(frozen=True)
class Brief:
    note: str = ""
    pointed: tuple[PointedLine, ...] = ()
    include: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.note.strip() and not self.pointed


@dataclass(frozen=True)
class Run:
    kind: OperationKind = OperationKind.FIRST
    onto: Sha | None = None
    conflict: str | None = None
    brief: Brief | None = None

    @property
    def is_rebase(self) -> bool:
        return self.kind == OperationKind.REBASE


@dataclass(frozen=True)
class Fix:
    state: str = QUEUED
    run: Run = field(default_factory=Run)
    attempts: int = 0
    started_at: str | None = None
    base_sha: Sha | None = None
    thread_sha: Sha | None = None
    tests: str | None = None
    tests_note: str | None = None
    agent_note: str | None = None
    classification: Classification | None = None
    reason: str | None = None
    plan: tuple[Step, ...] = ()
    summary: str | None = None
    confidence: ConfidenceLevel | None = None
    confidence_note: str | None = None
    steps: frozenset[str] = frozenset()
    landed_base: Sha | None = None
    landed_sha: Sha | None = None
    push_error: str | None = None
    reply_error: str | None = None
    decision_error: str | None = None
    reply_note: str | None = None
    pending_reply: str = ""
    resolve_on_land: bool = False
    kind: ProposalKind = ProposalKind.COMMIT
    reply: str | None = None
    ticket: Ticket | None = None
    ticket_key: str | None = None
    ticket_url: str | None = None
    file_error: str | None = None

    @property
    def is_proposed(self) -> bool:
        return self.state == PROPOSED

    @property
    def is_declined(self) -> bool:
        return self.state == DECLINED

    @property
    def has_failed(self) -> bool:
        return self.state == FAILED

    @property
    def is_settled(self) -> bool:
        return self.state in SETTLED

    @property
    def holds_a_proposal(self) -> bool:
        return self.is_settled or (self.run.kind == OperationKind.FILE
                                   and self.state in (QUEUED, RUNNING))

    @property
    def commits(self) -> tuple[Sha, Sha] | None:
        if self.landed_base is not None and self.landed_sha is not None:
            return self.landed_base, self.landed_sha
        if self.base_sha is not None and self.thread_sha is not None:
            return self.base_sha, self.thread_sha
        return None

    @property
    def picked(self) -> bool:
        return PICK in self.steps

    @property
    def pushed(self) -> bool:
        return PUSH in self.steps

    @property
    def answered(self) -> bool:
        return ANSWER in self.steps

    @property
    def filed(self) -> bool:
        return FILE in self.steps


@dataclass(frozen=True)
class Operation:
    """One piece of work asked of a thread, or started on it by the board.

    The record keeps every one it has seen, oldest first, so an id handed to
    a client goes on naming the same work after the thread has moved on to
    the next. `text` is whatever words the work carried: a reply, the note a
    park was left with, the steer a session was opened with.
    """

    id: str
    kind: OperationKind
    state: OperationState = OperationState.PENDING
    requested_at: str | None = None
    settled_at: str | None = None
    reason: str | None = None
    reason_code: ReasonCode | None = None
    attempts: int = 0
    text: str = ""
    delete_comment: bool = False
    until: str | None = None
    stopped: str | None = None
    brief: Brief | None = None
    posted_comment: int | None = None
    anchor: Location | None = None
    review: str | None = None
    github_node_id: str | None = None

    @property
    def is_run(self) -> bool:
        return self.kind in RUN_KINDS

    @property
    def holds_a_run(self) -> bool:
        return self.is_run or self.kind == OperationKind.START_SESSION

    @property
    def in_flight(self) -> bool:
        return self.state in IN_FLIGHT

    @property
    def attempts_allowed(self) -> int:
        return MAX_ATTEMPTS

    @property
    def wakes_on(self) -> str:
        return self.until or WAKE_MANUAL


@dataclass(frozen=True)
class Landing:
    kind: ProposalKind | None = None
    filed: bool = False
    picked: bool = False
    pushed: bool = False
    answered: bool = False
    landed_base: Sha | None = None
    landed_sha: Sha | None = None
    reply_note: str | None = None
    ticket_key: str | None = None
    ticket_url: str | None = None


@dataclass(frozen=True)
class OperationView:
    operation: Operation
    current: bool = False
    text: str = ""
    posted_comment: int | None = None
    brief: Brief | None = None
    plan: tuple[Step, ...] = ()
    onto: Sha | None = None
    conflict: str | None = None
    classification: Classification | None = None
    proposal: str | None = None
    landing: Landing = field(default_factory=Landing)

    @property
    def steps_done(self) -> int | None:
        return sum(1 for step in self.plan if step.done) if self.plan else None

    @property
    def steps_total(self) -> int | None:
        return len(self.plan) or None


@dataclass(frozen=True)
class Proposal:
    id: str
    kind: ProposalKind
    reply: str | None
    ticket: Ticket | None
    operation: str | None
    created_at: str | None
    base_sha: Sha | None
    thread_sha: Sha | None
    commits: tuple[Sha, Sha] | None
    summary: str | None
    agent_note: str | None
    confidence: ConfidenceLevel | None
    confidence_note: str | None
    tests: str | None
    tests_note: str | None


@dataclass(frozen=True)
class Conversation:
    key: str
    github_node_id: str | None = None
    state: str = OPEN
    role: str = ROLE_AUTHOR
    comment_id: int | None = None
    comment_type: str = ""
    author: str = ""
    reviewer_name: str = ""
    review_state: ReviewState | None = None
    path: str | None = None
    line: int | None = None
    start_line: int | None = None
    start_side: Side | None = None
    side: Side | None = None
    body: str = ""
    comments: tuple[Comment, ...] = ()
    comment_created_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = field(default=None, compare=False)
    gist: str = ""
    is_outdated: bool = False
    original_line: int | None = None
    original_start_line: int | None = None
    original_commit: str | None = None
    comment_deleted: bool = False
    deleted_by_board: bool = False
    github_resolved: bool | None = None
    github_resolved_at: str | None = None
    reopened: bool = False
    before_reply: str = ""
    replied_during_run: bool = False
    state_changed_at: str | None = None
    decidable_at: str | None = None
    seen_at: str | None = None
    closing_reply: str = ""
    closing_reply_id: int | None = None
    closing_into: str | None = None
    closing_on_github: bool = False
    closing_without_thumbs_up: bool = False
    wake_on: str | None = None
    defer_note: str = ""
    approved_reply: str = ""
    approved_reply_id: int | None = None
    panel_reply_ids: tuple[int, ...] = ()
    posted_comment_keys: tuple[str, ...] = ()
    operations: tuple[Operation, ...] = ()
    fix: Fix = field(default_factory=Fix)
    mention: bool = False
    verdict: ThreadVerdict | None = None
    verdict_for: str | None = None
    verdict_asked_for: str | None = None
    verdict_asks: int = 0
    verdict_asked_at: str | None = None
    unread: bool = False

    @property
    def is_removed(self) -> bool:
        return self.state == REMOVED

    @property
    def is_unreadable(self) -> bool:
        return self.state == UNREADABLE

    @property
    def run_holder(self) -> Operation | None:
        return next((operation for operation in reversed(self.operations)
                     if operation.holds_a_run), None)

    @property
    def standing(self) -> ConversationState:
        return state_of(self)

    @property
    def awaits_you(self) -> bool:
        standing = state_of(self)
        return standing is ConversationState.READY or (
            self.reopened
            and standing in (ConversationState.QUEUED, ConversationState.WORKING))

    @property
    def location(self) -> Location | None:
        if not self.path or self.line is None:
            return None
        return Location(path=self.path, line=self.line, start_line=self.start_line,
                        start_side=self.start_side, side=self.side or Side.AFTER)

    @property
    def latest_approval(self) -> Operation | None:
        return next((operation for operation in reversed(self.operations)
                     if operation.kind == OperationKind.APPROVE), None)

    @property
    def proposal(self) -> Proposal | None:
        fix = self.fix
        if not fix.holds_a_proposal:
            return None
        producer = _proposal_producer(self)
        return Proposal(
            id=_proposal_id(self), kind=fix.kind, reply=fix.reply, ticket=fix.ticket,
            operation=None if producer is None else producer.id,
            created_at=None if producer is None else producer.settled_at,
            base_sha=fix.base_sha, thread_sha=fix.thread_sha, commits=fix.commits,
            summary=fix.summary, agent_note=fix.agent_note,
            confidence=fix.confidence, confidence_note=fix.confidence_note,
            tests=fix.tests, tests_note=fix.tests_note)

    @property
    def posted_by_board(self) -> frozenset[int]:
        return frozenset(
            reply_id for reply_id in (self.closing_reply_id, self.approved_reply_id,
                                      *self.panel_reply_ids)
            if reply_id)

    @property
    def views(self) -> tuple[OperationView, ...]:
        holder, approval = self.run_holder, self.latest_approval
        held = None if holder is None else holder.id
        approved = None if approval is None else approval.id
        return tuple(_view_of(self, operation, operation.id in (held, approved))
                     for operation in self.operations)


def _proposal_producer(conversation: Conversation) -> Operation | None:
    holder = conversation.run_holder
    if (not conversation.fix.holds_a_proposal or holder is None
            or holder.state != OperationState.APPLIED):
        return None
    return holder


def _proposal_id(conversation: Conversation) -> str:
    producer = _proposal_producer(conversation)
    return f"{conversation.key if producer is None else producer.id}.proposal"


def _view_of(conversation: Conversation, operation: Operation, current: bool) -> OperationView:
    fix = conversation.fix
    if not current:
        if operation.kind == OperationKind.APPROVE:
            return OperationView(operation, text=operation.text)
        return OperationView(operation, text=operation.text,
                             posted_comment=operation.posted_comment, brief=operation.brief)
    if operation.kind == OperationKind.APPROVE:
        return OperationView(
            operation, current=True,
            text=operation.text or conversation.approved_reply,
            posted_comment=conversation.approved_reply_id,
            proposal=_proposal_id(conversation),
            landing=Landing(kind=fix.kind, filed=fix.filed, picked=fix.picked, pushed=fix.pushed,
                            answered=fix.answered, landed_base=fix.landed_base,
                            landed_sha=fix.landed_sha, reply_note=fix.reply_note,
                            ticket_key=fix.ticket_key, ticket_url=fix.ticket_url))
    produced = _proposal_producer(conversation) is not None
    return OperationView(
        operation, current=True, text=operation.text,
        posted_comment=operation.posted_comment,
        brief=operation.brief or fix.run.brief,
        plan=fix.plan, onto=fix.run.onto, conflict=fix.run.conflict,
        classification=fix.classification,
        proposal=_proposal_id(conversation) if produced else None)


_STATE_OF_RECORD_STATE = {
    WAITING_ON_REVIEWER: ConversationState.WAITING,
    ASSUMED_DONE: ConversationState.ASSUMED_DONE,
    NOT_MINE: ConversationState.NOT_MINE,
    CONFIRMED: ConversationState.DONE,
    DEFERRED: ConversationState.DEFERRED,
    REJECTED: ConversationState.DONE,
    RESOLVED: ConversationState.DONE,
    REMOVED: ConversationState.READY,
    DRAFT: ConversationState.DRAFT,
    ENROLLED: ConversationState.ENROLLED,
    DISCARDED: ConversationState.DONE,
}

_STATE_OF_FIX = {
    QUEUED: ConversationState.QUEUED,
    RUNNING: ConversationState.WORKING,
    IN_SESSION: ConversationState.IN_SESSION,
    LANDING: ConversationState.LANDING,
    LANDED: ConversationState.DONE,
    ABSENT: ConversationState.READY,
    PROPOSED: ConversationState.READY,
    DECLINED: ConversationState.READY,
    FAILED: ConversationState.READY,
}

_STATE_OF_RUN = {
    OperationKind.REBASE: ConversationState.LANDING,
    OperationKind.FILE: ConversationState.LANDING,
    OperationKind.REWORK: ConversationState.REWORK,
}


def _landing_failed(fix: Fix) -> bool:
    return fix.state == LANDING and bool(fix.push_error or fix.reply_error
                                         or fix.file_error)


def state_of(conversation: Conversation) -> ConversationState:
    """The contract's ConversationState for a thread.

    reopened stays the boolean the record already carries and says nothing
    about the work, so it is not folded into the answer.

    An unreadable record has no state to answer with: it has no kind, no
    comments and no operations. Its key goes in the collection's unreadable
    array instead, so nothing calls this on one.
    """
    if conversation.state == UNREADABLE:
        raise UnreadableRecord(
            f"{conversation.key} is an unreadable record")
    by_record = _STATE_OF_RECORD_STATE.get(conversation.state)
    if by_record is not None:
        return by_record
    fix = conversation.fix
    if fix.state in (QUEUED, RUNNING):
        by_run = _STATE_OF_RUN.get(fix.run.kind)
        if by_run is not None:
            return by_run
    if _landing_failed(fix):
        return ConversationState.READY
    mapped = _STATE_OF_FIX.get(fix.state)
    if mapped is None:
        raise UnreadableRecord(
            f"{conversation.key} holds a fix state the machine has no "
            f"answer for: {fix.state}")
    return mapped
