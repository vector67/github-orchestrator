import builtins
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import ClassVar, Protocol

from github_orchestrator.conversation._application.asking import Denied
from github_orchestrator.conversation._domain.conversation import (
    WAKE_MANUAL,
    Classification,
    Conversation,
    ConversationState,
)
from github_orchestrator.conversation._domain.review import Review, Verdict
from github_orchestrator.conversation._domain.thread import FetchedThread
from github_orchestrator.domain import Location, Mention, Pr, ThreadRow
from github_orchestrator.github import PullRequestState
from github_orchestrator.notifications import ThreadNews


@dataclass(frozen=True)
class PrFacts:
    title: str | None
    url: str
    base_branch: str | None
    branch: str | None
    head_sha: str | None
    is_author: bool | None
    account: str


@dataclass(frozen=True)
class Activity:
    last_action: str | None
    progress: str | None


@dataclass(frozen=True)
class ThreadActivity:
    threads: tuple[FetchedThread, ...]
    stale: tuple[FetchedThread, ...]
    cutoff: str | None
    kind: ClassVar[str] = "thread-activity"


@dataclass(frozen=True)
class Polled:
    polled_at: str
    my_last_comment_at: str | None
    comments_by_others: int
    unresolved_count: int | None
    mentions: tuple[Mention, ...] | None
    activity: ThreadActivity | None
    _announce: Callable[[ThreadNews], None] = field(repr=False, compare=False)
    _keep: Callable[[], None] = field(repr=False, compare=False)

    def commit(self) -> None:
        self._keep()

    def announce(self, news: ThreadNews) -> None:
        self._announce(news)


@dataclass(frozen=True)
class Counts:
    queued: int
    live: frozenset[str]
    proposed: int
    drafts: int
    answered: tuple[str, ...]
    rows: tuple[ThreadRow, ...]
    unreadable: tuple[str, ...]
    listed_at: str


@dataclass(frozen=True)
class Absorbed:
    threads: int
    created: tuple[Conversation, ...]
    refreshed: tuple[str, ...]
    drained: bool


class EditableConversation(Protocol):
    def approve(self, *, reply: str = "", delete_comment: bool = False,
                resolve: bool = False, message: str = "", ticket_project: str | None = None,
                ticket_title: str = "", ticket_body: str = "") -> Conversation | Denied: ...

    def rework(self, *, note: str = "",
               pointed: Sequence[tuple[str, int | None, str]] = (),
               include: Sequence[str] = ()) -> Conversation | Denied: ...

    def start_session(self, *, steer: str = "",
                      pointed: Sequence[tuple[str, int | None, str]] = (),
                      include: Sequence[str] = ()) -> Conversation | Denied: ...

    def retry(self) -> Conversation | Denied: ...

    def fix(self) -> Conversation | Denied: ...

    def stop(self) -> Conversation | Denied: ...

    def resolve(self, *, reply: str = "", delete_comment: bool = False,
                resolve: bool = False,
                thumbs_up: bool = True) -> Conversation | Denied: ...

    def reject(self, *, reply: str = "",
               delete_comment: bool = False) -> Conversation | Denied: ...

    def place(self, to: ConversationState, *, until: str = WAKE_MANUAL,
              note: str = "") -> Conversation | Denied: ...

    def unpark(self) -> Conversation | Denied: ...

    def reply(self, text: str) -> Conversation | Denied: ...

    def mark_seen(self) -> None: ...

    def edit(self, body: str, anchor: Location) -> Conversation | Denied: ...

    def enrol(self) -> Conversation | Denied: ...

    def withdraw(self) -> Conversation | Denied: ...

    def discard(self) -> Conversation | Denied: ...

    def post_now(self) -> Conversation | Denied: ...

    def plan(self, steps: Sequence[tuple[str, str | None]]) -> Conversation | Denied: ...

    def step_done(self, indexes: Sequence[int]) -> Conversation | Denied: ...

    def ready(self, sha: str, *, tests: str | None = None,
              tests_note: str | None = None, note: str | None = None,
              summary: str | None = None, confidence: str | None = None,
              confidence_note: str | None = None) -> Conversation | Denied: ...

    def move_base(self, sha: str) -> Conversation | Denied: ...

    def not_a_fix(self, classification: Classification, text: str, *,
                  ticket_project: str | None = None, ticket_title: str = "",
                  ticket_body: str = "", filed_key: str | None = None,
                  filed_url: str = "") -> Conversation | Denied: ...

    def fail(self, reason: str) -> Conversation | Denied: ...


class ConversationManager(Protocol):
    def editing(self, key: str) -> AbstractContextManager[EditableConversation]: ...

    def get(self, key: str) -> Conversation | None: ...

    def all(self) -> builtins.list[Conversation]: ...

    def open_draft(self, body: str, anchor: Location,
                   operation: str | None = None) -> Conversation | Denied: ...

    def open_thread(self, key: str, *, kind: str, path: str | None, line: int | None,
                    comment_id: int, author: str, body: str) -> str | None | Denied: ...

    def send_review(self, verdict: Verdict, body: str | None) -> Review | Denied: ...

    def reviews(self) -> Sequence[Review]: ...

    def facts(self) -> PrFacts: ...

    def activity(self, conversation: Conversation) -> Activity: ...

    def comment_url(self, conversation: Conversation, comment_id: int) -> str: ...

    def too_long(self, text: str) -> str | None: ...

    def poll(self, state: PullRequestState) -> Polled: ...

    def absorb(self, activity: ThreadActivity) -> Absorbed: ...

    def tick(self, news: ThreadNews, *, on_hold: bool) -> None: ...

    def counts(self) -> Counts: ...

    def recheck(self, conversation: Conversation) -> None: ...


class ConversationManagerFactory(Protocol):
    def of(self, pr: Pr) -> ConversationManager: ...
