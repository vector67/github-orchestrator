from dataclasses import asdict, dataclass, fields
from enum import Enum
from typing import Any, TypeVar

from github_orchestrator.change_detection.interface import (
    CiStatus,
    Mergeability,
    ReviewDecision,
    ReviewerStatus,
)
from github_orchestrator.domain import Mention

_Word = TypeVar("_Word", bound=Enum)


def word(kind: type[_Word], value: object) -> _Word | None:
    return next((known for known in kind if known.value == value), None)


@dataclass(frozen=True)
class Words:
    ci: CiStatus | None
    mergeability: Mergeability | None
    decision: ReviewDecision | None
    reviewers: dict[str, ReviewerStatus | None]


def words_of(snapshot: dict[str, Any]) -> Words:
    return Words(
        ci=word(CiStatus, snapshot.get("ci_status")),
        mergeability=word(Mergeability, snapshot.get("mergeable_state")),
        decision=word(ReviewDecision, snapshot.get("review_decision")),
        reviewers={login: word(ReviewerStatus, status)
                   for login, status in snapshot.get("reviewer_status", {}).items() if status},
    )


_MENTION_FIELDS = frozenset(field.name for field in fields(Mention))


def stored_mentions(mentions: tuple[Mention, ...]) -> list[dict[str, Any]]:
    return [asdict(mention) for mention in mentions]


def mentions_of(snapshot: dict[str, Any]) -> tuple[Mention, ...]:
    return tuple(Mention(**stored) for stored in snapshot.get("mentions", [])
                 if isinstance(stored, dict) and set(stored) == _MENTION_FIELDS)


_MERGEABILITY_WRITTEN_BY_GITHUB = {
    "clean": Mergeability.CLEAN.value,
    "dirty": Mergeability.CONFLICTS.value,
    "behind": Mergeability.BEHIND.value,
    "blocked": Mergeability.BLOCKED.value,
    "unstable": Mergeability.CHECKS_FAILING.value,
    "unknown": Mergeability.UNKNOWN.value,
    "draft": Mergeability.OTHER.value,
    "has_hooks": Mergeability.OTHER.value,
}

_CI_WRITTEN_BY_GITHUB = {
    "success": CiStatus.PASSING.value,
    "failure": CiStatus.FAILING.value,
}

_DECISIONS_WRITTEN_BY_GITHUB = {
    "APPROVED": ReviewDecision.APPROVED.value,
    "CHANGES_REQUESTED": ReviewDecision.CHANGES_REQUESTED.value,
    "REVIEW_REQUIRED": ReviewDecision.REVIEW_REQUIRED.value,
}

_STATUSES_WRITTEN_BY_GITHUB = {
    "APPROVED": ReviewerStatus.APPROVED.value,
    "CHANGES_REQUESTED": ReviewerStatus.CHANGES_REQUESTED.value,
    "COMMENTED": ReviewerStatus.COMMENTED.value,
    "DISMISSED": ReviewerStatus.DISMISSED.value,
    "PENDING": ReviewerStatus.PENDING.value,
}

_PASSED_WRITTEN_BY_GITHUB = frozenset({"success", "skipped", "neutral"})
_FAILED_WRITTEN_BY_GITHUB = frozenset(
    {"failure", "cancelled", "timed_out", "action_required", "stale"})


def _check(check: dict[str, Any]) -> dict[str, Any]:
    if "conclusion" not in check and "status" not in check:
        return check
    kept = {key: value for key, value in check.items()
            if key not in ("conclusion", "status")}
    return {**kept,
            "passed": check.get("conclusion") in _PASSED_WRITTEN_BY_GITHUB,
            "failed": check.get("conclusion") in _FAILED_WRITTEN_BY_GITHUB,
            "done": check.get("status") == "completed"}


def _translated(snapshot: dict[str, Any], key: str, words: dict[str, str]) -> None:
    value = snapshot.get(key)
    if isinstance(value, str) and value in words:
        snapshot[key] = words[value]


def current_form(snapshot: dict[str, Any]) -> dict[str, Any]:
    upgraded = dict(snapshot)
    _translated(upgraded, "mergeable_state", _MERGEABILITY_WRITTEN_BY_GITHUB)
    _translated(upgraded, "ci_status", _CI_WRITTEN_BY_GITHUB)
    _translated(upgraded, "review_decision", _DECISIONS_WRITTEN_BY_GITHUB)
    statuses = upgraded.get("reviewer_status")
    if isinstance(statuses, dict):
        upgraded["reviewer_status"] = {
            login: _STATUSES_WRITTEN_BY_GITHUB.get(status, status)
            for login, status in statuses.items()}
    checks = upgraded.get("checks")
    if isinstance(checks, list):
        upgraded["checks"] = [_check(check) if isinstance(check, dict) else check
                              for check in checks]
    return upgraded
