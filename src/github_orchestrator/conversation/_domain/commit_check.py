import re
from dataclasses import dataclass, replace

from github_orchestrator.conversation._domain.conversation import (
    OPEN,
    ROLE_REVIEWER,
    CommitCheck,
    CommitVerdict,
    Conversation,
)
from github_orchestrator.conversation._domain.verdict import (
    PLACED_BY_A_VERDICT,
    STATE_OF_VERDICT,
    newest_said,
    retry_due,
)

MAX_CANDIDATES = 5

_HASH = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,40}(?![0-9A-Za-z])")


@dataclass(frozen=True)
class CommitReference:
    on: str
    candidates: tuple[str, ...]


def _said_at(conversation: Conversation, index: int) -> str:
    comment = conversation.comments[index]
    return str(comment.id) if comment.id is not None else f"#{index + 1}"


def commit_reference(conversation: Conversation, viewer: str) -> CommitReference | None:
    if conversation.role != ROLE_REVIEWER:
        return None
    spoke = [index for index, comment in enumerate(conversation.comments)
             if comment.author == viewer]
    if not spoke:
        return None
    for index in range(len(conversation.comments) - 1, spoke[-1], -1):
        found = tuple(dict.fromkeys(_HASH.findall(conversation.comments[index].body)))
        if found:
            return CommitReference(on=_said_at(conversation, index),
                                   candidates=found[:MAX_CANDIDATES])
    return None


def commit_check_due(conversation: Conversation, viewer: str, now: str | None) -> bool:
    reference = commit_reference(conversation, viewer)
    if (reference is None or conversation.state not in PLACED_BY_A_VERDICT
            or (conversation.commit_check is not None
                and conversation.commit_check.on == reference.on)):
        return False
    return conversation.commit_check_asked_for != reference.on or retry_due(
        conversation.commit_check_asks, conversation.commit_check_asked_at, now)


def with_a_check_ask(conversation: Conversation, on: str, at: str | None) -> Conversation:
    asks = (conversation.commit_check_asks + 1
            if conversation.commit_check_asked_for == on else 1)
    return replace(conversation, commit_check_asked_for=on, commit_check_asks=asks,
                   commit_check_asked_at=at)


def held_back(conversation: Conversation) -> bool:
    check = conversation.commit_check
    return (check is not None and check.verdict is CommitVerdict.NOT_ADDRESSED
            and check.on == newest_said(conversation))


def checked(conversation: Conversation, check: CommitCheck) -> Conversation:
    if check.on != conversation.commit_check_asked_for:
        return conversation
    given = replace(conversation, commit_check=check)
    if held_back(given) and given.state in PLACED_BY_A_VERDICT:
        return replace(given, state=OPEN)
    return given


def set_by_hand(conversation: Conversation, check: CommitCheck, verdict: CommitVerdict,
                reason: str) -> Conversation:
    given = replace(conversation, commit_check=replace(check, verdict=verdict, reasoning=reason))
    if given.state not in PLACED_BY_A_VERDICT:
        return given
    if held_back(given):
        return replace(given, state=OPEN)
    if given.verdict is not None and given.verdict_for == newest_said(given):
        return replace(given, state=STATE_OF_VERDICT[given.verdict])
    return given
