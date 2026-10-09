import dataclasses
import itertools
from collections.abc import Set
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from github_orchestrator.change_detection import PrClosed, PrEvent
from github_orchestrator.conversation import ThreadActivity
from github_orchestrator.domain import Pr, Repo
from github_orchestrator.pr_event_queue._responses import (
    found_again,
    recovered,
    respond,
    settling_of,
    touches_the_run,
    waiting_of,
)
from github_orchestrator.pr_event_queue.interface import (
    Entry,
    Queued,
    Response,
    State,
    Waiting,
)
from github_orchestrator.pr_event_queue.interface import Queue as Queue


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class _Held:
    event: Queued
    queued_at: datetime
    order: int


@dataclass
class _Queue:
    pending: list[_Held] = field(default_factory=list)
    in_flight: list[_Held] = field(default_factory=list)
    failed: list[tuple[datetime, _Held]] = field(default_factory=list)
    torn_down: bool = False


class _FakeTaken:
    def __init__(self, queue: _Queue, entry: _Held, response: Response) -> None:
        self._queue = queue
        self._entry = entry
        self._response = response

    @property
    def _event(self) -> Queued:
        return self._entry.event

    @property
    def response(self) -> Response:
        return self._response

    def done(self) -> None:
        if isinstance(self._event, PrClosed):
            self._queue.torn_down = True
        if self._entry in self._queue.in_flight:
            self._queue.in_flight.remove(self._entry)

    def failed(self) -> None:
        if self._entry in self._queue.in_flight:
            self._queue.in_flight.remove(self._entry)
            self._queue.failed.append((_now(), self._entry))


def _order(pr: Pr) -> tuple[str, ...]:
    return (pr.repo.owner, pr.repo.name, str(pr.number))


class FakePrEventQueue:
    def __init__(self) -> None:
        self._queues: dict[Pr, _Queue] = {}
        self._order = itertools.count()

    def _queue(self, pr: Pr) -> _Queue:
        return self._queues.setdefault(pr, _Queue())

    def _held(self, pr: Pr) -> list[Queued]:
        queue = self._queue(pr)
        return [entry.event for entry in queue.pending + queue.in_flight]

    def _enqueue(self, pr: Pr, item: Queued) -> None:
        self._queue(pr).pending.append(_Held(item, _now(), next(self._order)))

    def add(self, pr: Pr, event: PrEvent) -> None:
        self._enqueue(pr, event)

    def add_thread_activity(self, pr: Pr, activity: ThreadActivity) -> None:
        if found_again(activity, self._held(pr)):
            return
        self._enqueue(pr, activity)

    def next(
        self, pr: Pr, *, is_author: bool, agents_enabled: bool,
        busy: bool = False,
    ) -> _FakeTaken | None:
        queue = self._queues.get(pr)
        if queue is None:
            return None
        for entry in queue.pending:
            if busy and touches_the_run(entry.event, is_author, agents_enabled):
                continue
            queue.pending.remove(entry)
            queue.in_flight.append(entry)
            response = respond(
                pr, entry.event, is_author=is_author,
                agents_enabled=agents_enabled, pending=lambda: self._pending(pr),
            )
            return _FakeTaken(queue, entry, response)
        return None

    def _pending(self, pr: Pr) -> list[Queued]:
        queue = self._queues.get(pr)
        if queue is None:
            return []
        return [entry.event for entry in queue.pending]

    def waiting(self, pr: Pr) -> Waiting:
        queue = self._queues.get(pr, _Queue())
        held = [entry.event for entry in queue.in_flight]
        pending = self._pending(pr)
        return waiting_of(pending, pending + held)

    def settling(self, pr: Pr) -> bool:
        queue = self._queues.get(pr, _Queue())
        return settling_of(self._pending(pr) + [entry.event for entry in queue.in_flight])

    def queues(self) -> list[Queue]:
        return [Queue(pr, (
                    *(Entry(pr, held.event, held.queued_at, State.IN_FLIGHT)
                      for held in queue.in_flight),
                    *(Entry(pr, held.event, held.queued_at, State.PENDING)
                      for held in queue.pending)))
                for pr, queue in sorted(self._queues.items(), key=lambda kv: _order(kv[0]))]

    def failed_since(self, when: datetime) -> list[Entry]:
        return [
            Entry(pr, held.event, held.queued_at, State.FAILED)
            for pr in sorted(self._queues, key=_order)
            for at, held in self._queues[pr].failed
            if at >= when
        ]

    def recover(self, pr: Pr) -> None:
        queue = self._queues.get(pr)
        if queue is None:
            return
        back = [dataclasses.replace(held, event=recovered(held.event)) for held in queue.in_flight]
        queue.pending = sorted(queue.pending + back, key=lambda held: held.order)
        queue.in_flight = []

    def drop_in_flight(self, pr: Pr) -> None:
        queue = self._queues.get(pr)
        if queue is not None:
            queue.in_flight = []

    def forget(self, pr: Pr) -> bool:
        self._queues.pop(pr, None)
        return True

    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]:
        moved = sorted({str(pr.repo) for pr in self._queues if pr.repo not in keep})
        for pr in [pr for pr in self._queues if pr.repo not in keep]:
            del self._queues[pr]
        return [into.joinpath(*repo.split("/")) for repo in moved]

    def is_torn_down(self, pr: Pr) -> bool:
        queue = self._queues.get(pr)
        return queue is not None and queue.torn_down
