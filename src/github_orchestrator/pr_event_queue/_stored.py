import dataclasses
import types
import typing
from enum import Enum
from typing import Any

from github_orchestrator.change_detection import (
    BecameMergeable,
    BecameUnmergeable,
    CiFailed,
    CiSucceeded,
    HeadChanged,
    PrClosed,
    PushedSinceReview,
    ReviewDecisionChanged,
    ReviewRequested,
)
from github_orchestrator.conversation import ThreadActivity
from github_orchestrator.domain import Pr
from github_orchestrator.pr_event_queue.interface import Queued

FORMAT = 2

_KINDS: dict[str, type[Any]] = {
    kind.kind: kind for kind in (CiSucceeded, CiFailed, BecameUnmergeable, BecameMergeable,
                                 ReviewDecisionChanged, PushedSinceReview, HeadChanged,
                                 ReviewRequested, PrClosed, ThreadActivity)
}


class Unreadable(Exception):
    pass


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: _plain(getattr(value, field.name))
                for field in dataclasses.fields(value)}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def document(pr: Pr, item: Queued) -> dict[str, Any]:
    return {"format": FORMAT, "type": item.kind, "repo": str(pr.repo), "pr": pr.number,
            "payload": _plain(item)}


def _typed(hint: Any, value: Any) -> Any:
    origin = typing.get_origin(hint)
    if origin in (typing.Union, types.UnionType):
        if value is None:
            return None
        arms = [arm for arm in typing.get_args(hint) if arm is not type(None)]
        return _typed(arms[0], value) if len(arms) == 1 else value
    if origin is tuple:
        if not isinstance(value, list):
            raise Unreadable(f"expected a list, found {value!r}")
        [inner, _] = typing.get_args(hint)
        return tuple(_typed(inner, item) for item in value)
    if isinstance(hint, type) and issubclass(hint, Enum):
        try:
            return hint(value)
        except ValueError as exc:
            raise Unreadable(str(exc)) from exc
    if isinstance(hint, type) and dataclasses.is_dataclass(hint):
        return _built(hint, value)
    return value


def _built(kind: type[Any], value: Any) -> Any:
    if not isinstance(value, dict):
        raise Unreadable(f"expected an object for {kind.__name__}, found {value!r}")
    hints = typing.get_type_hints(kind)
    given = {field.name: _typed(hints[field.name], value.get(field.name))
             for field in dataclasses.fields(kind)
             if field.name in value or type(None) in typing.get_args(hints[field.name])}
    try:
        return kind(**given)
    except TypeError as exc:
        raise Unreadable(str(exc)) from exc


def item_of(stored: Any) -> Queued:
    if not isinstance(stored, dict):
        raise Unreadable(f"expected an object, found {type(stored).__name__}")
    kind = _KINDS.get(str(stored.get("type")))
    if kind is None:
        raise Unreadable(f"no event is called {stored.get('type')!r}")
    payload = stored.get("payload", {})
    if stored.get("format") != FORMAT:
        payload = _written_before(kind, payload)
    item: Queued = _built(kind, payload)
    return item


_DECISIONS_WRITTEN_BY_GITHUB = {
    "APPROVED": "approved",
    "CHANGES_REQUESTED": "changes-requested",
    "REVIEW_REQUIRED": "review-required",
}

_SIDES_WRITTEN_BY_GITHUB = {"LEFT": "before", "RIGHT": "after"}

_REVIEW_STATES_WRITTEN_BY_GITHUB = {
    "APPROVED": "approved",
    "CHANGES_REQUESTED": "changes-requested",
    "COMMENTED": "commented",
    "DISMISSED": "dismissed",
    "PENDING": "pending",
}

_ANCHOR_KEYS = ("is_outdated", "start_line", "original_line", "original_start_line",
                "original_commit")


def _word(words: dict[str, str], value: Any, known: set[str]) -> Any:
    word = words.get(value, value) if isinstance(value, str) else value
    return word if word in known else None


def _comment_written_before(comment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": comment.get("id"),
        "author": comment.get("author") or "ghost",
        "body": comment.get("body") or "",
        "created_at": comment.get("created_at"),
        "updated_at": comment.get("updated_at"),
        "author_name": comment.get("author_name") or "",
        "review_state": _word(_REVIEW_STATES_WRITTEN_BY_GITHUB, comment.get("review_state"),
                              set(_REVIEW_STATES_WRITTEN_BY_GITHUB.values())),
    }


def _thread_written_before(thread: dict[str, Any]) -> dict[str, Any]:
    anchored = any(key in thread for key in _ANCHOR_KEYS)
    return {
        "key": str(thread["key"]),
        "kind": thread.get("kind") or "review",
        "comments": [_comment_written_before(comment)
                     for comment in thread.get("comments") or []],
        "anchor": {
            "is_outdated": bool(thread.get("is_outdated")),
            "side": _word(_SIDES_WRITTEN_BY_GITHUB, thread.get("diff_side"),
                          set(_SIDES_WRITTEN_BY_GITHUB.values())),
            **{key: thread.get(key) for key in _ANCHOR_KEYS if key != "is_outdated"},
        } if anchored else None,
        "path": thread.get("path"),
        "line": thread.get("line"),
        "is_resolved": thread.get("is_resolved"),
        "resolved_by": thread.get("resolved_by"),
        "state": _word(_REVIEW_STATES_WRITTEN_BY_GITHUB, thread.get("state"),
                       set(_REVIEW_STATES_WRITTEN_BY_GITHUB.values())),
    }


def _written_before(kind: type[Any], payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    decisions = set(_DECISIONS_WRITTEN_BY_GITHUB.values())
    if kind is CiSucceeded:
        return {"checks": [check.get("name", "") if isinstance(check, dict) else check
                           for check in payload.get("checks", [])]}
    if kind is ReviewDecisionChanged:
        return {"before": _word(_DECISIONS_WRITTEN_BY_GITHUB, payload.get("from"), decisions),
                "after": _word(_DECISIONS_WRITTEN_BY_GITHUB, payload.get("to"), decisions),
                "reviewer": payload.get("reviewer")}
    if kind is PrClosed:
        return {"merged": bool(payload.get("merged", False)),
                "no_longer_relevant": payload.get("reason") == "no-longer-relevant"}
    if kind is ThreadActivity:
        return {"threads": [_thread_written_before(thread)
                            for thread in payload.get("threads", [])],
                "stale": [_thread_written_before(thread) for thread in payload.get("stale", [])],
                "cutoff": payload.get("cutoff")}
    return payload
