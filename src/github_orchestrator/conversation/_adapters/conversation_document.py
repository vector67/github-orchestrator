from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from github_orchestrator.conversation._adapters.record_schema import Document
from github_orchestrator.conversation._adapters.review_words import (
    review_state_of,
    review_state_word,
    verdict_of,
    verdict_word,
)
from github_orchestrator.conversation._adapters.side_words import side_of, side_word
from github_orchestrator.conversation._domain.conversation import (
    UNREADABLE,
    Brief,
    Classification,
    Comment,
    ConfidenceLevel,
    Conversation,
    Fix,
    Operation,
    OperationKind,
    OperationState,
    PointedLine,
    ProposalKind,
    ReasonCode,
    Run,
    Step,
    ThreadVerdict,
    Ticket,
)
from github_orchestrator.conversation._domain.review import Review
from github_orchestrator.conversation._domain.verdict import unread_of
from github_orchestrator.domain import Location, Sha, Side


def _writable(conversation: Conversation) -> None:
    if conversation.state == UNREADABLE:
        raise ValueError(
            f"thread {conversation.key} stands in for a document that would "
            f"not parse; writing it would replace that document with an empty "
            f"thread"
        )


def _hex(sha: Sha | None) -> str | None:
    return None if sha is None else str(sha)


def _sha(written: str | None) -> Sha | None:
    return None if written is None else Sha(written)


def _classified(written: str | None) -> Classification | None:
    return None if written is None else Classification(written)


def _sure(written: str | None) -> ConfidenceLevel | None:
    return None if written is None else ConfidenceLevel(written)


def _reason(written: str | None) -> ReasonCode | None:
    return None if written is None else ReasonCode(written)


def _step(step: Step) -> dict[str, Any]:
    return {"text": step.text, "file": step.file, "done": step.done}


def _brief_document(brief: Brief | None) -> dict[str, Any] | None:
    if brief is None:
        return None
    return {
        "note": brief.note,
        "pointed": [{"file": one.file, "line": one.line, "text": one.text}
                    for one in brief.pointed],
        "include": list(brief.include),
    }


def _line_anchor_document(anchor: Location | None) -> dict[str, Any] | None:
    if anchor is None:
        return None
    return {"path": anchor.path, "line": anchor.line,
            "start_line": anchor.start_line, "start_side": side_word(anchor.start_side),
            "side": side_word(anchor.side)}


def _comment(comment: Comment) -> dict[str, Any]:
    return {
        "id": comment.id,
        "author": comment.author,
        "author_name": comment.author_name,
        "review_state": review_state_word(comment.review_state),
        "body": comment.body,
        "created_at": comment.created_at,
        "updated_at": comment.updated_at,
    }


def _operation(operation: Operation) -> dict[str, Any]:
    return {
        "id": operation.id,
        "kind": operation.kind,
        "state": operation.state,
        "requested_at": operation.requested_at,
        "settled_at": operation.settled_at,
        "reason": operation.reason,
        "reason_code": operation.reason_code,
        "attempts": operation.attempts,
        "text": operation.text,
        "delete_comment": operation.delete_comment,
        "until": operation.until,
        "stopped": operation.stopped,
        "brief": _brief_document(operation.brief),
        "posted_comment": operation.posted_comment,
        "anchor": _line_anchor_document(operation.anchor),
        "review": operation.review,
        "github_node_id": operation.github_node_id,
    }


def _ticket_document(ticket: Ticket | None) -> Document | None:
    if ticket is None:
        return None
    return {"project": ticket.project, "title": ticket.title, "body": ticket.body}


def _ticket(document: Document | None) -> Ticket | None:
    if document is None:
        return None
    return Ticket(project=document["project"], title=document["title"], body=document["body"])


def encode(conversation: Conversation) -> Document:
    _writable(conversation)
    fix = conversation.fix
    return {
        "thread_key": conversation.key,
        "github_node_id": conversation.github_node_id,
        "role": conversation.role,
        "conversation_state": conversation.state,
        "fix_state": fix.state,
        "fix_steps": sorted(fix.steps),
        "run_kind": fix.run.kind,
        "reopened": conversation.reopened,
        "before_reply": conversation.before_reply,
        "replied_during_run": conversation.replied_during_run,
        "state_changed_at": conversation.state_changed_at,
        "decidable_at": conversation.decidable_at,
        "seen_at": conversation.seen_at,
        "comment_id": conversation.comment_id,
        "comment_type": conversation.comment_type,
        "author": conversation.author,
        "reviewer_name": conversation.reviewer_name,
        "review_state": review_state_word(conversation.review_state),
        "path": conversation.path,
        "line": conversation.line,
        "start_line": conversation.start_line,
        "start_side": side_word(conversation.start_side),
        "side": side_word(conversation.side),
        "body": conversation.body,
        "comments": [_comment(c) for c in conversation.comments],
        "comment_created_at": conversation.comment_created_at,
        "created_at": conversation.created_at,
        "summary": conversation.gist,
        "is_outdated": conversation.is_outdated,
        "original_line": conversation.original_line,
        "original_start_line": conversation.original_start_line,
        "original_commit": conversation.original_commit,
        "comment_deleted": conversation.comment_deleted,
        "deleted_by_board": conversation.deleted_by_board,
        "github_resolved": conversation.github_resolved,
        "github_resolved_at": conversation.github_resolved_at,
        "closing_reply": conversation.closing_reply,
        "closing_reply_id": conversation.closing_reply_id,
        "closing_into": conversation.closing_into,
        "closing_on_github": conversation.closing_on_github,
        "closing_without_thumbs_up": conversation.closing_without_thumbs_up,
        "wake_on": conversation.wake_on,
        "defer_note": conversation.defer_note,
        "approved_reply": conversation.approved_reply,
        "approved_reply_id": conversation.approved_reply_id,
        "panel_reply_ids": list(conversation.panel_reply_ids),
        "posted_comment_keys": list(conversation.posted_comment_keys),
        "operations": [_operation(op) for op in conversation.operations],
        "base_sha": _hex(fix.base_sha),
        "attempts": fix.attempts,
        "started_at": fix.started_at,
        "thread_sha": _hex(fix.thread_sha),
        "tests": fix.tests,
        "tests_note": fix.tests_note,
        "agent_note": fix.agent_note,
        "classification": fix.classification,
        "reason": fix.reason,
        "plan": [_step(step) for step in fix.plan],
        "fix_summary": fix.summary,
        "confidence": fix.confidence,
        "confidence_note": fix.confidence_note,
        "rebase_onto": _hex(fix.run.onto),
        "rebase_conflict": fix.run.conflict,
        "rework_brief": _brief_document(fix.run.brief),
        "landed_base": _hex(fix.landed_base),
        "landed_sha": _hex(fix.landed_sha),
        "push_error": fix.push_error,
        "reply_note": fix.reply_note,
        "reply_error": fix.reply_error,
        "decision_error": fix.decision_error,
        "pending_reply": fix.pending_reply,
        "resolve_on_land": fix.resolve_on_land,
        "proposal_kind": fix.kind,
        "proposed_reply": fix.reply,
        "proposed_ticket": _ticket_document(fix.ticket),
        "ticket_key": fix.ticket_key,
        "ticket_url": fix.ticket_url,
        "file_error": fix.file_error,
        "verdict": conversation.verdict,
        "verdict_for": conversation.verdict_for,
        "verdict_asked_for": conversation.verdict_asked_for,
        "verdict_asks": conversation.verdict_asks,
        "verdict_asked_at": conversation.verdict_asked_at,
    }


def _brief(brief: Document | None) -> Brief | None:
    if brief is None:
        return None
    return Brief(note=brief["note"],
                 pointed=tuple(PointedLine(file=one["file"], line=one["line"],
                                           text=one["text"])
                               for one in brief["pointed"]),
                 include=tuple(brief["include"]))


def _anchor(anchor: Document | None) -> Location | None:
    if anchor is None:
        return None
    return Location(path=anchor["path"], line=anchor["line"],
                    start_line=anchor["start_line"],
                    start_side=side_of(anchor["start_side"]),
                    side=side_of(anchor["side"]) or Side.AFTER)


def _decoded_operation(entry: Document) -> Operation:
    return Operation(
        id=entry["id"],
        kind=OperationKind(entry["kind"]),
        state=OperationState(entry["state"]),
        requested_at=entry["requested_at"],
        settled_at=entry["settled_at"],
        reason=entry["reason"],
        reason_code=_reason(entry["reason_code"]),
        attempts=entry["attempts"],
        text=entry["text"],
        delete_comment=entry["delete_comment"],
        until=entry["until"],
        stopped=entry["stopped"],
        brief=_brief(entry["brief"]),
        posted_comment=entry["posted_comment"],
        anchor=_anchor(entry["anchor"]),
        review=entry["review"],
        github_node_id=entry["github_node_id"],
    )


def _decoded_comment(entry: Document) -> Comment:
    return Comment(
        id=entry["id"],
        author=entry["author"],
        author_name=entry["author_name"],
        review_state=review_state_of(entry["review_state"]),
        body=entry["body"],
        created_at=entry["created_at"],
        updated_at=entry["updated_at"],
    )


def decode(document: Document) -> Conversation:
    conversation = _decoded(document)
    return replace(conversation, unread=unread_of(conversation))


def _decoded(document: Document) -> Conversation:
    return Conversation(
        key=document["thread_key"],
        github_node_id=document["github_node_id"],
        state=document["conversation_state"],
        role=document["role"],
        comment_id=document["comment_id"],
        comment_type=document["comment_type"],
        author=document["author"],
        reviewer_name=document["reviewer_name"],
        review_state=review_state_of(document["review_state"]),
        path=document["path"],
        line=document["line"],
        start_line=document["start_line"],
        start_side=side_of(document["start_side"]),
        side=side_of(document["side"]),
        body=document["body"],
        comments=tuple(_decoded_comment(c) for c in document["comments"]),
        comment_created_at=document["comment_created_at"],
        created_at=document["created_at"],
        updated_at=document["updated_at"],
        gist=document["summary"],
        is_outdated=document["is_outdated"],
        original_line=document["original_line"],
        original_start_line=document["original_start_line"],
        original_commit=document["original_commit"],
        comment_deleted=document["comment_deleted"],
        deleted_by_board=document["deleted_by_board"],
        github_resolved=document["github_resolved"],
        github_resolved_at=document["github_resolved_at"],
        reopened=document["reopened"],
        before_reply=document["before_reply"],
        replied_during_run=document["replied_during_run"],
        state_changed_at=document["state_changed_at"],
        decidable_at=document["decidable_at"],
        seen_at=document["seen_at"],
        closing_reply=document["closing_reply"],
        closing_reply_id=document["closing_reply_id"],
        closing_into=document["closing_into"],
        closing_on_github=document["closing_on_github"],
        closing_without_thumbs_up=document["closing_without_thumbs_up"],
        wake_on=document["wake_on"],
        defer_note=document["defer_note"],
        approved_reply=document["approved_reply"],
        approved_reply_id=document["approved_reply_id"],
        panel_reply_ids=tuple(document["panel_reply_ids"]),
        posted_comment_keys=tuple(document["posted_comment_keys"]),
        operations=tuple(_decoded_operation(op) for op in document["operations"]),
        fix=Fix(
            state=document["fix_state"],
            run=Run(
                kind=OperationKind(document["run_kind"]),
                onto=_sha(document["rebase_onto"]),
                conflict=document["rebase_conflict"],
                brief=_brief(document["rework_brief"]),
            ),
            attempts=document["attempts"],
            started_at=document["started_at"],
            base_sha=_sha(document["base_sha"]),
            thread_sha=_sha(document["thread_sha"]),
            tests=document["tests"],
            tests_note=document["tests_note"],
            agent_note=document["agent_note"],
            classification=_classified(document["classification"]),
            reason=document["reason"],
            plan=tuple(Step(text=step["text"], file=step["file"], done=step["done"])
                       for step in document["plan"]),
            summary=document["fix_summary"],
            confidence=_sure(document["confidence"]),
            confidence_note=document["confidence_note"],
            steps=frozenset(document["fix_steps"]),
            landed_base=_sha(document["landed_base"]),
            landed_sha=_sha(document["landed_sha"]),
            push_error=document["push_error"],
            reply_error=document["reply_error"],
            decision_error=document["decision_error"],
            reply_note=document["reply_note"],
            pending_reply=document["pending_reply"],
            resolve_on_land=document["resolve_on_land"],
            kind=ProposalKind(document["proposal_kind"]),
            reply=document["proposed_reply"],
            ticket=_ticket(document["proposed_ticket"]),
            ticket_key=document["ticket_key"],
            ticket_url=document["ticket_url"],
            file_error=document["file_error"],
        ),
        verdict=None if document["verdict"] is None else ThreadVerdict(document["verdict"]),
        verdict_for=document["verdict_for"],
        verdict_asked_for=document["verdict_asked_for"],
        verdict_asks=document["verdict_asks"],
        verdict_asked_at=document["verdict_asked_at"],
    )


def encode_review(review: Review) -> Document:
    return {
        "id": review.id,
        "verdict": verdict_word(review.verdict),
        "body": review.body,
        "state": review.state,
        "requested_at": review.requested_at,
        "settled_at": review.settled_at,
        "reason": review.reason,
        "reason_code": review.reason_code,
        "drafts": list(review.drafts),
        "posted_review": review.posted_review,
    }


def decode_review(document: Document) -> Review:
    return Review(
        id=document["id"],
        verdict=verdict_of(document["verdict"]),
        body=document["body"],
        state=OperationState(document["state"]),
        requested_at=document["requested_at"],
        settled_at=document["settled_at"],
        reason=document["reason"],
        reason_code=_reason(document["reason_code"]),
        drafts=tuple(document["drafts"]),
        posted_review=document["posted_review"],
    )


THREADLESS_TYPES = ("issue", "review-summary")


def posted_reply_ids(listed: Sequence[Document]) -> frozenset[int]:
    return frozenset(
        reply_id
        for document in listed
        if document["comment_type"] not in THREADLESS_TYPES
        for reply_id in (document["closing_reply_id"],
                         document["approved_reply_id"],
                         *document["panel_reply_ids"])
        if reply_id
    )


def posted_comment_keys(listed: Sequence[Document]) -> frozenset[str]:
    return frozenset(
        key
        for document in listed
        for key in document["posted_comment_keys"]
        if key
    )
