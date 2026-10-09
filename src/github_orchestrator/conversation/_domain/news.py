from datetime import datetime

from github_orchestrator.conversation._domain.apply import REOPENED_BY_A_REPLY
from github_orchestrator.conversation._domain.conversation import (
    IN_SESSION,
    LANDED,
    LANDING,
    PROPOSED,
    QUEUED,
    RUNNING,
    Conversation,
)
from github_orchestrator.conversation._domain.operations import VERB_KINDS

_VERBS = frozenset(VERB_KINDS.values())
_STARTED = (RUNNING, IN_SESSION, PROPOSED, LANDING, LANDED)


def _after(at: str | None, ready: datetime) -> bool:
    return at is not None and datetime.fromisoformat(at) > ready


def handled_since_ready(conversation: Conversation | None) -> bool:
    if conversation is None or conversation.fix.state != PROPOSED:
        return True
    if conversation.decidable_at is None:
        return False
    ready = datetime.fromisoformat(conversation.decidable_at)
    return _after(conversation.seen_at, ready) or any(
        operation.kind in _VERBS and _after(operation.requested_at, ready)
        for operation in conversation.operations)


def opens_thread(record: Conversation | None, *, is_root: bool) -> bool:
    return record is None and is_root


def reopens(record: Conversation | None, *, first: bool) -> bool:
    return record is not None and first and record.state in REOPENED_BY_A_REPLY


def fix_queued(conversation: Conversation | None) -> bool:
    return conversation is not None and conversation.fix.state == QUEUED


def fix_started(conversation: Conversation | None) -> bool:
    return conversation is not None and conversation.fix.state in _STARTED


def replied_since(conversation: Conversation | None, account: str, at: str) -> bool:
    if conversation is None:
        return False
    arrived = datetime.fromisoformat(at)
    return any(comment.author == account and _after(comment.created_at, arrived)
               for comment in conversation.comments)
