import builtins
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime

from github_orchestrator.conversation._adapters import (
    conversation_document as codec,
)
from github_orchestrator.conversation._adapters import record_schema as schema
from github_orchestrator.conversation._adapters.clock import (
    CREATED_AT_FORMAT,
    STARTED_AT_FORMAT,
)
from github_orchestrator.conversation._adapters.intent_text import (
    format_intent,
    parse_intent,
)
from github_orchestrator.conversation._application.ports import Intent as Intent
from github_orchestrator.conversation._application.ports import (
    Kind,
    PendingDecision,
)
from github_orchestrator.conversation._domain.conversation import (
    UNREADABLE,
    Conversation,
    UnreadableRecord,
)
from github_orchestrator.conversation._domain.review import Review
from github_orchestrator.thread_records import PrRecords, UnreadableThread

log = logging.getLogger(__name__)

ACTION_MAX_CHARS = 200

THREAD = "json"
REVIEW = "review"
REVIEWS = "reviews"
ACTION = "action"
INTENT = "intent"
REPLY = "reply"
CURSOR = "cursor"
POLL = "poll"


def _decision(intent_text: str | None, reply: str | None) -> PendingDecision:
    intent = None if intent_text is None else parse_intent(intent_text)
    return PendingDecision(intent=intent, reply=reply,
                   garbled=intent_text is not None and intent is None)


def _intent(written: bytes) -> str:
    try:
        return written.decode()
    except UnicodeDecodeError:
        return ""


def _reply(written: bytes | None) -> str | None:
    if written is None:
        return None
    try:
        text = written.decode()
    except UnicodeDecodeError:
        return None
    return text if text.strip() else None


def _clipped(line: str) -> str:
    if len(line) > ACTION_MAX_CHARS:
        return line[:ACTION_MAX_CHARS - 1] + "…"
    return line


def _listing_order(conversation: Conversation) -> tuple[bool, bool, str, str]:
    created_at = conversation.created_at
    return (conversation.state == UNREADABLE, not created_at, created_at or "",
            conversation.key)


class Update:
    def __init__(self, conversation: Conversation | None,
                 unreadable: str | None = None):
        self._conversation = conversation
        self.changed = False
        self.unreadable = unreadable

    @property
    def conversation(self) -> Conversation | None:
        return self._conversation

    @conversation.setter
    def conversation(self, conversation: Conversation | None) -> None:
        self._conversation = conversation
        self.changed = True


class Conversations:
    def __init__(self, records: PrRecords, utcnow: Callable[[], datetime]):
        self._records = records
        self._utcnow = utcnow
        self._decoded: dict[str, tuple[bytes, Conversation]] = {}

    def load(self, key: str) -> Conversation | None:
        try:
            written = self._records.load(THREAD, key)
        except UnreadableThread as exc:
            raise UnreadableRecord(str(exc)) from exc
        return None if written is None else self._decode(key, written)

    def _decode(self, key: str, written: bytes) -> Conversation:
        known = self._decoded.get(key)
        if known is not None and known[0] == written:
            return known[1]
        conversation = codec.decode(schema.current(key, written))
        self._decoded[key] = (written, conversation)
        return conversation

    def save(self, conversation: Conversation) -> None:
        now = self._utcnow()
        self._records.save(THREAD, conversation.key, schema.stamped(
            codec.encode(conversation), now.strftime(CREATED_AT_FORMAT),
            now.strftime(STARTED_AT_FORMAT)))

    def list(self) -> builtins.list[Conversation]:
        listed = []
        for key, written in self._records.list(THREAD).items():
            if written is None:
                listed.append(Conversation(key=key, state=UNREADABLE))
                continue
            try:
                listed.append(self._decode(key, written))
            except UnreadableRecord as exc:
                log.warning("Standing in for the corrupt thread %s: %s", key, exc)
                listed.append(Conversation(key=key, state=UNREADABLE))
        return sorted(listed, key=_listing_order)

    @contextmanager
    def update(self, key: str) -> Iterator[Update]:
        with self._records.lock(key):
            update = Update(self.load(key))
            yield update
            if update.changed and update.conversation is not None:
                self.save(update.conversation)

    @contextmanager
    def held(self, key: str) -> Iterator[Update]:
        with self._records.lock(key):
            try:
                update = Update(self.load(key))
            except UnreadableRecord as exc:
                update = Update(None, unreadable=str(exc))
            yield update
            if update.changed and update.conversation is not None:
                self.save(update.conversation)

    def posted_reply_ids(self) -> frozenset[int]:
        return codec.posted_reply_ids(self._readable())

    def posted_comment_keys(self) -> frozenset[str]:
        return codec.posted_comment_keys(self._readable())

    def post(self, key: str, intent: Intent) -> None:
        self._records.save(INTENT, key, format_intent(intent).encode())

    def pending(self) -> dict[str, PendingDecision]:
        replies = {key: _reply(written) for key, written in self._records.list(REPLY).items()}
        found = {key: _decision(None, reply) for key, reply in replies.items()}
        for key, written in self._records.list(INTENT).items():
            if written is None:
                log.warning("Listing %s with no decision on it: it will not read", key)
            found[key] = _decision(_intent(written or b""), replies.get(key))
        return found

    def pending_on(self, key: str) -> PendingDecision:
        try:
            written = self._records.load(INTENT, key)
        except UnreadableThread as exc:
            raise UnreadableRecord(str(exc)) from exc
        try:
            reply = _reply(self._records.load(REPLY, key))
        except UnreadableThread:
            reply = None
        return _decision(None if written is None else _intent(written), reply)

    def clear(self, key: str, kind: Kind) -> None:
        self._records.delete(INTENT if kind == "intent" else REPLY, key)

    def write_action(self, key: str, line: str) -> None:
        self._records.save(ACTION, key, _clipped(line).encode())

    def read_action(self, key: str) -> str | None:
        try:
            written = self._records.load(ACTION, key)
            line = None if written is None else written.decode().strip()
        except (UnreadableThread, UnicodeDecodeError):
            return None
        return line or None

    def cursor(self) -> schema.Document | None:
        try:
            written = self._records.load(CURSOR, POLL)
            return None if written is None else schema.json_object(written)
        except (UnreadableThread, ValueError) as exc:
            log.warning("Passing over the poll cursor: %s", exc)
            return None

    def save_cursor(self, cursor: schema.Document) -> None:
        self._records.save(CURSOR, POLL, schema.as_json(cursor))

    def reviews(self) -> builtins.list[Review]:
        found = []
        for key, written in self._records.list(REVIEW).items():
            try:
                if written is None:
                    raise ValueError("it will not read")
                found.append(codec.decode_review(
                    schema.migrated_review(schema.json_object(written))))
            except (ValueError, TypeError, AttributeError) as exc:
                log.warning("Passing over the review %s: %s", key, exc)
        return sorted(found, key=lambda review: (review.requested_at or "", review.id))

    @contextmanager
    def update_reviews(self) -> Iterator["HeldReviews"]:
        with self._records.lock(REVIEWS):
            yield HeldReviews(self.reviews(), self._save_review)

    def _save_review(self, review: Review) -> None:
        self._records.save(REVIEW, review.id, schema.as_json(codec.encode_review(review)))

    def _readable(self) -> builtins.list[schema.Document]:
        readable = []
        for key, written in self._records.list(THREAD).items():
            if written is None:
                continue
            try:
                readable.append(schema.current(key, written))
            except UnreadableRecord:
                continue
        return readable


class HeldReviews:
    def __init__(self, reviews: builtins.list[Review], save: Callable[[Review], None]):
        self._reviews = reviews
        self._save = save

    @property
    def reviews(self) -> builtins.list[Review]:
        return self._reviews

    def save(self, review: Review) -> None:
        self._save(review)
