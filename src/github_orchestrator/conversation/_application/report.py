import logging

from github_orchestrator.conversation._application.asking import Denied
from github_orchestrator.conversation._application.ports import Held, Ports
from github_orchestrator.conversation._application.runner import run
from github_orchestrator.conversation._domain.commands import Command
from github_orchestrator.conversation._domain.conversation import (
    Conversation,
)
from github_orchestrator.conversation._domain.machine import Refused
from github_orchestrator.conversation._domain.standing import ErrorCode
from github_orchestrator.domain import Pr

log = logging.getLogger(__name__)


def not_a_key(key: str) -> Denied:
    return Denied(ErrorCode.MALFORMED_REQUEST, f"{key!r} names no thread of its own")


def answered(pr: Pr, key: str, command: Command, ports: Ports,
             held: Held) -> Conversation | Denied:
    if held.unreadable is not None:
        return Denied(ErrorCode.INTERNAL_REFUSAL, held.unreadable)
    conversation = held.conversation
    if conversation is None:
        log.warning("No record for %s thread %s; its %s was dropped",
                    pr, key, type(command).__name__)
        return Denied(ErrorCode.NOT_FOUND, f"{pr} has no thread called {key}")
    outcome = run(ports, conversation, command)
    if outcome.conversation != conversation:
        held.conversation = outcome.conversation
    if isinstance(outcome, Refused):
        log.warning("%s thread %s refused the agent's %s: %s",
                    pr, key, type(command).__name__, outcome.reason)
        return Denied(outcome.code, outcome.reason)
    return outcome.conversation
