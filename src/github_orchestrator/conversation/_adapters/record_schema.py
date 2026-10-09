import json
from collections.abc import Iterable
from typing import Any

from github_orchestrator.conversation._adapters.side_words import (
    side_of,
    start_side_word,
)
from github_orchestrator.conversation._domain.conversation import (
    ABSENT,
    ANSWER,
    ASSUMED_DONE,
    CONFIRMED,
    DECLINED,
    DEFERRED,
    DISCARDED,
    DRAFT,
    ENROLLED,
    FAILED,
    FIX_RUNS,
    IN_SESSION,
    LANDED,
    LANDING,
    MAX_ATTEMPTS,
    NOT_MINE,
    OPEN,
    PICK,
    PROPOSED,
    PUSH,
    QUEUED,
    REJECTED,
    REMOVED,
    RESOLVED,
    ROLE_AUTHOR,
    ROLE_REVIEWER,
    RUNNING,
    WAITING_ON_REVIEWER,
    Classification,
    ConfidenceLevel,
    OperationKind,
    OperationState,
    ProposalKind,
    ReasonCode,
    ThreadVerdict,
    UnreadableRecord,
)
from github_orchestrator.domain import Location, Sha, Side

Document = dict[str, Any]

VERSION = 2

CONVERSATION_STATES = frozenset({OPEN, WAITING_ON_REVIEWER, ASSUMED_DONE, NOT_MINE, CONFIRMED,
                                 DEFERRED, REJECTED, RESOLVED, REMOVED, DRAFT,
                                 ENROLLED, DISCARDED})

VERDICTS = frozenset(ThreadVerdict)

FIX_STATES = frozenset({QUEUED, RUNNING, DECLINED, FAILED, PROPOSED,
                        IN_SESSION, LANDING, LANDED, ABSENT})

OPERATION_KINDS = frozenset(OperationKind) - {OperationKind.SEND_REVIEW}

REASON_CODES = frozenset(ReasonCode)

CLASSIFICATIONS = frozenset(Classification)

CLASSIFICATION_WORDS = {"conversational": Classification.QUESTION,
                        "not-a-change": Classification.QUESTION,
                        "ambiguous": Classification.UNCLEAR}

CONFIDENCE_LEVELS = frozenset(ConfidenceLevel)

PROPOSAL_KINDS = frozenset(ProposalKind)

OPERATION_STATES = frozenset(OperationState)


_FIX_OF_STATUS = {
    "queued": QUEUED,
    "working": RUNNING,
    "ready": PROPOSED,
    "skipped": DECLINED,
    "failed": FAILED,
    "rejected": IN_SESSION,
}

_STATUS_OF_FIX = {fix_state: status
                  for status, fix_state in _FIX_OF_STATUS.items()}


def _settled_fix_state(document: Document) -> str:
    if document.get("thread_sha"):
        return PROPOSED
    if document.get("classification"):
        return DECLINED
    if int(document.get("attempts") or 0) >= MAX_ATTEMPTS:
        return FAILED
    return QUEUED


def _done_steps(document: Document) -> set[str]:
    pushed = {PUSH} if document.get("pushed") else set()
    answered = {ANSWER} if document.get("replied") else set()
    return pushed | answered


CONVERSATION_WORDS = {"dismissed": RESOLVED, "removed": REMOVED}

KNOWN_STATUSES = frozenset(
    set(_FIX_OF_STATUS) | set(CONVERSATION_WORDS) | {"committed", "approved"}
)


def _legacy_states(document: Document) -> tuple[str, str, frozenset[str]]:
    status = str(document.get("status") or "")
    if status in CONVERSATION_WORDS:
        return CONVERSATION_WORDS[status], _settled_fix_state(document), (
            frozenset(_done_steps(document)))
    if status == "committed":
        return OPEN, LANDING, frozenset({PICK})
    if status == "approved":
        if not document.get("pushed"):
            return OPEN, LANDING, frozenset({PICK})
        steps = frozenset(_done_steps(document) | {PICK})
        return OPEN, LANDING if document.get("reply_error") else LANDED, steps
    return OPEN, _FIX_OF_STATUS.get(status, QUEUED), frozenset()


def _written_status(document: Document) -> str:
    written = document.get("status")
    if written is None:
        return ""
    if not isinstance(written, str):
        raise ValueError(f"status is a {type(written).__name__}, not a word")
    if written and written not in KNOWN_STATUSES:
        raise ValueError(f"status {written!r} is no word this board writes")
    return written


def _list_of(document: Document, field: str) -> list[Any]:
    value = document.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} is a {type(value).__name__}, not a list")
    return value


def _merged_flags(document: Document, written: str,
                  steps: Iterable[str]) -> frozenset[str]:
    merged = set(steps)
    if document.get("replied"):
        merged.add(ANSWER)
    if document.get("pushed") and written == "approved":
        merged.add(PUSH)
    return frozenset(merged)


def _status_of(state: str, fix_state: str, steps: frozenset[str]) -> str:
    if state == RESOLVED:
        return "dismissed"
    if fix_state in (LANDING, LANDED):
        return "approved" if PUSH in steps else "committed"
    if state == REMOVED:
        return "removed"
    return _STATUS_OF_FIX.get(fix_state, fix_state)


def _agrees_with_its_states(written: str, state: str, fix_state: str,
                            steps: frozenset[str]) -> bool:
    if not written:
        return True
    return written == _status_of(state, fix_state, steps)


def _v1_states(document: Document) -> tuple[str, str, frozenset[str]]:
    written = _written_status(document)
    word = document.get("conversation_state") or OPEN
    state = CONVERSATION_WORDS.get(word, word)
    fix_state = document.get("fix_state") or QUEUED
    steps = frozenset(_list_of(document, "fix_steps"))
    if _agrees_with_its_states(written, state, fix_state, steps):
        return state, fix_state, _merged_flags(document, written, steps)
    if written in CONVERSATION_WORDS:
        return (CONVERSATION_WORDS[written], fix_state,
                _merged_flags(document, written, steps))
    return _legacy_states(document)


def _named(document: Document, field: str, known: frozenset[str],
           fallback: str) -> str:
    name = document.get(field) or fallback
    if name not in known:
        raise ValueError(f"{field} {name!r} is no state of this board's")
    return str(name)


def _v2_states(document: Document) -> tuple[str, str, frozenset[str]]:
    return (_named(document, "conversation_state", CONVERSATION_STATES, OPEN),
            _named(document, "fix_state", FIX_STATES, QUEUED),
            frozenset(_list_of(document, "fix_steps")))


def _read_states(version: int, document: Document) -> tuple[str, str, frozenset[str]]:
    if not version:
        return _legacy_states(document)
    if version == 1:
        return _v1_states(document)
    return _v2_states(document)


def _states(version: int, document: Document) -> tuple[str, str, frozenset[str]]:
    state, fix_state, steps = _read_states(version, document)
    if state not in CONVERSATION_STATES or fix_state not in FIX_STATES:
        raise ValueError(f"{state!r} with a fix {fix_state!r} is no state of this board's")
    return state, fix_state, steps


def _run_kind(document: Document) -> str:
    kind = document.get("run_kind")
    if kind is None:
        return OperationKind.REBASE if document.get("rebase_onto") else OperationKind.FIRST
    if kind not in FIX_RUNS:
        raise ValueError(f"run_kind {kind!r} is no kind of run this board asks "
                         f"for")
    return str(kind)


def _pointed(brief: Document) -> list[Document]:
    lines = []
    for one in _list_of(brief, "pointed"):
        if not isinstance(one, dict):
            raise ValueError(f"a pointed line is a {type(one).__name__}, not "
                             f"a line of a diff")
        file, line, text = one.get("file"), one.get("line"), one.get("text")
        if not isinstance(file, str):
            raise ValueError(f"a pointed line names a {type(file).__name__} "
                             f"where it should name the file it is in")
        if line is not None and not isinstance(line, int):
            raise ValueError(f"a pointed line sits on a {type(line).__name__} "
                             f"where it should sit on a line number")
        if not isinstance(text, str):
            raise ValueError(f"a pointed line says a {type(text).__name__} "
                             f"where it should quote the code")
        lines.append({"file": file, "line": line, "text": text})
    return lines


def _brief(document: Document, field: str = "rework_brief") -> Document | None:
    brief = document.get(field)
    if brief is None:
        return None
    if not isinstance(brief, dict):
        raise ValueError(f"{field} is a {type(brief).__name__}, not a "
                         f"brief this board wrote")
    note = brief.get("note")
    if note is not None and not isinstance(note, str):
        raise ValueError(f"a rework brief notes a {type(note).__name__} where "
                         f"it should note what to change")
    return {"note": note or "", "pointed": _pointed(brief),
            "include": list(_list_of(brief, "include"))}


def _plan(document: Document) -> list[Document]:
    steps = []
    for step in _list_of(document, "plan"):
        if not isinstance(step, dict):
            raise ValueError(f"a plan step is a {type(step).__name__}, not "
                             f"something an agent wrote down")
        text = step.get("text")
        if not isinstance(text, str):
            raise ValueError(f"a plan step says a {type(text).__name__} where "
                             f"it should say what the agent will do")
        file = step.get("file")
        if file is not None and not isinstance(file, str):
            raise ValueError(f"a plan step names a {type(file).__name__} where "
                             f"it should name the file it touches")
        steps.append({"text": text, "file": file, "done": bool(step.get("done"))})
    return steps


def _line_anchor(entry: Document) -> Document | None:
    anchor = entry.get("anchor")
    if anchor is None:
        return None
    if not isinstance(anchor, dict):
        raise ValueError(f"an anchor is a {type(anchor).__name__}, not a "
                         f"place in the diff")
    path, line = anchor.get("path"), anchor.get("line")
    if not isinstance(path, str) or not isinstance(line, int):
        raise ValueError("an anchor names no path and line to hang off")
    start_line, start_side = anchor.get("start_line"), start_side_word(anchor)
    Location(path=path, line=line, side=Side.AFTER, start_line=start_line,
             start_side=side_of(start_side))
    return {"path": path, "line": line, "start_line": start_line,
            "start_side": start_side, "side": anchor.get("side")}


def _operation(entry: Any) -> Document:
    if not isinstance(entry, dict):
        raise ValueError(f"an operation is a {type(entry).__name__}, not "
                         f"work this board recorded")
    operation_id, kind, state = (entry.get("id"), entry.get("kind"),
                                 entry.get("state"))
    if not isinstance(operation_id, str) or not operation_id:
        raise ValueError("an operation carries no id to be named by")
    if kind not in OPERATION_KINDS:
        raise ValueError(f"an operation of kind {kind!r} is no work this "
                         f"board asks for")
    if state not in OPERATION_STATES:
        raise ValueError(f"an operation {state!r} is in no state work can "
                         f"be in")
    return {
        "id": operation_id,
        "kind": str(kind),
        "state": str(state),
        "requested_at": entry.get("requested_at"),
        "settled_at": entry.get("settled_at"),
        "reason": entry.get("reason"),
        "reason_code": _reason_code(entry),
        "attempts": int(entry.get("attempts") or 0),
        "text": str(entry.get("text") or ""),
        "delete_comment": bool(entry.get("delete_comment")),
        "until": entry.get("until"),
        "stopped": entry.get("stopped"),
        "brief": _brief(entry, "brief"),
        "posted_comment": entry.get("posted_comment"),
        "anchor": _line_anchor(entry),
        "review": entry.get("review"),
        "github_node_id": entry.get("github_node_id"),
    }


def _reason_code(entry: Document) -> str | None:
    code = entry.get("reason_code")
    if code is not None and code not in REASON_CODES:
        raise ValueError(f"reason code {code!r} is no reason this board gives")
    return None if code is None else str(code)


def _classification(document: Document) -> str | None:
    written = document.get("classification")
    word = CLASSIFICATION_WORDS.get(written, written) if isinstance(written, str) else None
    return str(word) if word in CLASSIFICATIONS else None


def _proposal_kind(document: Document) -> str:
    kind = document.get("proposal_kind") or ProposalKind.COMMIT
    if kind not in PROPOSAL_KINDS:
        raise ValueError(f"proposal kind {kind!r} is no proposal this board makes")
    return str(kind)


def _verdict(document: Document) -> str | None:
    verdict = document.get("verdict")
    if verdict is None:
        return None
    if verdict not in VERDICTS:
        raise ValueError(f"verdict {verdict!r} is no verdict this board gives")
    return str(verdict)


def _confidence(document: Document) -> str | None:
    written = document.get("confidence")
    return str(written) if written in CONFIDENCE_LEVELS else None


def _comment(comment: Any) -> Document:
    return {
        "id": comment.get("id"),
        "author": comment.get("author") or "",
        "author_name": comment.get("author_name") or "",
        "review_state": comment.get("review_state"),
        "body": comment.get("body") or "",
        "created_at": comment.get("created_at"),
        "updated_at": comment.get("updated_at"),
    }


def _closing_reply(document: Document) -> tuple[str, int | None]:
    reply = str(document.get("closing_reply") or "")
    reply_id = document.get("closing_reply_id")
    if reply or reply_id is not None:
        return reply, reply_id
    return (str(document.get("declined_reply") or ""),
            document.get("declined_reply_id"))


def _github_node_id(document: Document) -> str | None:
    if "github_node_id" not in document:
        return str(document.get("thread_key") or "") or None
    node_id = document["github_node_id"]
    return None if node_id is None else str(node_id)


def _sha(document: Document, field: str) -> str | None:
    written = document.get(field)
    if not written:
        return None
    if not isinstance(written, str) or Sha.parse(written) is None:
        raise ValueError(f"{field} {written!r} is no commit hash")
    return written


def _adopted_base(document: Document) -> str | None:
    if "worktree" in document and not document["worktree"]:
        return None
    return _sha(document, "base_sha")


def _newest_said(document: Document) -> str | None:
    comments = _list_of(document, "comments")
    if not comments:
        return None
    newest = comments[-1].get("id")
    return str(newest) if newest is not None else f"#{len(comments)}"


def _verdict_state(document: Document, state: str) -> str:
    if ("verdict_asks" in document or document.get("role") != ROLE_REVIEWER
            or state not in (OPEN, WAITING_ON_REVIEWER)
            or document.get("verdict_for") == _newest_said(document)):
        return state
    return OPEN


def _migrated(version: int, document: Document) -> Document:
    state, fix_state, steps = _states(version, document)
    state = _verdict_state(document, state)
    closing_reply, closing_reply_id = _closing_reply(document)
    return {
        "thread_key": str(document.get("thread_key") or ""),
        "github_node_id": _github_node_id(document),
        "role": str(document.get("role") or ROLE_AUTHOR),
        "conversation_state": state,
        "fix_state": fix_state,
        "fix_steps": sorted(steps),
        "run_kind": _run_kind(document),
        "reopened": bool(document.get("reopened")),
        "before_reply": str(document.get("before_reply") or ""),
        "replied_during_run": bool(document.get("replied_during_run")),
        "state_changed_at": document.get("state_changed_at"),
        "decidable_at": document.get("decidable_at"),
        "seen_at": document.get("seen_at"),
        "comment_id": document.get("comment_id"),
        "comment_type": str(document.get("comment_type") or ""),
        "author": str(document.get("author") or ""),
        "reviewer_name": str(document.get("reviewer_name") or ""),
        "review_state": document.get("review_state"),
        "path": document.get("path"),
        "line": document.get("line"),
        "start_line": document.get("start_line"),
        "start_side": start_side_word(document),
        "side": document.get("side"),
        "body": str(document.get("body") or ""),
        "comments": [_comment(c) for c in _list_of(document, "comments")],
        "comment_created_at": document.get("comment_created_at"),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
        "summary": str(document.get("summary") or ""),
        "is_outdated": bool(document.get("is_outdated")),
        "original_line": document.get("original_line"),
        "original_start_line": document.get("original_start_line"),
        "original_commit": document.get("original_commit"),
        "comment_deleted": bool(document.get("comment_deleted")),
        "deleted_by_board": bool(document.get("deleted_by_board")),
        "github_resolved": document.get("github_resolved"),
        "github_resolved_at": document.get("github_resolved_at"),
        "closing_reply": closing_reply,
        "closing_reply_id": closing_reply_id,
        "closing_into": document.get("closing_into"),
        "closing_on_github": bool(document.get("closing_on_github")),
        "closing_without_thumbs_up": bool(document.get("closing_without_thumbs_up")),
        "wake_on": document.get("wake_on"),
        "defer_note": str(document.get("defer_note") or ""),
        "approved_reply": str(document.get("approved_reply") or ""),
        "approved_reply_id": document.get("approved_reply_id"),
        "panel_reply_ids": list(_list_of(document, "panel_reply_ids")),
        "posted_comment_keys": list(document.get("posted_comment_keys") or ()),
        "operations": [_operation(entry)
                       for entry in _list_of(document, "operations")],
        "base_sha": _adopted_base(document),
        "attempts": int(document.get("attempts") or 0),
        "started_at": document.get("started_at"),
        "thread_sha": _sha(document, "thread_sha"),
        "tests": document.get("tests"),
        "tests_note": document.get("tests_note"),
        "agent_note": document.get("agent_note"),
        "classification": _classification(document),
        "reason": document.get("reason"),
        "plan": _plan(document),
        "fix_summary": document.get("fix_summary"),
        "confidence": _confidence(document),
        "confidence_note": document.get("confidence_note"),
        "rebase_onto": _sha(document, "rebase_onto"),
        "rebase_conflict": document.get("rebase_conflict"),
        "rework_brief": _brief(document),
        "landed_base": _sha(document, "landed_base"),
        "landed_sha": _sha(document, "landed_sha"),
        "push_error": document.get("push_error"),
        "reply_note": document.get("reply_note"),
        "reply_error": document.get("reply_error"),
        "decision_error": document.get("decision_error"),
        "pending_reply": document.get("pending_reply") or "",
        "resolve_on_land": bool(document.get("resolve_on_land")),
        "proposal_kind": _proposal_kind(document),
        "proposed_reply": document.get("proposed_reply"),
        "proposed_ticket": document.get("proposed_ticket"),
        "ticket_key": document.get("ticket_key"),
        "ticket_url": document.get("ticket_url"),
        "file_error": document.get("file_error"),
        "verdict": _verdict(document),
        "verdict_for": document.get("verdict_for"),
        "verdict_asked_for": document.get("verdict_asked_for"),
        "verdict_asks": int(document.get("verdict_asks") or 0),
        "verdict_asked_at": document.get("verdict_asked_at"),
    }


def json_object(written: bytes) -> Document:
    document = json.loads(written.decode())
    if not isinstance(document, dict):
        raise ValueError(f"it holds a {type(document).__name__}, not an object")
    return document


def as_json(document: Document) -> bytes:
    return json.dumps(document).encode()


def _version(document: Document) -> int:
    written = document.get("version")
    if not written:
        return 0
    if isinstance(written, bool) or not isinstance(written, int):
        raise ValueError(f"version {written!r} is no number")
    return written


def current(key: str, written: bytes) -> Document:
    try:
        document = json_object(written)
        return _migrated(_version(document), document)
    except (AttributeError, TypeError, ValueError) as exc:
        raise UnreadableRecord(f"thread {key} will not decode: {exc}") from exc


def migrated_review(document: Document) -> Document:
    review_id, verdict, state = (document.get("id"), document.get("verdict"),
                                 document.get("state"))
    if not isinstance(review_id, str) or not isinstance(verdict, str):
        raise ValueError("a review carries no id or verdict")
    if state not in OPERATION_STATES:
        raise ValueError(f"a review {state!r} is in no state work can be in")
    return {
        "id": review_id,
        "verdict": verdict,
        "body": document.get("body"),
        "state": str(state),
        "requested_at": document.get("requested_at"),
        "settled_at": document.get("settled_at"),
        "reason": document.get("reason"),
        "reason_code": _reason_code(document),
        "drafts": [str(key) for key in document.get("drafts") or ()],
        "posted_review": document.get("posted_review"),
    }


def stamped(document: Document, created_at: str, updated_at: str) -> bytes:
    written: Document = {"version": VERSION} | document
    written["created_at"] = document.get("created_at") or created_at
    written["updated_at"] = updated_at
    return as_json(written)
