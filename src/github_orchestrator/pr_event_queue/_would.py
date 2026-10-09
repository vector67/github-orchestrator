from collections import Counter
from collections.abc import Callable

from github_orchestrator.change_detection import (
    BecameMergeable,
    BecameUnmergeable,
    ChangeDetection,
    HeadChanged,
    PrClosed,
    PrEvent,
)
from github_orchestrator.conversation import ThreadActivity
from github_orchestrator.domain import Pr
from github_orchestrator.pr_event_queue._responses import launch_of
from github_orchestrator.pr_event_queue.interface import Queued

_REASONS = {"blocked": "blocked by branch protection"}


def _detail(event: Queued) -> str | None:
    match event:
        case BecameUnmergeable() | BecameMergeable():
            reason: str = event.reason.value
            return _REASONS.get(reason, reason)
        case PrClosed() if event.no_longer_relevant:
            return "no-longer-relevant"
        case HeadChanged():
            return f"{event.previous[:7]}..{event.head[:7]}"
        case ThreadActivity():
            return (f"{len(event.threads)} thread(s), "
                    f"{len(event.stale)} stale record(s)")
    return None


def _label(event: Queued) -> str:
    detail = _detail(event)
    return event.kind if detail is None else f"{event.kind} ({detail})"


def _run(event: Queued, is_author: bool | None, agents_enabled: bool) -> str:
    if is_author is None:
        return " — what it does waits for a poll to save whose PR this is"
    if launch_of(event, is_author) is None:
        return ""
    if not agents_enabled:
        return " — would start no run: agents are disabled"
    return " — would launch an agent run"


class WouldIntake:
    def __init__(self, change_detection: ChangeDetection, agents_enabled: bool,
                 say: Callable[[str], None]) -> None:
        self._change_detection = change_detection
        self._agents_enabled = agents_enabled
        self._say = say
        self._enqueued: Counter[Pr] = Counter()

    def add(self, pr: Pr, event: PrEvent) -> None:
        self._would_enqueue(pr, event)

    def add_thread_activity(self, pr: Pr, activity: ThreadActivity) -> None:
        self._would_enqueue(pr, activity)

    def enqueued(self, pr: Pr) -> int:
        return self._enqueued[pr]

    def _would_enqueue(self, pr: Pr, event: Queued) -> None:
        facts = self._change_detection.facts(pr)
        is_author = None if facts is None else facts.is_author
        self._enqueued[pr] += 1
        self._say(f"would enqueue {_label(event)} for {pr}"
                  f"{_run(event, is_author, self._agents_enabled)}")
