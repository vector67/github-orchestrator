from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest

from github_orchestrator.agent_runs.fake import HeldVerdicts
from github_orchestrator.agent_runs.fake import Outcome as RunOutcome
from github_orchestrator.change_detection import Poll
from github_orchestrator.conversation import (
    Classification,
    ConversationState,
    Denied,
    ErrorCode,
    Verdict,
)
from github_orchestrator.domain import Location, Side
from github_orchestrator.github import PullRequestState
from github_orchestrator.github.fake import FakeGitHub, GhError
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import fake_settings
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    World,
    at,
    commit_fix,
    drain,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    world,
)

TABLE = (Path(__file__).parents[3] / "docs" / "superpowers" / "specs"
         / "2026-09-22-board-state-machine.md")

HEADING = "## The transition table"

EMPTY = "—"


@dataclass(frozen=True)
class Edge:
    origin: str
    trigger: str
    qualifier: str
    destination: str
    code: str

    @property
    def named(self) -> str:
        return f"{self.trigger} ({self.qualifier})" if self.qualifier else (
            self.trigger)

    @property
    def pair(self) -> tuple[str, str]:
        return (self.origin, self.named)


def _cells(line: str) -> list[str]:
    bare = line.replace("`", "").strip().strip("|")
    return [cell.strip() for cell in bare.split("|")]


def _trigger(cell: str) -> tuple[str, str]:
    kind, _, qualifier = cell.partition("(")
    return kind.strip(), qualifier.rstrip(")").strip()


def _table_lines() -> list[str]:
    lines = TABLE.read_text().splitlines()
    rest = lines[lines.index(HEADING) + 1:]
    end = next((number for number, line in enumerate(rest)
                if line.startswith("## ")), len(rest))
    return [line for line in rest[:end] if line.startswith("|")]


def _edges() -> tuple[Edge, ...]:
    edges = []
    for row in _table_lines()[2:]:
        origin, trigger, destination, code = _cells(row)
        kind, qualifier = _trigger(trigger)
        edges.append(Edge(
            origin=origin, trigger=kind, qualifier=qualifier,
            destination="" if destination == EMPTY else destination,
            code="" if code == EMPTY else code))
    return tuple(edges)


EDGES = _edges()

BY_PAIR = {edge.pair: edge for edge in EDGES}

KEY = "PRRT_one"

BODY = "rename this"

NOW = "2026-09-22T10:00:00Z"

ANCHOR = Location(path="g", line=1, side=Side.AFTER)

PROPOSAL = "a proposal is waiting"

NO_PROPOSAL = "no proposal"


class SaysNoWhenAsked(FakeGitHub):
    refusing = False

    def reply_to_thread(self, key, body):
        if self.refusing:
            raise GhError("HTTP 502")
        return super().reply_to_thread(key, body)

    def post_review_comment(self, pr, head, location, body):
        if self.refusing:
            raise GhError("HTTP 422")
        return super().post_review_comment(pr, head, location, body)


@dataclass
class Bench:
    here: World
    github: SaysNoWhenAsked
    threads: Any


def _bench(tmp_path: Path, *, is_author: bool) -> Bench:
    github = SaysNoWhenAsked()
    windows = FakePrProcesses()
    here = world(fake_settings(tmp_path, agents_enabled=True), github=github, clock=at(NOW),
                 agent_runs=HeldVerdicts(windows), pr_processes=windows)
    repo_at(here.working_copies, WORKTREE, {"f": "1\n", "g": "one\n"})
    head = here.working_copies.commit(WORKTREE, {"g": "a line to draft on\n"}, "add g")
    author = github.account if is_author else f"not-{github.account}"
    github.add_pr(THE_PR, PullRequestState(author=author, base_branch="main", head_sha=head))
    here.change_detection.advance(THE_PR, Poll(state=github.pr_state(THE_PR), polled_at=NOW),
                                  set())
    here.pr_processes.open(THE_PR, Path(WORKTREE))
    return Bench(here, github, here.conversation_managers.of(THE_PR))


def _asked(bench: Bench, key: str, verb: Callable[[Any, str], Any]) -> None:
    with bench.threads.editing(key) as conversation:
        asked = verb(conversation)
    assert not isinstance(asked, Denied), asked
    drain(bench.threads)


@dataclass(frozen=True)
class Card:
    name: str
    build: Callable[[Bench], str]
    is_author: bool = True
    qualifiers: frozenset[str] = field(default_factory=frozenset)

    def then(self, name: str, verb: Callable[[Any, str], Any], *qualifiers: str) -> "Card":
        def built(bench: Bench) -> str:
            key = self.build(bench)
            _asked(bench, key, verb)
            return key
        return Card(name, built, self.is_author, frozenset(qualifiers) or self.qualifiers)


def _opened(bench: Bench) -> str:
    on_github(bench.github, KEY, said(1, BODY))
    hear(bench.threads)
    return KEY


def _reviewer_says_more(bench: Bench, key: str) -> None:
    record = bench.github.prs[THE_PR]
    record.threads = [
        replace(thread, comments=(*thread.comments, said(900, "one more thing")))
        if thread.key == key else thread for thread in record.threads]
    hear(bench.threads)


def _proposed(bench: Bench) -> str:
    _opened(bench)
    propose(bench.here, bench.threads, KEY)
    return KEY


def _queued(bench: Bench) -> str:
    _proposed(bench)
    _reviewer_says_more(bench, KEY)
    return KEY


def _working(bench: Bench) -> str:
    _queued(bench)
    start_run(bench.here, bench.threads, finishes=False)
    return KEY


def _declined(bench: Bench) -> str:
    _opened(bench)
    start_run(bench.here, bench.threads)
    with bench.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.NEEDS_HUMAN, "which helper?")
    return KEY


def _failed(bench: Bench) -> str:
    _opened(bench)
    for _ in range(bench.threads.get(KEY).run_holder.attempts_allowed):
        start_run(bench.here, bench.threads)
        with bench.threads.editing(KEY) as editable:
            editable.fail("boom")
    return KEY


def _rebasing(bench: Bench) -> str:
    _proposed(bench)
    bench.here.working_copies.commit(WORKTREE, {"f": "theirs\n"}, "someone else")
    bench.here.agent_runs.script(RunOutcome(finishes=False))
    _asked(bench, KEY, lambda conversation: conversation.approve(reply="landing this"))
    return KEY


def _reworking(bench: Bench) -> str:
    _proposed(bench)
    bench.here.agent_runs.script(RunOutcome(finishes=False))
    _asked(bench, KEY, lambda conversation: conversation.rework(note="narrow it"))
    return KEY


def _draft(bench: Bench) -> str:
    drafted = bench.threads.open_draft(BODY, ANCHOR)
    assert not isinstance(drafted, Denied), drafted
    key: str = drafted.key
    return key


QUEUED = Card("queued", _queued)

WORKING = Card("working", _working)

A_PROPOSAL = Card("proposed", _proposed, qualifiers=frozenset({PROPOSAL}))

DECLINED_RUN = Card("declined", _declined, qualifiers=frozenset({NO_PROPOSAL}))

FAILED_RUN = Card("failed", _failed, qualifiers=frozenset({NO_PROPOSAL}))

IN_SESSION = A_PROPOSAL.then("in-session", lambda conversation: conversation.start_session())

REWORKED = Card("rework", _reworking)

LANDING = Card("rebasing", _rebasing, qualifiers=frozenset({"the kind is rebase"}))


def _replied(card: Card) -> Card:
    return card.then(f"{card.name}-replied", lambda conversation: conversation.reply("a word"))


def _deferred(card: Card) -> Card:
    return card.then(f"{card.name}-deferred", lambda conversation: conversation.place(
        ConversationState.DEFERRED))


def _placed_by(word: str) -> Callable[[Bench], str]:
    def placed(bench: Bench) -> str:
        _opened(bench)
        agent_runs = bench.here.agent_runs
        assert isinstance(agent_runs, HeldVerdicts)
        agent_runs.give(word)
        return KEY
    return placed


ASSUMED_DONE = Card("assumed-done", _placed_by("assumed-done"), is_author=False)

NOT_MINE = Card("not-mine", _placed_by("not-mine"), is_author=False)

A_DRAFT = Card("draft", _draft, is_author=False)

AN_ENROLLED_DRAFT = A_DRAFT.then("enrolled", lambda conversation: conversation.enrol())

CLOSED_BY_RESOLVE = A_PROPOSAL.then("resolved", lambda conversation: conversation.resolve(reply="thanks"),
                                    "closed by resolve")

CLOSED_BY_REJECT = A_PROPOSAL.then("rejected",
                                   lambda conversation: conversation.reject(reply="not this one"),
                                   "closed by reject")

CLOSED_BY_APPROVE = A_PROPOSAL.then("approved",
                                    lambda conversation: conversation.approve(reply="landing this"),
                                    "closed by approve")

CLOSED_BY_DISCARD = A_DRAFT.then("discarded", lambda conversation: conversation.discard(),
                                 "closed by discard")

CLOSED_BY_CONFIRM = ASSUMED_DONE.then("confirmed", lambda conversation: conversation.place(
    ConversationState.DONE), "closed by confirm")

FIXTURES: dict[str, tuple[Card, ...]] = {
    ConversationState.DRAFT: (A_DRAFT,),
    ConversationState.ENROLLED: (AN_ENROLLED_DRAFT,),
    ConversationState.QUEUED: (QUEUED,),
    ConversationState.WORKING: (WORKING,),
    ConversationState.IN_SESSION: (IN_SESSION,),
    ConversationState.REWORK: (REWORKED,),
    ConversationState.LANDING: (LANDING,),
    ConversationState.READY: (A_PROPOSAL, DECLINED_RUN, FAILED_RUN),
    ConversationState.WAITING: (_replied(A_PROPOSAL), _replied(DECLINED_RUN)),
    ConversationState.ASSUMED_DONE: (ASSUMED_DONE,),
    ConversationState.NOT_MINE: (NOT_MINE,),
    ConversationState.DEFERRED: (_deferred(A_PROPOSAL), _deferred(DECLINED_RUN)),
    ConversationState.DONE: (CLOSED_BY_RESOLVE, CLOSED_BY_REJECT,
                             CLOSED_BY_APPROVE, CLOSED_BY_DISCARD, CLOSED_BY_CONFIRM),
}

VERBS: dict[str, Callable[[Any, str], Any]] = {
    "approve": (lambda conversation: conversation.approve(reply="landing this")),
    "rework": (lambda conversation: conversation.rework(note="the other way round")),
    "retry": (lambda conversation: conversation.retry()),
    "start-session": (lambda conversation: conversation.start_session()),
    "resolve": (lambda conversation: conversation.resolve(reply="thanks")),
    "reject": (lambda conversation: conversation.reject(reply="not this one")),
    "defer": (lambda conversation: conversation.place(ConversationState.DEFERRED)),
    "unpark": (lambda conversation: conversation.unpark()),
    "confirm": (lambda conversation: conversation.place(ConversationState.DONE)),
    "place": (lambda conversation: conversation.place(ConversationState.WAITING)),
    "reply": (lambda conversation: conversation.reply("a word")),
    "stop": (lambda conversation: conversation.stop()),
    "edit-draft": (lambda conversation: conversation.edit("the other way round", ANCHOR)),
    "enrol": (lambda conversation: conversation.enrol()),
    "withdraw-from-review": (lambda conversation: conversation.withdraw()),
    "discard": (lambda conversation: conversation.discard()),
    "post-now": (lambda conversation: conversation.post_now()),
}


def _ready(bench: Bench, key: str) -> None:
    sha = commit_fix(bench.here, key, {"f": "2\n"})
    with bench.threads.editing(key) as editable:
        assert not isinstance(editable.ready(sha), Denied)


def _ready_rebased(bench: Bench, key: str) -> None:
    working_copies = bench.here.working_copies
    checkout = working_copies.thread_checkout(THE_PR, key)
    working_copies.branches[working_copies.branch_at(checkout)] = str(
        bench.threads.get(key).fix.base_sha)
    _ready(bench, key)


def _declines(bench: Bench, key: str) -> None:
    with bench.threads.editing(key) as editable:
        declined = editable.not_a_fix(Classification.NEEDS_HUMAN, "which helper?")
    assert not isinstance(declined, Denied), declined


def _github_says_no(verb: Callable[[Any, str], Any]) -> Callable[[Bench, str], None]:
    def refused(bench: Bench, key: str) -> None:
        bench.github.refusing = True
        _asked(bench, key, verb)
    return refused


def _picked_up(bench: Bench, key: str) -> None:
    start_run(bench.here, bench.threads, finishes=False)


def _lost(bench: Bench, key: str) -> None:
    bench.threads = bench.here.conversation_managers.of(THE_PR)
    bench.threads.tick(FakeNotifications(), on_hold=True)


def _sent(bench: Bench, key: str) -> None:
    sent = bench.threads.send_review(Verdict.COMMENT, "a few things")
    assert not isinstance(sent, Denied), sent
    drain(bench.threads)


@dataclass(frozen=True)
class Event:
    act: Callable[[Bench, str], None]
    drains: bool


RUN_HOLDERS = (ConversationState.QUEUED, ConversationState.WORKING,
               ConversationState.IN_SESSION, ConversationState.REWORK,
               ConversationState.LANDING)

PARKABLE = (ConversationState.READY, ConversationState.WAITING, ConversationState.DEFERRED,
            ConversationState.ASSUMED_DONE, ConversationState.NOT_MINE)

EVENTS: dict[tuple[str, str], Event] = {
    (ConversationState.QUEUED, "pick-up"): Event(_picked_up, drains=True),
    (ConversationState.REWORK, "pick-up"): Event(_picked_up, drains=True),
    (ConversationState.ENROLLED, "posted"): Event(_sent, drains=True),
    (ConversationState.DRAFT, "settle-refused"):
        Event(_github_says_no(lambda conversation: conversation.post_now()), drains=True),
    **{(state, "settle-applied"): Event(_ready, drains=False)
       for state in (ConversationState.WORKING, ConversationState.IN_SESSION,
                     ConversationState.REWORK)},
    (ConversationState.LANDING, "settle-applied (the kind is rebase)"):
        Event(_ready_rebased, drains=False),
    **{(state, "settle-refused"): Event(_declines, drains=False) for state in RUN_HOLDERS},
    **{(state, "settle-refused"): Event(_github_says_no(VERBS["reply"]), drains=True)
       for state in PARKABLE},
    **{(state, "requeue"): Event(_lost, drains=False)
       for state in (ConversationState.WORKING, ConversationState.REWORK,
                     ConversationState.LANDING)},
    **{(edge.origin, edge.named): Event(_reviewer_says_more, drains=False) for edge in EDGES
       if edge.trigger == "comment" and edge.destination
       and edge.qualifier not in CLOSED_BY_DISCARD.qualifiers},
}

BEHIND_A_WAITING_APPROVE = frozenset(
    edge.pair for edge in EDGES
    if edge.origin == ConversationState.LANDING and edge.trigger in VERBS
    and edge.code != ErrorCode.OPERATION_OUTSTANDING)

SCHEDULED = (ConversationState.QUEUED, ConversationState.REWORK)

KIND_OF_TRIGGER = {"reply": "reply", "resolve": "resolve", "reject": "reject",
                   "post-now": "post-now", "approve": "approve"}


def _named(edge: Edge) -> str:
    return f"{edge.origin}-{edge.named}"


def _cards(edge: Edge) -> tuple[Card, ...]:
    return tuple(card for card in FIXTURES[edge.origin]
                 if not edge.qualifier or edge.qualifier in card.qualifiers)


def _driven(edge: Edge) -> bool:
    return edge.pair not in BEHIND_A_WAITING_APPROVE and (
        edge.trigger in VERBS or edge.pair in EVENTS)


def _settles_at(edge: Edge) -> str:
    settled = BY_PAIR.get((edge.destination,
                           f"settle-applied (the kind is {KIND_OF_TRIGGER.get(edge.trigger)})"))
    return settled.destination if settled else edge.destination


def _first_after(edge: Edge, card: Card) -> str:
    if not card.is_author:
        return edge.destination
    qualified = [f"first ({qualifier})" for qualifier in card.qualifiers
                 if edge.destination == edge.origin]
    first = next((BY_PAIR[(edge.destination, named)] for named in (*qualified, "first")
                  if (edge.destination, named) in BY_PAIR), None)
    return first.destination if first and first.destination else edge.destination


def _drains(edge: Edge) -> bool:
    return edge.trigger in VERBS or EVENTS[edge.pair].drains


def _lands_at(edge: Edge, card: Card) -> str:
    settled = _first_after(edge, card) if edge.trigger == "comment" else _settles_at(edge)
    picked_up = BY_PAIR.get((settled, "pick-up"))
    if _drains(edge) and settled in SCHEDULED and picked_up and picked_up.destination:
        return picked_up.destination
    return settled


def _act(bench: Bench, key: str, edge: Edge) -> None:
    if edge.trigger in VERBS:
        _asked(bench, key, VERBS[edge.trigger])
    else:
        EVENTS[edge.pair].act(bench, key)


def _cases(edges: list[Edge], kept: Callable[[Edge, Card], bool] = lambda edge, card: True,
           ) -> list[Any]:
    return [pytest.param(edge, card, id=f"{_named(edge)}-{card.name}")
            for edge in edges for card in _cards(edge) if kept(edge, card)]


DRAFTING_VERBS = ("edit-draft", "enrol", "withdraw-from-review", "discard", "post-now")


def _refusal_worth_proving(edge: Edge, card: Card) -> bool:
    if card in (FAILED_RUN, CLOSED_BY_REJECT):
        return False
    if edge.trigger not in DRAFTING_VERBS or edge.origin in (ConversationState.DRAFT,
                                                              ConversationState.ENROLLED):
        return True
    if edge.origin == ConversationState.DONE:
        return card == CLOSED_BY_RESOLVE
    return edge.origin == ConversationState.READY and card == A_PROPOSAL


def test_every_row_is_written_in_the_contracts_vocabulary():
    for edge in EDGES:
        assert edge.origin in tuple(ConversationState), _named(edge)
        assert not edge.destination or edge.destination in tuple(ConversationState), _named(edge)
        assert not edge.code or edge.code in tuple(ErrorCode), _named(edge)
        assert not (edge.destination and edge.code), (
            f"{_named(edge)}: an edge either moves the thread or refuses it")


def test_the_table_carries_a_row_for_every_state():
    assert {edge.origin for edge in EDGES} == set(ConversationState)


@pytest.mark.parametrize(
    "edge,card", _cases([edge for edge in EDGES if edge.destination and _driven(edge)]))
def test_an_allowed_edge_leaves_the_thread_where_the_table_says(edge, card, tmp_path):
    bench = _bench(tmp_path, is_author=card.is_author)
    key = card.build(bench)
    built = bench.threads.get(key).standing
    assert built == edge.origin

    _act(bench, key, edge)

    landed = bench.threads.get(key).standing
    assert landed == _lands_at(edge, card), (
        "a verb that posts to GitHub settles in the pass that takes it, and a comment "
        "on an author's thread asks for a first run, so each ends where the table's "
        "following edge says")


@pytest.mark.parametrize(
    "edge,card", _cases([edge for edge in EDGES
                          if edge.code and edge.trigger in VERBS and _driven(edge)],
                         _refusal_worth_proving))
def test_a_refused_edge_comes_back_with_the_code_the_table_names(edge, card, tmp_path):
    bench = _bench(tmp_path, is_author=card.is_author)
    key = card.build(bench)
    built = bench.threads.get(key).standing
    assert built == edge.origin

    with bench.threads.editing(key) as conversation:
        refused = VERBS[edge.trigger](conversation)

    assert isinstance(refused, Denied), (
        f"{_named(edge)} is refused {edge.code} and the thread takes it")
    assert refused.code == edge.code, refused.reason
