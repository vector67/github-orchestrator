from enum import StrEnum


class ErrorCode(StrEnum):
    """Why the review threads refused a verb or a report.

    The sentence beside it is the domain's own words and changes freely; this
    is what a caller branches on. Two pairs name both directions of one
    condition, because the transition table refuses in both.

    CONFIRM_AGAIN is the domain asking for the same verb a second time
    rather than turning it down: nothing failed, and repeating the request
    is what clears it.

    INTERNAL_REFUSAL is not a general-purpose fallback. It carries the
    refusals that cross no HTTP boundary, and a refusal a client can reach
    gets a code of its own.

    MALFORMED_REQUEST is a parameter the domain cannot take at all, such as
    a thread key that names no thread of its own, as distinct from one it
    takes and then refuses.
    """

    NOT_FOUND = "not-found"
    OPERATION_OUTSTANDING = "operation-outstanding"
    NOTHING_IN_FLIGHT = "nothing-in-flight"
    WORK_IN_FLIGHT = "work-in-flight"
    NO_PROPOSAL = "no-proposal"
    PROPOSAL_EXISTS = "proposal-exists"
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
    COMMENT_GONE = "comment-gone"
    NOT_DELETABLE = "not-deletable"
    BAD_WAKE_CONDITION = "bad-wake-condition"
    REVIEW_IN_FLIGHT = "review-in-flight"
    NOTHING_ENROLLED = "nothing-enrolled"
    GIT_FAILED = "git-failed"
    AGENTS_DISABLED = "agents-disabled"
    INTERNAL_REFUSAL = "internal-refusal"
