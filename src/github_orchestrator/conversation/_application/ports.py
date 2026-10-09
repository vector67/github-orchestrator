from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Literal, Protocol

from github_orchestrator.conversation._application.settings import ThreadsConfig
from github_orchestrator.conversation._domain.conversation import (
    Brief,
    Comment,
    Conversation,
    PointedLine,
    ThreadVerdict,
    Ticket,
)
from github_orchestrator.conversation._domain.review import Review, Verdict
from github_orchestrator.domain import Location, Sha
from github_orchestrator.working_copies import PrCheckout, ThreadWorkspace


class WorkspaceRefused(Exception):
    pass


@dataclass(frozen=True)
class RunProgress:
    alive: bool
    elapsed: float = 0.0
    last_action: str | None = None


@dataclass(frozen=True)
class PostedReply:
    comment: Comment | None = None
    posted_key: str | None = None


@dataclass(frozen=True)
class PostedDraft:
    comment: Comment
    key: str | None = None


@dataclass(frozen=True)
class PostedReview:
    id: int | None
    drafts: tuple[PostedDraft, ...]


@dataclass(frozen=True)
class Intent:
    decision: str
    delete_comment: bool = False
    payload: str | None = None
    modifier: str = ""
    pointed: tuple[PointedLine, ...] = ()
    include: tuple[str, ...] = ()
    operation: str | None = None
    requested_at: str | None = None
    anchor: Location | None = None
    resolve: bool = False
    thumbs_up: bool = True
    message: str = ""
    ticket: Ticket | None = None


@dataclass(frozen=True)
class PendingDecision:
    intent: Intent | None = None
    reply: str | None = None
    garbled: bool = False


Kind = Literal["intent", "reply"]


class Update(Protocol):
    conversation: Conversation | None


class Held(Update, Protocol):
    unreadable: str | None


class HeldReviews(Protocol):
    @property
    def reviews(self) -> Sequence[Review]: ...

    def save(self, review: Review) -> None: ...


class Records(Protocol):
    def load(self, key: str) -> Conversation | None: ...

    def save(self, conversation: Conversation) -> None: ...

    def list(self) -> Sequence[Conversation]: ...

    def update(self, key: str) -> AbstractContextManager[Update]: ...

    def held(self, key: str) -> AbstractContextManager[Held]: ...

    def post(self, key: str, intent: Intent) -> None: ...

    def pending(self) -> Mapping[str, PendingDecision]: ...

    def pending_on(self, key: str) -> PendingDecision: ...

    def clear(self, key: str, kind: Kind) -> None: ...

    def write_action(self, key: str, line: str) -> None: ...

    def read_action(self, key: str) -> str | None: ...

    def reviews(self) -> Sequence[Review]: ...

    def update_reviews(self) -> AbstractContextManager[HeldReviews]: ...


class GitHub(Protocol):

    def post_reply(self, conversation: Conversation, body: str,
                   commit: Sha | None) -> PostedReply: ...

    def resolve_thread(self, conversation: Conversation) -> None: ...

    def unresolve_thread(self, conversation: Conversation) -> None: ...

    def react(self, conversation: Conversation, comment_id: int) -> None: ...

    def post_review_comment(self, conversation: Conversation,
                            head: str) -> PostedDraft: ...

    def thread_key_of_comment(self, comment_id: int) -> str | None: ...

    def post_review(self, verdict: Verdict, body: str | None,
                    drafts: Sequence[Conversation],
                    head: str) -> PostedReview: ...

    def delete_comment(self, conversation: Conversation) -> None: ...

    def comment_exists(self, conversation: Conversation) -> bool | None: ...

    def takes_review(self, verdict: Verdict, body: str | None) -> bool: ...

    def page(self) -> str: ...

    def comment_page(self, conversation: Conversation, comment_id: int) -> str: ...

    def too_long(self, text: str) -> str | None: ...


class Agents(Protocol):
    def run_alive(self) -> bool: ...

    def live_keys(self) -> frozenset[str]: ...

    def start_run(self, conversation: Conversation, worktree: str | None, kind: str,
                  onto: Sha | None) -> str | None: ...

    def stop_run(self, key: str) -> None: ...

    def pump(self, key: str) -> RunProgress: ...

    def open_session(self, worktree: str | None,
                     conversation: Conversation, steer: str | None,
                     skipped: bool, brief: Brief | None) -> str | None: ...


class Summaries(Protocol):
    def write_gist(self, conversation: Conversation, source: str,
                   done: Callable[[str], None]) -> None: ...

    def ask_verdict(self, conversation: Conversation,
                    done: Callable[[ThreadVerdict], None]) -> None: ...


class Clock(Protocol):
    def now(self) -> str: ...

    def stamps(self, count: int) -> list[str]: ...

    def monotonic(self) -> float: ...


class PullRequests(Protocol):
    def ci_green(self) -> bool | None: ...

    def head_sha(self) -> str | None: ...

    def base_branch(self) -> str | None: ...

    def branch(self) -> str | None: ...

    def ticket(self) -> str | None: ...

    def title(self) -> str | None: ...

    def role(self) -> str | None: ...

    def author(self) -> str | None: ...

    def is_closed(self, number: int) -> bool | None: ...


@dataclass(frozen=True)
class Ports:
    records: Records
    github: GitHub
    git: PrCheckout
    agents: Agents
    summaries: Summaries
    clock: Clock
    config: ThreadsConfig
    pull_requests: PullRequests


def thread_workspace(ports: Ports, conversation: Conversation) -> ThreadWorkspace:
    return ports.git.workspace(conversation.key, conversation.fix.base_sha)
