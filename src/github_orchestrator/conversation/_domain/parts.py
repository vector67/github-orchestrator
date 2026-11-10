from dataclasses import dataclass, replace
from enum import StrEnum

FILE = "file"
PICK = "pick"
PUSH = "push"
OPEN = "open"
ANSWER = "answer"
MARK_RESOLVED = "resolve"


@dataclass(frozen=True)
class Ticket:
    project: str
    title: str
    body: str


class SplitPart(StrEnum):
    TICKET = "ticket"
    CHANGES = "changes"
    NEW_PR = "new-pr"
    REPLY = "reply"


class PartState(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    QUEUED = "queued"
    RUNNING = "running"
    RUN = "run"


@dataclass(frozen=True)
class Split:
    branch: str
    base: str
    base_reason: str
    ticket: Ticket | None = None
    accepted: frozenset[SplitPart] = frozenset()


@dataclass(frozen=True)
class PartView:
    part: SplitPart
    state: PartState
    waits_for: SplitPart | None


_RUNS_AS = {SplitPart.TICKET: FILE, SplitPart.CHANGES: PUSH, SplitPart.NEW_PR: OPEN,
            SplitPart.REPLY: ANSWER}

_TOUCHED_BY = frozenset({FILE, PICK, PUSH, OPEN, ANSWER})


def parts(split: Split) -> tuple[SplitPart, ...]:
    return tuple(part for part in SplitPart
                 if part != SplitPart.TICKET or split.ticket is not None)


def waits_for(split: Split, part: SplitPart) -> SplitPart | None:
    if part == SplitPart.NEW_PR and split.ticket is not None:
        return SplitPart.TICKET
    if part == SplitPart.REPLY:
        return SplitPart.NEW_PR
    return None


def has_run(steps: frozenset[str], part: SplitPart) -> bool:
    return _RUNS_AS[part] in steps


def any_run(steps: frozenset[str]) -> bool:
    return bool(steps & _TOUCHED_BY)


def accepting(split: Split, part: SplitPart | None) -> Split:
    asked = parts(split) if part is None else (part,)
    return replace(split, accepted=split.accepted | frozenset(asked))


def newly_accepted(split: Split, part: SplitPart | None) -> frozenset[SplitPart]:
    return accepting(split, part).accepted - split.accepted


def dropped(split: Split, part: SplitPart) -> Split:
    return replace(split, accepted=split.accepted - {part})


def _waiting(split: Split, steps: frozenset[str], part: SplitPart) -> bool:
    prerequisite = waits_for(split, part)
    return prerequisite is not None and not has_run(steps, prerequisite)


def next_part(split: Split, steps: frozenset[str]) -> SplitPart | None:
    return next((part for part in parts(split)
                 if part in split.accepted and not has_run(steps, part)
                 and not _waiting(split, steps, part)), None)


def _state(split: Split, steps: frozenset[str], part: SplitPart, under_way: bool) -> PartState:
    if has_run(steps, part):
        return PartState.RUN
    if part not in split.accepted:
        return PartState.PROPOSED
    if under_way and next_part(split, steps) == part:
        return PartState.RUNNING
    if _waiting(split, steps, part):
        return PartState.QUEUED
    return PartState.ACCEPTED


def views(split: Split, steps: frozenset[str], under_way: bool) -> tuple[PartView, ...]:
    return tuple(PartView(part=part, state=_state(split, steps, part, under_way),
                          waits_for=waits_for(split, part))
                 for part in parts(split))
