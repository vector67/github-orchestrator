from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum

FILE = "file"
PICK = "pick"
PUSH = "push"
OPEN = "open"
ANSWER = "answer"
MATCH_DRAFT = "match-draft"
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
    pr_url: str | None = None


@dataclass(frozen=True)
class PartResult:
    text: str
    url: str | None = None


@dataclass(frozen=True)
class PartView:
    part: SplitPart
    state: PartState
    waits_for: SplitPart | None
    result: PartResult | None = None


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


def taken_from_a_report(steps: frozenset[str], reworked: SplitPart | None) -> frozenset[SplitPart]:
    if reworked is not None:
        return frozenset({reworked})
    return frozenset(part for part in SplitPart if not has_run(steps, part))


def reported(split: Split, report: Split, taken: frozenset[SplitPart]) -> Split:
    new_pr = report if SplitPart.NEW_PR in taken else split
    return replace(split, branch=new_pr.branch, base=new_pr.base, base_reason=new_pr.base_reason,
                   ticket=report.ticket if SplitPart.TICKET in taken else split.ticket,
                   accepted=split.accepted - taken)


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


def views(split: Split, steps: frozenset[str], under_way: bool,
          results: Mapping[SplitPart, PartResult]) -> tuple[PartView, ...]:
    return tuple(PartView(part=part, state=_state(split, steps, part, under_way),
                          waits_for=waits_for(split, part),
                          result=results.get(part) if has_run(steps, part) else None)
                 for part in parts(split))
