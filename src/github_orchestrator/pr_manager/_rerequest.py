from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from github_orchestrator.change_detection import CiStatus, Facts
from github_orchestrator.conversation import (
    Conversation,
    ConversationState,
    OperationKind,
    OperationState,
)

OUTSIDE_A_ROUND = frozenset({"draft", "enrolled", "discarded", "not_mine", "removed", "unreadable"})
CLOSED = frozenset({ConversationState.DONE, ConversationState.WAITING,
                    ConversationState.ASSUMED_DONE, ConversationState.NOT_MINE,
                    ConversationState.DEFERRED})
ACCEPT_UNDER_WAY = frozenset({OperationState.PENDING, OperationState.RUNNING,
                              OperationState.REQUEUED})


@dataclass(frozen=True)
class Due:
    ask: tuple[str, ...]
    drop: tuple[str, ...]


def due(facts: Facts, conversations: Sequence[Conversation], queued: Sequence[str]) -> Due:
    drop = tuple(login for login in queued if login in facts.pending_reviewers)
    if not _pushed_and_green(facts, conversations):
        return Due(ask=(), drop=drop)
    ask = tuple(login for login in queued
                if login not in drop and not _holds_an_open_thread(login, facts, conversations))
    return Due(ask=ask, drop=drop)


def _pushed_and_green(facts: Facts, conversations: Sequence[Conversation]) -> bool:
    accepts = [operation for conversation in conversations
               for operation in conversation.operations if operation.kind == OperationKind.APPROVE]
    if any(accept.state in ACCEPT_UNDER_WAY for accept in accepts):
        return False
    if not _polled_after(facts.polled_at, (accept.settled_at for accept in accepts
                                           if accept.state == OperationState.APPLIED)):
        return False
    if facts.had_checks:
        return facts.ci_status is CiStatus.PASSING
    return facts.ci_status not in (CiStatus.FAILING, CiStatus.PENDING)


def _polled_after(polled_at: str | None, settled: Iterable[str | None]) -> bool:
    last = max((_instant(at) for at in settled if at is not None), default=None)
    if last is None:
        return True
    return polled_at is not None and _instant(polled_at) > last


def _holds_an_open_thread(login: str, facts: Facts,
                          conversations: Sequence[Conversation]) -> bool:
    asked_at = facts.review_requested_at.get(login)
    return any(conversation.author == login
               and conversation.state not in OUTSIDE_A_ROUND
               and (asked_at is None or conversation.opened_at is None
                    or _instant(conversation.opened_at) >= _instant(asked_at))
               and conversation.standing not in CLOSED
               for conversation in conversations)


def _instant(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)
