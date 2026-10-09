import json
from dataclasses import replace
from typing import Any

from github_orchestrator.conversation._adapters.side_words import (
    side_of,
    side_word,
    start_side_word,
)
from github_orchestrator.conversation._application.ports import Intent
from github_orchestrator.conversation._domain.conversation import (
    ConversationState,
    PointedLine,
    Ticket,
)
from github_orchestrator.domain import Location, Side

WAKE_MANUAL = "manual"

WAKE_CI = "ci"

WAKE_PR_PREFIX = "pr:"

APPROVE = "approve"

REWORK = "rework"

SESSION = "session"

BRIEF_MODIFIER = "brief"

EDIT_DRAFT = "edit-draft"

PLACE = "place"

DECISIONS = (APPROVE, REWORK, SESSION, "resolve", "retry", "fix", "reject",
             "defer", "unpark", "confirm", "place", "not_fixed", "stop", "reply", EDIT_DRAFT,
             "enrol", "withdraw-from-review", "discard", "post-now")

WORDS_ONLY = (REWORK, "not_fixed", "reply", EDIT_DRAFT)

ASKED = "@operation"

DELETE_MODIFIER = "delete"

GITHUB_MODIFIER = "github"

RESOLVE = "resolve"

NO_THUMBS_UP_MODIFIER = "no-thumbs-up"

WAKE_MODIFIERS = (WAKE_MANUAL, WAKE_CI, "push")


def _modifier_allowed(decision: str, modifier: str) -> bool:
    if modifier == "":
        return True
    if decision == "defer":
        return (modifier in WAKE_MODIFIERS
                or (modifier.startswith(WAKE_PR_PREFIX)
                    and modifier[len(WAKE_PR_PREFIX):].isdigit()))
    if decision in WORDS_ONLY:
        return False
    if decision == PLACE:
        return modifier in frozenset(ConversationState)
    if decision == SESSION:
        return modifier in (BRIEF_MODIFIER, DELETE_MODIFIER)
    if decision == RESOLVE:
        *slot, last = modifier.split(" ")
        return (last in (GITHUB_MODIFIER, DELETE_MODIFIER, NO_THUMBS_UP_MODIFIER)
                if not slot else
                slot in ([GITHUB_MODIFIER], [DELETE_MODIFIER])
                and last == NO_THUMBS_UP_MODIFIER)
    return modifier == DELETE_MODIFIER


def _approve_payload(payload: str | None, resolve: bool, message: str,
                     ticket: Ticket | None) -> str:
    approve: dict[str, Any] = {"reply": payload, "resolve": resolve, "message": message}
    if ticket is not None:
        approve["ticket"] = {"project": ticket.project, "title": ticket.title,
                             "body": ticket.body}
    return json.dumps(approve)


def _draft_payload(payload: str | None, anchor: Location | None) -> str:
    if anchor is None:
        raise ValueError("an edit to a draft says where it hangs")
    return json.dumps({"body": payload or "", "path": anchor.path,
                       "line": anchor.line, "start_line": anchor.start_line,
                       "start_side": side_word(anchor.start_side),
                       "side": side_word(anchor.side)})


def _brief_payload(payload: str | None, pointed: tuple[PointedLine, ...],
                   include: tuple[str, ...]) -> str:
    return json.dumps({
        "note": payload or "",
        "pointed": [{"file": one.file, "line": one.line, "text": one.text}
                    for one in pointed],
        "include": list(include),
    })


def format_intent(intent: Intent) -> str:
    """The decision as the pending decisions hold it.

    A verb a client asked for through the API carries the id and the moment
    it was asked with on a line of its own ahead of the decision, so the
    operation the drain records is the one the `202` named.
    """
    decision, payload, modifier = intent.decision, intent.payload, intent.modifier
    resolve, message = intent.resolve, intent.message
    if decision not in DECISIONS:
        raise ValueError(
            f"invalid decision {decision!r}; expected one of {DECISIONS}"
        )
    if resolve and intent.delete_comment:
        raise ValueError("a deleted comment leaves no thread to mark resolved")
    briefed = decision == SESSION and bool(intent.pointed or intent.include)
    slot = modifier or (DELETE_MODIFIER if intent.delete_comment
                        else GITHUB_MODIFIER if resolve and decision == RESOLVE
                        else BRIEF_MODIFIER if briefed
                        else "")
    if decision == RESOLVE and not intent.thumbs_up:
        slot = f"{slot} {NO_THUMBS_UP_MODIFIER}".lstrip()
    if not _modifier_allowed(decision, slot):
        raise ValueError(f"invalid modifier {slot!r} for {decision!r}")
    if resolve and decision not in (APPROVE, RESOLVE):
        raise ValueError(f"only an approve resolves the thread, not {decision!r}")
    if message and decision != APPROVE:
        raise ValueError(f"only an approve carries a message, not {decision!r}")
    if decision == APPROVE:
        payload = _approve_payload(payload, resolve, message, intent.ticket)
    if decision == REWORK or briefed:
        payload = _brief_payload(payload, intent.pointed, intent.include)
    if decision == EDIT_DRAFT:
        payload = _draft_payload(payload, intent.anchor)
    first = f"{decision} {slot}" if slot else decision
    if intent.operation is not None:
        first = f"{ASKED} {intent.operation} {intent.requested_at or ''}".rstrip() + (
            f"\n{first}")
    return first if payload is None else f"{first}\n{payload}"


def _strings(brief: dict[str, Any], field: str) -> tuple[str, ...] | None:
    values = brief.get(field, [])
    if not isinstance(values, list) or any(not isinstance(v, str)
                                           for v in values):
        return None
    return tuple(values)


def _pointed(brief: dict[str, Any]) -> tuple[PointedLine, ...] | None:
    lines = brief.get("pointed", [])
    if not isinstance(lines, list):
        return None
    read = []
    for one in lines:
        if not isinstance(one, dict):
            return None
        file, line, text = one.get("file"), one.get("line"), one.get("text")
        if not isinstance(file, str) or not isinstance(text, str):
            return None
        if line is not None and not isinstance(line, int):
            return None
        read.append(PointedLine(file=file, line=line, text=text))
    return tuple(read)


def _brief_intent(decision: str, payload: str | None) -> Intent | None:
    try:
        brief = json.loads(payload or "")
    except ValueError:
        return None
    if not isinstance(brief, dict) or not isinstance(brief.get("note", ""), str):
        return None
    pointed = _pointed(brief)
    include = _strings(brief, "include")
    if pointed is None or include is None:
        return None
    return Intent(decision=decision, payload=brief.get("note", ""),
                  pointed=pointed, include=include)


def _approve_intent(payload: str | None, modifier: str) -> Intent | None:
    if payload is None:
        return Intent(decision=APPROVE,
                      delete_comment=modifier == DELETE_MODIFIER,
                      modifier=modifier)
    try:
        approve = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(approve, dict):
        return None
    reply, resolve = approve.get("reply"), approve.get("resolve", False)
    message = approve.get("message", "")
    try:
        ticket = _ticket(approve.get("ticket"))
    except ValueError:
        return None
    if (not (reply is None or isinstance(reply, str))
            or not isinstance(resolve, bool) or not isinstance(message, str)):
        return None
    return Intent(decision=APPROVE, payload=reply, resolve=resolve,
                  message=message, ticket=ticket,
                  delete_comment=modifier == DELETE_MODIFIER,
                  modifier=modifier)


def _ticket(ticket: Any) -> Ticket | None:
    if ticket is None:
        return None
    if not isinstance(ticket, dict) or not all(
            isinstance(ticket.get(part), str) for part in ("project", "title", "body")):
        raise ValueError("an approve's ticket is a project, a title and a body")
    return Ticket(project=ticket["project"], title=ticket["title"], body=ticket["body"])


def _draft_intent(payload: str | None) -> Intent | None:
    try:
        draft = json.loads(payload or "")
    except ValueError:
        return None
    if not isinstance(draft, dict):
        return None
    body, path, line = draft.get("body"), draft.get("path"), draft.get("line")
    start_line = draft.get("start_line")
    side = side_of(draft["side"]) if draft.get("side") else Side.AFTER
    start_side = side_of(start_side_word(draft))
    if (not isinstance(body, str) or not isinstance(path, str)
            or not isinstance(line, int) or side is None
            or not (start_line is None or isinstance(start_line, int))):
        return None
    try:
        anchor = Location(path=path, line=line, start_line=start_line,
                          start_side=start_side, side=side)
    except ValueError:
        return None
    return Intent(decision=EDIT_DRAFT, payload=body, anchor=anchor)


def _resolve_intent(payload: str | None, modifier: str) -> Intent:
    words = modifier.split(" ")
    return Intent(decision=RESOLVE, payload=payload,
                  delete_comment=DELETE_MODIFIER in words,
                  resolve=GITHUB_MODIFIER in words,
                  thumbs_up=NO_THUMBS_UP_MODIFIER not in words,
                  modifier=modifier)


def _asked(text: str) -> tuple[str | None, str | None, str]:
    if not text.startswith(f"{ASKED} "):
        return None, None, text
    header, _, rest = text.partition("\n")
    _, operation, requested_at = (header.split(" ") + [""])[:3]
    return operation or None, requested_at or None, rest


def parse_intent(text: str) -> Intent | None:
    operation, requested_at, text = _asked(text)
    intent = _parsed(text)
    if intent is None or operation is None:
        return intent
    return replace(intent, operation=operation, requested_at=requested_at)


def _parsed(text: str) -> Intent | None:
    first, separator, payload = text.partition("\n")
    decision, _, modifier = first.strip().partition(" ")
    if decision not in DECISIONS or not _modifier_allowed(decision, modifier):
        return None
    if decision == APPROVE:
        return _approve_intent(payload if separator else None, modifier)
    if decision == REWORK:
        return _brief_intent(REWORK, payload if separator else None)
    if decision == SESSION and modifier == BRIEF_MODIFIER:
        return _brief_intent(SESSION, payload if separator else None)
    if decision == EDIT_DRAFT:
        return _draft_intent(payload if separator else None)
    if decision == RESOLVE:
        return _resolve_intent(payload if separator else None, modifier)
    return Intent(
        decision=decision,
        delete_comment=modifier == DELETE_MODIFIER,
        payload=payload if separator else None,
        modifier=modifier,
    )
