from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel, StringConstraints

from github_orchestrator import conversation as domain
from github_orchestrator.board_api.interface import CloneState, WallGroup, WriteState
from github_orchestrator.conversation import (
    Classification,
    ConfidenceLevel,
    ConversationState,
    OperationKind,
    OperationState,
    ReasonCode,
)
from github_orchestrator.domain import AuthorKind, HubState, Side


class ErrorCode(StrEnum):
    """Why a request was refused, as the contract's closed vocabulary.

    The sentence beside it is the domain's own words and changes freely; this
    is what a client branches on. Most codes are the review threads' own
    refusals, passed through; the rest are the board's, refusing at HTTP
    before the domain is asked.

    CONFIRM_AGAIN is the domain asking for the same verb a second time
    rather than turning it down: nothing failed, and repeating the request
    is what clears it.

    INTERNAL_REFUSAL is not a general-purpose fallback. It carries the
    refusals that cross no HTTP boundary, and a refusal a client can reach
    gets a code of its own.

    MALFORMED_REQUEST is the request itself not parsing, or a parameter
    outside its declared type, as distinct from a request that parses and
    the domain then refuses.

    FOREIGN_ORIGIN is a write that did not come from the board's own page:
    addressed to another host, or sent by another site's.

    MANAGER_STARTING is the PR manager not having finished its first tick,
    so it has no status to give yet. It clears within a tick.

    WATCHER_STARTING is the hub serving before the watcher has finished its
    first cycle, so it does not know yet which pull requests it holds. It
    clears within a cycle.

    WATCHER_FAILING is the hub serving while no cycle has succeeded and the
    last one failed; the detail is the watcher's last error.

    NOT_WATCHING is the hub serving in setup or broken state, so the watcher
    polls nothing; the detail is what is wrong with the config.

    NOT_FROZEN is the hub asked to release a pull request whose manager is
    not frozen on the wrong branch, so there is nothing to let go of.

    BOARD_UNREACHABLE is the hub holding a pull request whose board does not
    answer: it has none yet, it is starting, its manager is frozen or down.

    TERMINAL_REFUSED is the PR manager not opening a terminal command: the
    worktree is frozen on another branch, or the command could not start.

    MANAGER_REFUSED is a command for the PR manager that its last status
    already rules out: the worktree is frozen on another branch, agents are
    disabled, or an agent is already running. The detail says which.

    NO_GH_TOKEN is gh holding no token for the login the setup screen asked
    about; the detail says to run `gh auth login`.

    REPO_NOT_VISIBLE is a repo typed on the setup screen that the login
    cannot see, or that does not exist.

    SETUP_REFUSED is a setup write refused before anything was written or
    cloned, one error per field, each naming its field.

    NOT_BROKEN is the setup screen asking to move aside a config that parses,
    which is never moved from the page.

    SERVER_ERROR is the board failing in a way nothing anticipated. Its
    traceback is in the PR manager's log under the board process's pid.
    """

    NOT_FOUND = "not-found"
    OPERATION_OUTSTANDING = "operation-outstanding"
    NOTHING_IN_FLIGHT = "nothing-in-flight"
    WORK_IN_FLIGHT = "work-in-flight"
    NO_PROPOSAL = "no-proposal"
    PROPOSAL_EXISTS = "proposal-exists"
    NOTHING_COMMITTED = "nothing-committed"
    ALREADY_CLOSED = "already-closed"
    PARKED = "parked"
    NOT_PARKED = "not-parked"
    STILL_A_DRAFT = "still-a-draft"
    NOT_A_DRAFT = "not-a-draft"
    ALREADY_ENROLLED = "already-enrolled"
    CONFIRM_AGAIN = "confirm-again"
    ANCHOR_NOT_IN_DIFF = "anchor-not-in-diff"
    EMPTY_BRIEF = "empty-brief"
    MALFORMED_REQUEST = "malformed-request"
    EMPTY_BODY = "empty-body"
    BODY_TOO_LONG = "body-too-long"
    COMMENT_GONE = "comment-gone"
    NOT_DELETABLE = "not-deletable"
    BAD_WAKE_CONDITION = "bad-wake-condition"
    PRECONDITION_FAILED = "precondition-failed"
    UNREADABLE_RECORD = "unreadable-record"
    RANGE_INVERTED = "range-inverted"
    RANGE_TOO_WIDE = "range-too-wide"
    NOT_TEXT = "not-text"
    NO_SUCH_COMMIT = "no-such-commit"
    NO_SUCH_PATH = "no-such-path"
    REVIEW_IN_FLIGHT = "review-in-flight"
    NOTHING_ENROLLED = "nothing-enrolled"
    GIT_FAILED = "git-failed"
    GITHUB_REJECTED = "github-rejected"
    AGENTS_DISABLED = "agents-disabled"
    INTERNAL_REFUSAL = "internal-refusal"
    FOREIGN_ORIGIN = "foreign-origin"
    MANAGER_STARTING = "manager-starting"
    WATCHER_STARTING = "watcher-starting"
    WATCHER_FAILING = "watcher-failing"
    NOT_WATCHING = "not-watching"
    NOT_FROZEN = "not-frozen"
    BOARD_UNREACHABLE = "board-unreachable"
    TERMINAL_REFUSED = "terminal-refused"
    MANAGER_REFUSED = "manager-refused"
    NO_GH_TOKEN = "no-gh-token"
    REPO_NOT_VISIBLE = "repo-not-visible"
    SETUP_REFUSED = "setup-refused"
    NOT_BROKEN = "not-broken"
    SERVER_ERROR = "server-error"


_ERROR_CODES = {code: ErrorCode(code.value) for code in domain.ErrorCode}


def error_code(code: domain.ErrorCode) -> ErrorCode:
    return _ERROR_CODES[code]


class DiffSide(StrEnum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"


_DIFF_SIDES: dict[Side, DiffSide] = {Side.BEFORE: DiffSide.LEFT, Side.AFTER: DiffSide.RIGHT}


def diff_side(side: Side | None) -> DiffSide | None:
    return None if side is None else _DIFF_SIDES[side]


def side_of(word: DiffSide) -> Side:
    return next(side for side, spelled in _DIFF_SIDES.items() if spelled == word)


Sha = Annotated[str, StringConstraints(pattern="^[0-9a-f]{7,40}$")]

ThreadKey = Annotated[str, StringConstraints(pattern="^[A-Za-z0-9_-]+$")]

WakeCondition = Annotated[
    str, StringConstraints(pattern="^(manual|ci|push|pr:[0-9]+)$"),
    Field(description="What brings a parked thread back: `manual` for "
                      "nothing but a hand, `ci` for the checks going green, "
                      "`push` for the next push to the branch, `pr:<number>` "
                      "for another pull request closing."),
]


class PullRequest(BaseModel):
    """The pull request this board serves."""

    repo: str
    number: int
    title: str | None
    html_url: str = Field(
        description="Where the pull request is on github.com. Here for the "
                    "same reason a comment's `html_url` is: the anchor scheme "
                    "is GitHub's, not this domain's, so the board builds it "
                    "rather than making the front end learn someone else's "
                    "URL format.")
    base_branch: str | None = Field(
        description="What the pull request merges into.")
    branch: str | None = Field(
        description="The pull request's own branch, which an approve pushes to.")
    head_sha: Sha | None = Field(
        description="The branch's current head. A `rebase` operation carries "
                    "`onto`, and without this there is nothing to compare it "
                    "against.")


class ErrorDetail(BaseModel):
    status: int
    code: ErrorCode
    detail: str = Field(
        description="The domain's own sentence, in its own words. A client "
                    "branches on `code` and displays this.")


class Errors(BaseModel):
    """Every error answers in this shape, whatever the status."""

    errors: Annotated[list[ErrorDetail], Field(min_length=1)]


class Person(BaseModel):
    """Someone who has interacted with the pull request."""

    login: str
    name: str | None = Field(
        description="Null where GitHub has given the board no display name. "
                    "The board stores no people of its own; this is what the "
                    "records happen to have been told.")


class PersonList(RootModel[list[Person]]):
    """Everyone the records name, by login."""


class WatcherHealth(BaseModel):
    """How the watcher's polling is going, as its heartbeat and its record of
    failed cycles say. The hub runs in the watcher's own process, so a hub that
    answers has a watcher running."""

    polled_at: str | None = Field(
        description="When the last good poll ended. Null before the first.")
    next_poll_at: str | None = Field(
        description="When the next poll is due, a poll interval after the last "
                    "good one; in the past once it is late. Null before the first.")
    overdue: bool = Field(
        description="No good poll for more than two poll intervals and two "
                    "minutes' grace, so a cycle slowed by load is not an alarm.")
    last_error: str | None = Field(
        description="Why the last cycle failed, while cycles keep failing. Null "
                    "while they succeed.")
    fix: str | None = Field(
        description="What to do about `last_error`, in plain words, where the watcher "
                    "recognises it: gh holding no token for the account, or the "
                    "account unable to see a watched repo. Null otherwise.")


class NewestRelease(BaseModel):
    """The newest release the daily release check found."""

    version: str
    checked_at: str
    newer: bool = Field(
        description="Whether this release is newer than the version this hub runs, which "
                    "is when the top bar shows Update available.")


class Health(BaseModel):
    """That this server is up, which process it is, and what it serves."""

    status: Literal["ok"]
    pid: int = Field(
        description="The process every line this server writes to its log is "
                    "stamped with: the PR manager's for a board, the watcher's "
                    "for the hub.")
    serves: Literal["board", "hub"] = Field(
        description="`board` for one pull request's board, `hub` for the "
                    "watcher's list of every pull request. The page reads it "
                    "to know which routes this server answers.")
    hub_url: str = Field(
        description="Where the hub is, for a board to link back to it.")
    font_problem: str | None = Field(
        description="Why the board's own face is not served when `board_font_dir` "
                    "names a directory that cannot be listed or holds no "
                    "<Family>-<Style>.otf face, for the page to say so; null when the faces "
                    "are served or no directory is configured.")
    state: HubState | None = Field(
        description="The hub's state: `setup` with no config, no account or no repos, "
                    "serving the hub alone; `watching` polling GitHub with a complete "
                    "config; `broken` with a config that does not parse, serving the hub "
                    "alone. It changes only by a restart. Null from a board.")
    version: str | None = Field(
        description="The installed github-orchestrator's version. Null from a board, "
                    "and where the package carries none.")
    watcher: WatcherHealth | None = Field(
        description="How the watcher's polling is going. Null from a board.")
    newest_release: NewestRelease | None = Field(
        description="The newest release the daily release check found. Null from a "
                    "board, before the first check, when no check has ever succeeded, and "
                    "when check_for_updates is false.")


class ClientError(BaseModel):
    """An error the board's own page hit, for the agent manager's log."""

    where: Annotated[str, StringConstraints(min_length=1, max_length=200)] = Field(
        description="Which part of the page was working when it failed.")
    message: Annotated[str, StringConstraints(max_length=4000)]
    stack: Annotated[str | None, StringConstraints(max_length=20000)] = None


class ThreadKind(StrEnum):
    """What kind of thing this thread is, which is what decides whether a
    reply can be threaded under it. `draft` is the board's own: a comment
    being composed, with nothing on GitHub for it yet. `pr-body` is the pull
    request's description, held as a thread when it mentions the viewer."""

    DRAFT = "draft"
    REVIEW = "review"
    ISSUE = "issue"
    REVIEW_SUMMARY = "review-summary"
    PR_BODY = "pr-body"


class ReviewVerdict(StrEnum):
    """What a sent review says overall. GitHub's `event` values; `body` is
    required for the two that are not an approval."""

    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    COMMENT = "COMMENT"


class ReviewState(StrEnum):
    """GitHub's own vocabulary, passed through."""

    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    COMMENTED = "COMMENTED"
    DISMISSED = "DISMISSED"
    PENDING = "PENDING"


_REVIEW_STATES = {
    domain.ReviewState.APPROVED: ReviewState.APPROVED,
    domain.ReviewState.CHANGES_REQUESTED: ReviewState.CHANGES_REQUESTED,
    domain.ReviewState.COMMENTED: ReviewState.COMMENTED,
    domain.ReviewState.DISMISSED: ReviewState.DISMISSED,
    domain.ReviewState.PENDING: ReviewState.PENDING,
}

_VERDICTS = {
    domain.Verdict.APPROVE: ReviewVerdict.APPROVE,
    domain.Verdict.REQUEST_CHANGES: ReviewVerdict.REQUEST_CHANGES,
    domain.Verdict.COMMENT: ReviewVerdict.COMMENT,
}


def review_state(state: domain.ReviewState | None) -> ReviewState | None:
    return None if state is None else _REVIEW_STATES[state]


def review_verdict(verdict: domain.Verdict) -> ReviewVerdict:
    return _VERDICTS[verdict]


def verdict_of(verdict: ReviewVerdict) -> domain.Verdict:
    return next(ours for ours, spelled in _VERDICTS.items() if spelled is verdict)


class Anchor(BaseModel):
    """What the thread hangs off in the diff, and where that has moved to
    since. It sits on the thread rather than the comment because every
    comment in a review thread shares one position, and it is the thread
    that goes outdated."""

    path: str | None = Field(
        description="Null on a thread about the pull request at large.")
    line: int | None = Field(
        description="Where the line is now. Null once the thread has gone "
                    "outdated.")
    start_line: int | None = Field(
        description="The first line, where the thread spans several.")
    start_side: DiffSide | None = Field(
        description="Which side of the diff the first line is on. A range may "
                    "start on the old side and end on the new.")
    side: DiffSide | None = Field(
        description="Which side of the diff the line is on. GitHub needs it "
                    "when a comment is posted. Null on a thread polled "
                    "before the board kept it, and on one about the pull "
                    "request at large.")
    original_line: int | None
    original_start_line: int | None
    original_commit: Sha | None = Field(
        description="The commit the thread was written against.")
    is_outdated: bool = Field(
        description="The code the thread was written on has changed "
                    "underneath it.")


class CommentSummary(BaseModel):
    """A comment as a conversation carries it: enough to order the thread,
    name who spoke and tell a review apart from a reply. The body is its own
    read."""

    id: int | None = Field(
        description="GitHub's id. Null on a draft's comment, and on a "
                    "stand-in the board made for a thread GitHub gave it no "
                    "comment for.")
    author: str = Field(description="A login. Resolve on `/people`.")
    created_at: str | None
    review_state: ReviewState | None = Field(
        description="Set where the comment came with a review. Null on an "
                    "ordinary reply and on a draft.")


class Comment(CommentSummary):
    """One comment on a thread, with what was written."""

    body: str = Field(
        description="Markdown. Whatever renders it must sanitise it.")
    updated_at: str | None
    html_url: str | None = Field(
        description="Where the comment is on github.com. Null where it is "
                    "not there yet, which is every draft. The board builds "
                    "it rather than making the front end learn GitHub's URL "
                    "format.")
    posted_by_board: bool = Field(
        description="The board posted it, rather than a person on "
                    "github.com.")
    deleted: bool = Field(description="GitHub no longer has it.")
    deleted_by_board: bool = Field(
        description="The board removed it, as part of an approve, resolve or "
                    "reject.")


class CommentList(RootModel[list[Comment]]):
    """The thread's comments, oldest first."""


class ProposalKind(StrEnum):
    COMMIT = "commit"
    REPLY = "reply"
    TICKET = "ticket"


class OperationSummary(BaseModel):
    """An operation as a conversation carries it. The same shape whatever the
    kind; a rework's brief or a landing's progress is on the operation itself.

    `last_action` and `progress` are deliberately absent. They change every
    second, and on an embedded summary they would move the conversation's
    etag on every agent heartbeat, so the board's poll would never come back
    304 while anything was running. They are on `/operations`.
    """

    id: str
    kind: OperationKind
    state: OperationState
    reason: str | None = Field(
        description="Why it was refused or put back, in the domain's own "
                    "words.")
    reason_code: ReasonCode | None = Field(
        description="The same refusal as a token. Branch on this, show "
                    "`reason`.")
    requested_at: str | None
    settled_at: str | None
    steps_done: int | None = Field(
        description="How many of the agent's plan steps are finished. Null "
                    "where there is no plan. Written a handful of times per "
                    "run, so it does not disturb the etag the way "
                    "`last_action` would.")
    steps_total: int | None
    attempts: int | None = Field(
        description="Attempts already spent. Null on a kind that does not "
                    "attempt. Here as well as on the operation because the "
                    "conversation collection is the only read that draws "
                    "\"attempt 2 of 3\", and it embeds this summary.")
    attempts_allowed: int | None = Field(
        description="How many the domain gives a run, so the card does not "
                    "hardcode a constant only the server knows.")
    lands: ProposalKind | None = Field(
        description="What the thread's current approve lands: a commit, a reply "
                    "or a ticket. Null on every other operation, so a card can say "
                    "how the thread closed from the summary alone.")
    ticket_key: str | None = Field(
        description="The key of the ticket the current approve filed, once filed.")


class RecordState(StrEnum):
    """Where a thread's record stands beneath the machine's `state`: whose
    turn it is, or whether it was ever sent."""

    OPEN = "open"
    WAITING_ON_REVIEWER = "waiting_on_reviewer"
    ASSUMED_DONE = "assumed_done"
    NOT_MINE = "not_mine"
    CONFIRMED = "confirmed"
    DEFERRED = "deferred"
    REJECTED = "rejected"
    RESOLVED = "resolved"
    REMOVED = "removed"
    DRAFT = "draft"
    ENROLLED = "enrolled"
    DISCARDED = "discarded"


class Conversation(BaseModel):
    """One comment thread, or one draft. Stored facts, plus its state, plus
    its comments and operations as summaries so a card can be drawn and read
    for its standing from the collection alone."""

    key: ThreadKey
    github_node_id: str | None = Field(
        description="GitHub's id for the thread. Null on a draft, and filled "
                    "in when the draft is posted. The `key` does not change "
                    "at that moment.")
    kind: ThreadKind
    state: ConversationState
    state_changed_at: str | None = Field(
        description="When the machine last moved this thread. One of the two "
                    "clocks the collection is ordered by; the other is the "
                    "newest comment's `created_at`. Null on every thread that "
                    "has not moved since the stamp was introduced, which is "
                    "why the order tolerates a null here.")
    reopened: bool = Field(
        description="Someone spoke on this thread after you had. A flag "
                    "rather than a member of `state`, because a thread can be "
                    "reopened and have work in flight at once.")
    etag: str = Field(
        description="This thread's revision. Send it as `If-Match` on an "
                    "operation. A field rather than only a header so that a "
                    "client holding the whole collection can act on any "
                    "member of it, in the manner of AIP-154.")
    github_removed: bool = Field(
        description="GitHub no longer has the thread.")
    github_resolved: bool | None = Field(
        description="Whether GitHub calls the thread resolved. Null where the "
                    "board has not been told, and on a draft.")
    github_resolved_at: str | None
    created_at: str | None = Field(
        description="When the board first made a record for this thread.")
    anchor: Anchor
    gist: str | None = Field(
        description="The thread in a line, as an agent wrote it. Null until "
                    "one has.")
    comments: list[CommentSummary] = Field(
        description="Every comment on the thread, oldest first. The bodies "
                    "are on `/conversations/{key}/comments`.")
    operations: list[OperationSummary] = Field(
        description="Everything the board has recorded about work on this "
                    "thread, oldest first. The state machine folds this into "
                    "`state`.")
    mention: bool = Field(
        description="On a pull request the viewer did not write, the thread "
                    "holds a mention of the viewer they have not answered.")
    updated_at: str | None = Field(
        description="When the record was last saved. Of two copies of a "
                    "thread the one with the later stamp is newer. Left out "
                    "of `etag`, which moves only with what a card shows. Null "
                    "on a record saved before the stamp was written.")
    author_kind: AuthorKind = Field(
        description="Who opened the thread: the viewer, another person, or "
                    "one of the review bots. The only list of the bots.")
    unread: bool = Field(
        description="On a pull request the viewer did not write, the thread is "
                    "the viewer's move because no verdict has placed it yet: it "
                    "has a newest comment nobody has read for them. False "
                    "everywhere else.")
    record_state: RecordState


class ConversationList(BaseModel):
    """The threads, and the keys of the records that would not parse.

    An envelope rather than a bare array because one unreadable record must
    neither disappear from the board nor fail the read of the other forty.
    """

    conversations: list[Conversation] = Field(
        description="Ordered, newest first, by whichever is later: "
                    "`state_changed_at` or the newest comment's "
                    "`created_at`. Group by `state` and the order inside each "
                    "group is the order given here.")
    unreadable: list[ThreadKey] = Field(
        description="The keys whose records would not parse. They are keys "
                    "and nothing else: a record that will not parse has no "
                    "kind, no state and no comments. Reading one of these at "
                    "`/conversations/{key}` is the `unreadable-record` "
                    "refusal.")
    listed_at: str = Field(
        description="When the board read the records: the list names every "
                    "thread as of then, so a thread saved since may be "
                    "missing from it. Left out of the tag.")


class PlanStep(BaseModel):
    text: str
    file: str | None
    done: bool


class PointedLine(BaseModel):
    """A line the operator singled out, with its text, so the agent does not
    have to read the file to know what was meant."""

    file: str
    line: int | None
    text: str


class Brief(BaseModel):
    """What an operator sends a proposal back with. Also the body of
    `:rework`."""

    note: str = Field(description="What to change and why.")
    pointed: list[PointedLine] = Field(
        description="The lines the operator pointed the agent at.")
    include: list[str] = Field(
        description="Logins whose comments go into the agent's context along "
                    "with the note.")


class LandingSteps(BaseModel):
    """How far an approve got. A commit is picked, pushed and answered; a ticket
    is filed and answered; a reply is only answered."""

    filed: bool
    picked: bool
    pushed: bool
    answered: bool


class OperationEnvelope(BaseModel):
    """The fields every operation carries, whatever its kind."""

    id: str
    conversation: ThreadKey | None = Field(
        description="The thread this operation is about. Null on work about "
                    "the whole review.")
    kind: OperationKind
    state: OperationState
    reason: str | None
    reason_code: ReasonCode | None
    requested_at: str | None
    settled_at: str | None


class FixOperation(OperationEnvelope):
    """An agent run. `first` when the thread appeared, `rebase` when the head
    moved under it, `rework` when it was sent back with a brief, `retry` when
    its attempts were refreshed. Leaves a proposal behind when it succeeds."""

    kind: Literal[OperationKind.FIRST, OperationKind.REBASE,
                  OperationKind.REWORK, OperationKind.RETRY]
    attempts: int
    attempts_allowed: int
    last_action: str | None = Field(
        description="The last thing the agent reported doing. Changes "
                    "constantly, which is why it is here and not on the "
                    "summary.")
    progress: str | None = Field(
        description="What git says about the agent's worktree — how far "
                    "ahead of its base it is. Null when there is nothing to "
                    "report or no worktree.")
    plan: list[PlanStep] = Field(
        description="The changes the agent said it would make, ticked off as "
                    "it goes. On the operation rather than the proposal, "
                    "because a running agent has no proposal yet.")
    onto: Sha | None = Field(
        description="The head a `rebase` run is rebasing onto.")
    conflict: str | None = Field(
        description="What conflicted, when a pick sent the run back to "
                    "rebase.")
    brief: Brief | None = Field(
        description="What a `rework` run was sent back with.")
    proposal: str | None = Field(
        description="What the run left behind, once it has.")
    classification: Classification | None = Field(
        description="How the agent classified the comment when it declined.")


class SessionOperation(OperationEnvelope):
    """An interactive agent session on the thread's worktree. `running` from
    the moment the pane opens until the operator tells the agent in the session
    to update the board."""

    kind: Literal[OperationKind.START_SESSION]
    steer: str | None = Field(
        description="What the session was told on the way in. Null where "
                    "it was opened with nothing to say.")
    last_action: str | None
    progress: str | None
    plan: list[PlanStep]
    proposal: str | None


class ApproveOperation(OperationEnvelope):
    """Landing a proposal on the pull request branch and answering the
    comment."""

    kind: Literal[OperationKind.APPROVE]
    reply: str | None = Field(
        description="The words this approve carried, posted or not yet.")
    delete_comment: bool = Field(
        description="Whether the approve was asked to remove the root "
                    "comment too.")
    proposal: str | None = Field(
        description="The proposal it is landing.")
    steps: LandingSteps
    landed_base: Sha | None = Field(
        description="The PR branch's commit the proposal was picked onto.")
    landed_sha: Sha | None = Field(
        description="The commit the proposal landed as.")
    posted_comment: int | None = Field(
        description="The reply that was posted, as an id.")
    reply_note: str | None = Field(
        description="Why no reply was posted, where the board applied the "
                    "approve and decided not to post one. Not a failure.")
    ticket_key: str | None = Field(
        description="The key the tracker gave the ticket this approve filed, "
                    "once it is filed.")
    ticket_url: str | None = Field(
        description="The filed ticket's link, which the reply carries on a line "
                    "of its own.")


class FileOperation(OperationEnvelope):
    """The agent run that files an accepted ticket. The approve it serves waits
    for it and posts the reply once it has reported the ticket; one that ends
    without reporting refuses the approve with `file-failed`, and nothing is
    posted."""

    kind: Literal[OperationKind.FILE]


class StopOperation(OperationEnvelope):
    """Halting whatever was in flight. Posts nothing and touches no comment.
    The operation it stopped settles as `refused` with `reason_code` of
    `withdrawn`."""

    kind: Literal[OperationKind.STOP]
    stopped: str | None = Field(
        description="The operation this one halted.")


class CloseOperation(OperationEnvelope):
    """Closing the thread. `resolve` accepts it; `reject` turns a finished
    proposal down and drops its worktree. Neither stops work in flight; that
    is `stop`."""

    kind: Literal[OperationKind.RESOLVE, OperationKind.REJECT]
    reply: str | None
    delete_comment: bool
    posted_comment: int | None = Field(
        description="The reply that was posted when the thread closed.")


class DeferOperation(OperationEnvelope):
    """Parking the thread until something wakes it."""

    kind: Literal[OperationKind.DEFER]
    until: WakeCondition
    note: str | None = Field(
        description="The operator's private note. Nothing is posted.")


class UnparkOperation(OperationEnvelope):
    """Bringing a parked thread back."""

    kind: Literal[OperationKind.UNPARK]


class PlaceOperation(OperationEnvelope):
    """Moving a thread an agent placed, on the board alone. `confirm` takes an
    Assumed done thread to Done; `place` takes it, or a Not my conversation
    thread, to the outcome the operator chose. Nothing reaches GitHub."""

    kind: Literal[OperationKind.CONFIRM, OperationKind.PLACE]


class ReplyOperation(OperationEnvelope):
    """Posting a reply to the thread."""

    kind: Literal[OperationKind.REPLY]
    body: str
    posted_comment: int | None


class DraftOperation(OperationEnvelope):
    """Work on a draft the board owns outright. `create-draft` is on the
    pull request's collection because there is no thread yet; the rest are
    on the thread's.

    Consecutive `edit-draft` operations collapse into one, replaced in place
    rather than appended, so a draft composed over ten minutes leaves one
    entry in the history rather than forty. The entry carries the id of the
    newest edit."""

    kind: Literal[OperationKind.CREATE_DRAFT, OperationKind.EDIT_DRAFT,
                  OperationKind.ENROL, OperationKind.WITHDRAW_FROM_REVIEW,
                  OperationKind.DISCARD, OperationKind.POST_NOW]
    body: str | None = Field(
        description="The draft's text as this operation left it. Null on the "
                    "kinds that do not change it.")
    anchor: Anchor | None = Field(
        description="Where this operation left the draft anchored. Null on "
                    "the kinds that do not change it.")
    posted_comment: int | None = Field(
        description="The comment a `post-now` created, as an id.")


class ReviewOperation(OperationEnvelope):
    """Sending one GitHub review with a verdict and every enrolled draft.

    The only operation that moves more than one thread, which is why it
    also writes a `posted` operation onto each draft it posted: a thread's
    state stays readable from that thread's own history."""

    kind: Literal[OperationKind.SEND_REVIEW]
    verdict: ReviewVerdict
    body: str | None = Field(
        description="The review's summary, at the top of the notification.")
    drafts: list[ThreadKey] = Field(
        description="The threads that went out with it, in the order sent. "
                    "While it is pending, the drafts enrolled when it was "
                    "asked for; the drain sends whatever is enrolled when it "
                    "takes it.")
    posted_review: int | None = Field(
        description="GitHub's id for the review, once it took it.")


class PostedOperation(OperationEnvelope):
    """Written onto a draft by the `send-review` that posted it. Carries the
    thread's new GitHub identity so its own history explains how it stopped
    being a draft."""

    kind: Literal[OperationKind.POSTED]
    review: str | None = Field(
        description="The `send-review` operation that posted it.")
    posted_comment: int | None
    github_node_id: str | None = Field(
        description="The thread GitHub opened for it. Null when GitHub did "
                    "not list the thread straight after the review; the "
                    "conversation's own `github_node_id` is filled in when "
                    "the poller first sees it.")


Operation = Annotated[
    FixOperation | SessionOperation | ApproveOperation | FileOperation | StopOperation
    | CloseOperation | DeferOperation | UnparkOperation | PlaceOperation | ReplyOperation
    | DraftOperation | ReviewOperation | PostedOperation,
    Field(discriminator="kind",
          description="A piece of work. Every kind carries the same "
                      "envelope; the kinds that need more add their own "
                      "fields."),
]


class OperationList(RootModel[list[Operation]]):
    """Operations, oldest first."""


class Outcome(BaseModel):
    """What a verb on a thread was taken as, answered `202` before the drain
    takes it."""

    operation: Operation = Field(
        description="The operation the verb queued, as `Location` reads it.")
    conversation: Conversation = Field(
        description="The thread as the board's dry run of the verb says the "
                    "drain will leave it, before anything reaches GitHub or "
                    "git. `updated_at` is the moment the verb was asked, so "
                    "a copy saved before it is older and the drain's save is "
                    "not; `etag` is the thread's as it stands with the verb "
                    "waiting, the tag a next verb is checked against.")


class DiffSource(StrEnum):
    ORIGIN = "origin"
    LOCAL = "local"


class DiffFileStatus(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"
    RENAMED = "renamed"
    COPIED = "copied"


class DiffLineKind(StrEnum):
    CONTEXT = "context"
    ADDED = "added"
    REMOVED = "removed"


class DiffLine(BaseModel):
    kind: DiffLineKind
    old_line: int | None
    new_line: int | None
    text: str = Field(
        description="The line, without its leading +, - or space, and "
                    "without highlighting.")


class DiffHunk(BaseModel):
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    section: str | None = Field(
        description="What git puts after the `@@`: the enclosing function or "
                    "class. Null where it could not work one out.")
    lines: list[DiffLine]


class FileChange(BaseModel):
    """One file in a change: `hunks` is `[]` when there are none to show,
    which `is_binary` explains."""

    path: str
    old_path: str | None = Field(
        description="Set only where the file was renamed or copied.")
    status: DiffFileStatus
    added: int
    removed: int
    is_binary: bool = Field(
        description="Without this, a binary file and an unchanged one are "
                    "both an empty `hunks` array.")
    line_count: int | None = Field(
        default=None,
        description="How many lines the file has at the diff's head, so a "
                    "reader knows whether lines lie hidden below the last "
                    "hunk. Null where the head no longer holds the file.")
    hunks: list[DiffHunk] = Field(
        description="Empty where there are none, as on a binary file or a "
                    "pure rename.")


class Diff(BaseModel):
    base: Sha
    head: Sha
    files: list[FileChange]


class Commits(BaseModel):
    """Two commits that address a diff: `/diffs/{base}..{head}`."""

    base: Sha
    head: Sha


class Ticket(BaseModel):
    """A ticket as the agent proposed it, or as the viewer left it in the
    accept dialog."""

    project: str = Field(
        description="Where it is filed: a Jira project key, or the watched "
                    "repository as owner/name for a GitHub issue.")
    title: str
    body: str


class Proposal(BaseModel):
    """What one completed run or session left behind. Half of this comes from
    a record and half from git, which is why reading it costs subprocesses.

    The plan is not here. It belongs to the operation, because a card shows
    how far a *running* agent has got and a proposal only exists once the run
    is over. The summary is here, because the agent writes it at the end and
    it describes the artifact.
    """

    id: str
    conversation: ThreadKey = Field(description="The thread it was left on.")
    kind: ProposalKind = Field(
        description="What accepting it does: `commit` lands the agent's commit "
                    "and answers the comment, `reply` posts `reply` and "
                    "nothing else, `ticket` files `ticket` and then posts "
                    "`reply`. Only a commit has a diff, files or tests.")
    reply: str | None = Field(
        description="The reply the agent proposes to post. Null on a commit, "
                    "whose answer the viewer writes on accepting.")
    ticket: Ticket | None = Field(
        description="The ticket the agent proposes to file. Null unless "
                    "`kind` is `ticket`.")
    operation: str | None = Field(
        description="The run or session that produced it.")
    created_at: str | None = Field(
        description="When the work that produced it finished. Null on a "
                    "record written before the board kept a history, which "
                    "never stamped it.")
    updated_at: str | None = Field(
        description="When the thread's record was last saved, moving the "
                    "base among other things. Of two copies the one with the "
                    "later stamp is newer.")
    commits: Commits | None = Field(
        description="The commits its diff runs between: the agent's base and "
                    "the commit it left, or once an approve has landed it, "
                    "where it landed. A moved base is new commits. Null where "
                    "it committed nothing, which is the reason an approve "
                    "refuses.")
    directory: str | None = Field(
        description="The worktree on this machine the agent made the fix "
                    "in. Null where no worktree was ever cut for it.")
    summary: str | None = Field(description="What the agent said it did.")
    agent_note: str | None = Field(
        description="Anything else it wanted to say. Written before "
                    "summaries existed and still the only thing some "
                    "proposals carry.")
    confidence: ConfidenceLevel | None
    confidence_note: str | None = Field(
        description="The sentence behind the level.")
    tests: str | None = Field(
        description="What the agent did about tests, in its own word.")
    tests_note: str | None
    commit_message: str | None = Field(
        description="The message of the commit the agent left, which is the "
                    "one an approve lands with unless it is given another. "
                    "Null where git cannot read it.")


class ProposalList(RootModel[list[Proposal]]):
    """What has been left on this thread, oldest first."""


class FileLine(BaseModel):
    number: int
    text: str


class FileLines(BaseModel):
    sha: Sha
    path: str
    from_line: int
    to_line: int
    truncated: bool = Field(
        description="The file continues past `to_line`. Always false when "
                    "the caller gave an explicit range, because a range "
                    "wider than the ceiling is refused rather than clipped.")
    lines: list[FileLine]


class ApproveRequest(BaseModel):
    reply: str | None = Field(
        default=None,
        description="Posted to the thread, or to the pull request when the "
                    "comment has no thread of its own. Longer than GitHub "
                    "will take is a 413 rather than a validation error, "
                    "because the limit is theirs and not this domain's.")
    delete_comment: bool = Field(
        default=False,
        description="Also remove the root comment from GitHub. Refused "
                    "`not-deletable` where it is not the viewer's to remove: "
                    "someone else's, of a kind GitHub deletes none of, or "
                    "replied to by anybody else.")
    resolve: bool = Field(
        default=False,
        description="Also mark the thread resolved on GitHub once the "
                    "comment is answered. Refused on a comment with no "
                    "thread of its own, and beside `delete_comment`, which "
                    "leaves no thread to resolve.")
    message: str | None = Field(
        default=None,
        description="The message the landed commit carries in place of the "
                    "agent's. Empty or absent lands the agent's own.")
    ticket: Ticket | None = Field(
        default=None,
        description="The ticket to file, as the viewer edited it, when the "
                    "proposal is a ticket. Absent files the ticket as the "
                    "agent proposed it.")


class CloseRequest(BaseModel):
    """The body of both `:resolve` and `:reject`."""

    reply: str | None = Field(
        default=None,
        description="Posted before the thread closes. With nothing written, "
                    "a reviewer's thread gets a thumbs-up on its newest reply "
                    "instead.")
    delete_comment: bool = Field(
        default=False,
        description="Also remove the root comment from GitHub, refused "
                    "`not-deletable` on the same terms as an approve's.")


class ResolveRequest(CloseRequest):
    """The body of `:resolve`."""

    resolve: bool = Field(
        default=False,
        description="Also mark the thread resolved on GitHub, after any "
                    "reply. Left false, a reviewer's thread closes on the "
                    "board only; a comment with no thread of its own has nothing to "
                    "resolve and only closes on the board. Refused beside "
                    "`delete_comment`, which leaves no thread to resolve.")
    thumbs_up: bool = Field(
        default=True,
        description="With nothing written, put a thumbs-up on the newest "
                    "reply of a reviewer's thread as it resolves. False "
                    "resolves it with no reaction.")


class BriefRequest(BaseModel):
    """The body of `:rework`. An autonomous run has only this to work
    from, so a brief with neither a note nor a pointed line is refused."""

    note: str = ""
    pointed: list[PointedLine] = Field(
        default_factory=list,
        description="The lines the operator pointed the agent at.")
    include: list[str] = Field(
        default_factory=list,
        description="Logins whose comments go into the agent's context along "
                    "with the note.")


class StartSessionRequest(BaseModel):
    steer: str | None = Field(
        default=None, description="What to tell the session on the way in.")
    pointed: list[PointedLine] = Field(
        default_factory=list,
        description="The lines the operator pointed the session at.")
    include: list[str] = Field(
        default_factory=list,
        description="Logins whose comments go into the session's context along "
                    "with the steer.")


class DeferRequest(BaseModel):
    until: WakeCondition
    note: str | None = Field(
        default=None, description="Private to the board; nothing is posted.")


class PlaceRequest(BaseModel):
    to: Literal[ConversationState.READY, ConversationState.WAITING,
                ConversationState.NOT_MINE, ConversationState.QUEUED] = Field(
        description="The state the thread is to be in: `ready` for my move, "
                    "`waiting` for their move, `not-mine`, or `queued` for a "
                    "fresh agent run. Which of them a thread takes depends on "
                    "whose pull request it is.")


class ReplyRequest(BaseModel):
    body: Annotated[str, StringConstraints(min_length=1)]


class DraftBody(BaseModel):
    """The body of `:create-draft` and `:edit-draft`. Both carry the whole
    draft, so an edit is a replacement rather than a patch: the composer
    holds the text and the anchor together and sends what it has."""

    body: Annotated[str, StringConstraints(min_length=1, max_length=65536)]
    path: Annotated[str, StringConstraints(min_length=1)] = Field(
        description="Repository-relative path the comment hangs off.")
    line: Annotated[int, Field(ge=1, description="The line, 1-based.")]
    start_line: Annotated[int | None, Field(
        default=None, ge=1,
        description="The first line, where the comment spans several.")]
    start_side: DiffSide | None = Field(
        default=None,
        description="Which side of the diff the first line is on. Defaults to "
                    "`side`; dropped without a `start_line`.")
    side: DiffSide = Field(
        default=DiffSide.RIGHT,
        description="Which side of the diff. Defaults to the new side, which "
                    "is what a reviewer almost always means.")


class SendReviewRequest(BaseModel):
    verdict: ReviewVerdict
    body: str | None = Field(
        default=None,
        description="The review's summary. GitHub requires it for "
                    "`REQUEST_CHANGES` and `COMMENT`, and a request without "
                    "one is refused before anything is sent. Longer than "
                    "GitHub will take is a 413.")


class AgentState(StrEnum):
    """Whether the manager has an agent run going for this pull request."""

    IDLE = "idle"
    WORKING = "working"


class AgentActivity(BaseModel):
    name: str = Field(
        description="The name of the agent this instance runs, as the board shows it.")
    enabled: bool = Field(
        description="Whether `config.toml` lets the manager start an agent at "
                    "all. With it off, `:carry-on` is refused with a notice.")
    state: AgentState
    event: str | None = Field(
        description="The event the run is working on. Null when idle.")
    elapsed_seconds: float | None = Field(
        description="How long the run has been going. Null when idle.")
    silent_seconds: float | None = Field(
        description="How long since the run last said anything. Null when "
                    "idle.")


class LastRun(BaseModel):
    event: str
    exit_code: int | None = Field(
        description="Null where the run was stopped before it could exit.")
    ended_at: str


class ThreadCounts(BaseModel):
    queued: int = Field(description="Threads waiting for an agent run.")
    live: int = Field(description="Threads an agent is working on now.")
    proposed: int = Field(description="Fixes an agent proposed, waiting for your decision.")
    drafts: int = Field(description="Your draft review comments, not sent yet.")


class DashboardPr(BaseModel):
    repo: str
    number: int
    title: str | None
    url: str | None = Field(description="Where the pull request is on github.com.")
    branch: str | None
    ticket: str | None = Field(
        description="The Jira ticket the branch name carries, such as `PROJ-34`.")
    author: str | None = Field(
        description="The login of the pull request's author. Null before a "
                    "poll has said, or where GitHub did not.")


class SinceYouActed(BaseModel):
    """What happened on someone else's pull request since your last review."""

    commits: int = Field(description="Commits pushed since. Not counted after a force-push.")
    force_pushed: bool
    reviews: int
    comments: int
    threads_resolved: int


class DashboardStatus(BaseModel):
    detailed_reviewer: str | None = Field(
        description="The login of the detailed reviewer. Null where none is "
                    "assigned.")
    you_are_the_detailed_reviewer: bool
    mergeable: bool = Field(description="False where GitHub has not said.")
    needs_rebase: bool = Field(
        description="The branch conflicts with or is behind its base, so a "
                    "rebase on main would bring it level.")
    last_event_at: str | None
    review_ready_at: str | None
    since_you_last_acted: SinceYouActed | None = Field(
        description="Null on your own pull requests and before your first "
                    "review.")
    failed_checks: list[str] = Field(description="The checks failing on the head commit.")
    checks_done: int
    checks_total: int
    changed_files: int | None
    approved_by: list[str]


class DashboardSystem(BaseModel):
    agent: AgentActivity
    last_run: LastRun | None = Field(
        description="How the newest finished run ended. Null before the "
                    "first one.")
    queued_events: int = Field(
        description="Events waiting for this pull request's manager to take.")
    on_hold: bool = Field(
        description="On hold, the manager takes no events but a closing one.")
    unpushed_commits: int | None = Field(
        description="Commits on the worktree's branch that are not on the "
                    "pull request yet. Null where git could not say.")
    threads: ThreadCounts


class FrozenWorktree(BaseModel):
    """The manager froze because the worktree holds another branch."""

    worktree: str
    here: str = Field(description="The branch the worktree holds.")
    expected: str = Field(description="The pull request's own branch.")
    seconds_left: float = Field(
        description="How long until the watcher gives up waiting and builds "
                    "a fresh worktree.")
    run_working: bool = Field(
        description="An agent run is still producing output, so the watcher "
                    "waits for it.")
    release_requested: bool


class MergeState(StrEnum):
    """GitHub's mergeability in the snapshot's words."""

    CLEAN = "clean"
    CONFLICTS = "conflicts"
    BEHIND = "behind"
    BLOCKED = "blocked"
    CHECKS_FAILING = "checks-failing"
    UNKNOWN = "unknown"
    OTHER = "other"


class MentionFact(BaseModel):
    author: str
    at: str | None = Field(description="When they wrote it. Null where GitHub did not say.")
    answered: bool = Field(description="You have spoken on the thread since.")


class PrFacts(BaseModel):
    """What GitHub said of the pull request at the watcher's last poll: the
    facts the next move reads."""

    polled_at: str | None = Field(
        description="When the watcher polled them. Of two copies the one with "
                    "the later stamp is newer. Null on a snapshot written "
                    "before the stamp was kept.")
    ended: bool = Field(description="Merged or closed, or the watcher is letting it go.")
    is_author: bool | None = Field(
        description="Whether the account is the author, the one answer to "
                    "whose pull request this is. Null where GitHub did not say.")
    changes_requested_by: list[str]
    pending_reviewers: list[str] = Field(
        description="Reviewers asked for a review who have not given one.")
    ci_status: str = Field(description="`passing`, `failing` or `pending`.")
    merge_state: MergeState | None = Field(
        description="Null where GitHub did not say.")
    draft: bool
    review_decision: str | None = Field(
        description="`approved`, `changes-requested` or `review-required`. "
                    "Null while GitHub has no decision.")
    my_review: str | None = Field(
        description="Your own review that stands: `approved`, "
                    "`changes-requested`, `commented` or `dismissed`. Null "
                    "where you have not reviewed.")
    my_review_at: str | None = Field(description="When you gave the review that stands.")
    viewer_requested: bool = Field(
        description="You are on the requested list right now.")
    mentioned: bool = Field(description="The pull request has mentioned you.")
    mentions: list[MentionFact] = Field(description="Every mention of you, oldest first.")
    unresolved_threads: int | None = Field(
        description="Review threads unresolved on GitHub. Null where GitHub did not say.")


class ManagerFlags(BaseModel):
    """What the PR manager holds of the pull request beside GitHub's facts."""

    frozen_on: str | None = Field(
        description="The other branch the worktree holds. Null where it holds its own.")
    on_hold: bool
    working_on: str | None = Field(
        description="The event an agent run is working on. Null where none runs.")
    hidden: bool = Field(description="Dismissed, until its next event or forever.")
    threads_live: int = Field(description="Threads an agent is working on now.")
    changed_at: str | None = Field(
        description="When one of these last changed, as this process saw it. "
                    "Of two copies the one with the later stamp is newer.")


class ThreadRow(BaseModel):
    """One thread in a line: what the next move reads of it, in the
    conversation's own words."""

    key: ThreadKey
    state: ConversationState
    record_state: RecordState
    author_kind: AuthorKind
    updated_at: str | None = Field(
        description="When the record was last saved. A full conversation "
                    "with the same stamp is the fuller copy.")


class Dashboard(BaseModel):
    """Everything the PR manager's dashboard shows, as of its last tick.

    The terminal dashboard draws from the same values. The manager replaces
    this once a tick, so a command answered `202` shows here within a tick or
    two.
    """

    pr: DashboardPr
    polled: bool = Field(
        description="False until change detection has polled the pull "
                    "request, and `facts` is null until then.")
    status: DashboardStatus
    system: DashboardSystem
    frozen: FrozenWorktree | None
    undismiss_command: str = Field(
        description="The command that reverses dismissing this pull request "
                    "forever.")
    notice: str | None = Field(
        description="The sentence the dashboard is showing for a few seconds, "
                    "such as why a command was refused.")
    facts: PrFacts | None = Field(
        description="What the next move reads of GitHub. Null until the first poll.")
    manager: ManagerFlags
    threads: list[ThreadRow] = Field(
        description="Every readable thread on the pull request, one line each. "
                    "The same threads `/conversations` lists.")
    unreadable: list[str] = Field(
        description="The keys of the threads whose records will not read, "
                    "as `/conversations` names them.")
    listed_at: str | None = Field(
        description="When `threads` and `unreadable` were read: the list "
                    "names every thread as of then, so a thread saved since "
                    "may be missing from it. Left out of the tag.")


class ManagerChanges(BaseModel):
    """What the agent has written in its notes on this pull request's changes."""

    markdown: str | None = Field(
        description="The notes as Markdown, for the page to render. Null "
                    "where the agent has written none.")


class OutputLine(BaseModel):
    text: str
    run_boundary: bool = Field(
        description="True on the marker between one run's output and the "
                    "next, whose `text` says nothing.")


class AgentOutput(BaseModel):
    """The tail of what the agent has said on this pull request, oldest first."""

    lines: list[OutputLine]


class CapturedGit(StrEnum):
    """A git palette command the page runs in the worktree and shows the
    output of, named by the palette's keys: `f` force-pushes with lease, `p`
    pushes, `pra` pulls with rebase and autostash, `s` is the status, `l` the
    log and `d` the diff against HEAD. The palette's other commands need a
    terminal and are not offered here."""

    FORCE_PUSH = "f"
    PUSH = "p"
    PULL = "pra"
    STATUS = "s"
    LOG = "l"
    DIFF = "d"


class GitRequest(BaseModel):
    keys: CapturedGit


class GitRun(BaseModel):
    """What a git command printed in the worktree, stdout then stderr."""

    exit_code: int = Field(
        description="The command's exit code; -1 when it ran past its time and "
                    "was stopped.")
    lines: list[str]
    seconds: float = Field(description="How long the command ran.")
    truncated: bool = Field(
        description="True when the command printed more lines than are "
                    "answered, and only the first of them are here.")


class TerminalRequest(BaseModel):
    keys: str = Field(
        pattern=r"^(new|a|c|r|i[0-9]+)$",
        description="What to open, named by the git palette's keys: `new` a login "
                    "shell, `a` git add -p, `c` git commit, `i<N>` git rebase -i "
                    "HEAD~N, `r` the agent rebasing on main with you steering. The "
                    "palette's other commands run in the page.")


class TerminalSession(BaseModel):
    """A pty in a worktree, living while a page is connected to it."""

    id: str
    argv: list[str] = Field(description="The command the session runs.")
    worktree: str = Field(description="Where it runs: the PR's worktree, or a "
                                      "thread's own for a steered session.")


class TerminalSessionList(BaseModel):
    sessions: list[TerminalSession] = Field(description="Oldest first.")


class DismissRequest(BaseModel):
    forever: bool = Field(
        description="False dismisses the pull request until its next event; "
                    "true dismisses it for good. Either way the manager "
                    "stops its run and exits, and the board goes with it.")


class HeldPullRequest(BaseModel):
    """One pull request the watcher holds, as the wall shows it."""

    repo: str
    number: int
    manager: str = Field(
        description="What became of the PR manager: `running`, `exited`, "
                    "`no-window` when none was started or it was closed, or "
                    "`unreadable` when its record would not read.")
    board_url: str | None = Field(
        description="`/pr/<owner>/<name>/<number>` on the hub, where the pull request's board "
                    "is carried, when one is wanted. It answers only while its "
                    "PR manager runs.")
    board_answered: bool = Field(
        description="True where `dashboard` is the running manager's own, read "
                    "from its board within the last 30 seconds. False where the "
                    "board has not answered for longer or there is none, and the "
                    "hub built the "
                    "dashboard from what is on disk: no run, no notice, and a "
                    "frozen worktree as the watcher sees it.")
    dashboard: Dashboard = Field(
        description="What `/api/dashboard` on its board answers. The page "
                    "decides the row's move and group from its facts, "
                    "manager flags and thread rows.")


class WallGroupName(BaseModel):
    group: WallGroup
    name: str = Field(description="The group's heading, such as `Needs you`.")


class HeldPullRequests(BaseModel):
    """Every pull request the watcher held after its last cycle, as the wall
    shows them."""

    watching: list[str] = Field(
        description="Every repository this instance watches, `owner/name`, in name "
                    "order, from its own settings.")
    groups: list[WallGroupName] = Field(
        description="Every group, in the order the wall shows them.")
    pull_requests: list[HeldPullRequest] = Field(
        description="By repository, then number; the page sorts the wall "
                    "into its groups itself.")




class RunsToday(BaseModel):
    runs: int = Field(description="Runs that ended since midnight, the hub's local time.")
    cost_usd: float | None = Field(
        description="What those runs would have cost on the API, summed over the "
                    "ones that reported a cost; a floor when `unpriced` is not 0. "
                    "Null where none reported one.")
    unpriced: int = Field(description="Runs that ended without reporting a cost.")


class FinishedRun(BaseModel):
    """One agent run from the run ledger."""

    ended_at: str
    repo: str | None = Field(description="Null where the ledger names no pull request.")
    number: int | None
    event: str = Field(
        description="What the run was for: the event it answered, such as "
                    "`ci-failed`, or `thread-fix-<thread>` for a thread's fix.")
    elapsed_seconds: float
    exit_code: int | None = Field(
        description="Negative for a signal. Null where the ledger did not say.")
    cost_usd: float | None = Field(
        description="What the run would have cost on the API. Null where it "
                    "reported none.")
    failed: bool = Field(
        description="It exited with a code other than 0, or the agent reported the "
                    "run as an error.")
    board_url: str | None = Field(
        description="`/pr/<owner>/<name>/<number>` on the hub while the watcher holds the pull "
                    "request, where its Dashboard shows the agent's output. Null "
                    "once it lets go, or for a run on no pull request.")


class RunLedger(BaseModel):
    """The agent runs of the last seven days and the watcher's health, as the
    Runs page and the wall's top bar show them."""

    watcher: WatcherHealth
    today: RunsToday
    runs: list[FinishedRun] = Field(description="Newest first.")


Login = Annotated[str, StringConstraints(pattern="^[A-Za-z0-9-]+$", max_length=39)]


class FieldError(ErrorDetail):
    field: str = Field(
        description="Which part of the setup write this refuses: `gh_account`, "
                    "`repos[<index>].repo`, `repos[<index>].local_path`, or `config` for the "
                    "file as a whole, such as a `hub_port` among the boards' ports.")


class FieldErrors(BaseModel):
    """A setup write refused field by field, nothing written or cloned."""

    errors: Annotated[list[FieldError], Field(min_length=1)]


class SetupRepo(BaseModel):
    """One watched repo as the config writes it."""

    repo: str = Field(description="`owner/name`.")
    local_path: str = Field(
        description="Its clone, as written in the config: `~/` stands for the home folder.")
    new_worktree_command: str = Field(
        default="",
        description="What runs in each new worktree of this repo. Empty for the config's "
                    "top-level default.")


class SetupOptions(BaseModel):
    agent_model: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    agents_enabled: bool = Field(description="Whether agents start on their own.")
    max_thread_runs: int = Field(ge=1, le=64,
                                 description="How many thread agents run at once.")


class SetupRequirement(BaseModel):
    program: str
    fix: str | None = Field(
        description="How to install it when it is not on the watcher's PATH; null when it is.")


class Setup(BaseModel):
    """The setup screen's read: the hub's state and the config as it stands."""

    state: HubState = Field(description="As the config file reads now.")
    etag: str = Field(
        description="The config's revision. Send it as `If-Match` on `PUT /api/setup`.")
    config_path: str
    problem: str | None = Field(
        description="What is wrong with the config, in setup or broken state; null while "
                    "watching.")
    active_account: str | None = Field(
        description="The account gh is logged in as now, to fill the username with; null "
                    "when gh answers nothing.")
    gh_account: str | None = Field(description="The config's account; null until set.")
    repos: list[SetupRepo]
    options: SetupOptions
    hub_port: int
    agent_name: str = Field(
        description="The agent this instance runs, by the name the board shows; the model "
                    "option is that agent's.")
    requirements: list[SetupRequirement]


class SetupAccount(BaseModel):
    login: str
    scopes: list[str] = Field(description="The scopes of gh's token for the login.")


class SetupRepoChoice(BaseModel):
    repo: str
    can_push: bool = Field(description="The login can push to it; the screen lists these "
                                       "first and the rest under Show read-only.")
    has_my_prs: bool = Field(
        description="The login has an open pull request there or is asked to review one.")
    default_branch: str


class SetupRepoChoices(BaseModel):
    """The repos a login can reach, newest push first."""

    login: str
    repos: list[SetupRepoChoice]


class SetupClone(BaseModel):
    """Where a repo's clone is, or would go."""

    repo: str
    path: str = Field(description="The config's clone for a watched repo, otherwise "
                                  "`~/repositories/<name>`.")
    exists: bool = Field(description="Something is at the path.")
    is_clone: bool = Field(description="What is there is a clone of the repo.")


class SetupRequest(BaseModel):
    """The whole config the setup screen writes."""

    gh_account: Login
    repos: Annotated[list[SetupRepo], Field(min_length=1, max_length=100)]
    options: SetupOptions
    hub_port: int | None = Field(
        default=None, description="Left as the config has it when null.")


class SetupCloneProgress(BaseModel):
    repo: str
    path: str = Field(description="Where the clone is, or goes, with the home folder spelled "
                                  "out.")
    state: CloneState = Field(
        description="`found` for a clone already there, else `waiting`, `cloning`, then "
                    "`cloned` or `failed`.")
    error: str | None


class SetupOperation(BaseModel):
    """A setup write in progress."""

    id: str
    state: WriteState = Field(
        description="`cloning` while clones run; `failed` when one fails, with the config "
                    "left as it was; `restarting` once the config is written and the watcher "
                    "stops for its service to start it again. Poll `/api/health` until its "
                    "`pid` changes.")
    clones: list[SetupCloneProgress]
    error: str | None
    archived: list[str] = Field(
        description="Where the state, queues, transcripts and holds of repos no longer "
                    "watched went.")
    kept_worktrees: list[str] = Field(
        description="Worktrees of the pull requests in repos no longer watched. They are "
                    "left where they are.")


class Tour(BaseModel):
    due: bool = Field(description="Whether the board's first-run tour is still to be shown: "
                                  "true from the first setup that leaves setup state until the "
                                  "page says it was seen.")


class MovedAside(BaseModel):
    moved_to: str = Field(description="Where the broken config is now.")
