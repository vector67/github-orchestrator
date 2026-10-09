import argparse
import dataclasses
import os
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import dishka

from github_orchestrator.agent_runs.fake import (
    FixingThread,
    HeldVerdicts,
    RebasingFix,
    Reworking,
)
from github_orchestrator.agent_runs.fake import Outcome as RunOutcome
from github_orchestrator.board_api import BoardApi, Dashboard
from github_orchestrator.board_api.fake import FakeManagerPanel
from github_orchestrator.board_api.interface import Dashboards
from github_orchestrator.change_detection import ChangeDetection, Poll
from github_orchestrator.conversation import (
    Classification,
    Conversation,
    ConversationManager,
    ConversationManagerFactory,
    ConversationState,
    Denied,
    EditableConversation,
)
from github_orchestrator.desktop.fake import FakeDesktop
from github_orchestrator.domain import Pr
from github_orchestrator.domain import Repo as RepoName
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    ReviewState,
    Thread,
    ThreadComment,
)
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.terminal_sessions import TerminalSessions
from github_orchestrator.wiring import preview_container

__all__: list[str] = []

PR = Pr(RepoName("acme", "widgets"), 7)
PR_TITLE = "Rework the invoice writer"
PR_BRANCH = "rework-the-invoice-writer"

MOMENT = "2026-09-12T09:00:00Z"
LAST_RUN_ENDED = datetime.fromisoformat("2026-09-12T08:41:00+00:00")
BASE_BRANCH = "main"
RECHECK_SECONDS = 5.0

@dataclasses.dataclass(frozen=True)
class Repo:
    worktree: str
    base_branch: str = BASE_BRANCH
    head: str = ""


@dataclasses.dataclass(frozen=True)
class Card:
    comment_id: int
    key: str
    gist: str
    path: str
    line: int
    author: str = "anna"
    author_name: str = "Anna Example"
    review_state: ReviewState | None = ReviewState.CHANGES_REQUESTED
    replies: tuple[ThreadComment, ...] = ()
    on_github: bool = True

    @property
    def body(self) -> str:
        return f"{self.gist}\n\nAnd a second paragraph, for the panel to draw."

    def thread(self, *later: ThreadComment) -> Thread:
        return Thread(key=self.key, kind=CommentKind.REVIEW, path=self.path, line=self.line,
                      comments=(ThreadComment(id=self.comment_id, author=self.author,
                                              body=self.body, created_at=MOMENT,
                                              author_name=self.author_name,
                                              review_state=self.review_state),
                                *self.replies, *later))


def _said(comment_id: int, author: str, author_name: str, body: str,
          when: str) -> ThreadComment:
    return ThreadComment(id=comment_id, author=author, author_name=author_name, body=body,
                         created_at=when)


READY = Card(9000001, "PRRT_ready",
             "the proposal waiting on your decision: a finished plan, medium "
             "confidence and tests nobody verified",
             "billing/invoice_writer.py", 142,
             replies=(_said(9100001, "anna", "Anna Example",
                            "And the same guard belongs in the reader.",
                            "2026-09-12T09:30:00Z"),
                      _said(9100002, "mira", "Mira Sample",
                            "Agreed — the silent skip has bitten us twice.",
                            "2026-09-12T09:45:00Z")))
REOPENED = Card(9000002, "PRRT_reopened",
                "the reopened mark, top of Ready for you after a reply came back to "
                "work you had already spoken for",
                "billing/invoice_writer.py", 88)
DECLINED = Card(9000003, "PRRT_declined",
                "a fix the agent declined as one only the author can decide, under a "
                "bot author with no display name",
                "adapters/store.py", 12, author="copilot", author_name="",
                review_state=None)
FAILED = Card(9000004, "PRRT_failed",
              "a fix that failed three attempts, under the longest author name the "
              "rail has to fit",
              "migrations/0042_add_column.py", 5, author="jo",
              author_name="Jo Ó'Brien-Vandermolenaar", review_state=None)
ASSUMED_DONE = Card(9000019, "PRRT_assumed_done",
                    "thanks, the early return reads much better now",
                    "billing/errors.py", 12, review_state=ReviewState.APPROVED)
REMOVED = Card(9000005, "PRRT_removed", "the row for a comment GitHub no longer has",
               "billing/invoice_writer.py", 201)
WORKING = Card(9000006, "PRRT_working",
               "a live run part way through its plan, the panel that is swapped whole "
               "every poll",
               "billing/reader.py", 61)
QUEUED = Card(9000007, "PRRT_queued",
              "a fix queued behind the run slots, with nothing to show yet",
              "billing/errors.py", 30)
IN_SESSION = Card(9000008, "PRRT_rework", "a rework session you opened in a pane",
                  "billing/guard.py", 17)
REWORKING = Card(9000018, "PRRT_reworking",
                 "a fix you sent back with a note and a pointed line, queued for the "
                 "rework run that carries them",
                 "billing/guard.py", 18)
REBASING = Card(9000009, "PRRT_rebasing",
                "a rebase run, naming the head it is moving onto",
                "billing/invoice_writer.py", 300)
WAITING = Card(9000011, "PRRT_waiting",
               "a proposal waiting on the reviewer, low confidence with a failed test "
               "verdict and the note behind it",
               "billing/api.py", 44)
DEFERRED = Card(9000012, "PRRT_deferred",
                "a conversation parked until another PR closes, showing what it waits "
                "for and the note you wrote",
                "billing/invoice_writer.py", 1)
REJECTED = Card(9000013, "PRRT_rejected",
                "a proposal you rejected, where unpark can only re-queue a fresh run",
                "billing/parser.py", 9)
LANDED = Card(9000014, "PRRT_landed",
              "a landed fix whose fold diffs the cherry-pick either side, every step "
              "done and the tests passed",
              "billing/header.py", 22)
RESOLVED = Card(9000015, "PRRT_resolved", "a conversation settled by a closing reply",
                "billing/header.py", 26)
PUSH_REJECTED = Card(9000016, "PRRT_push_rejected",
                     "a landing whose push git refused, back in Ready for you wearing "
                     "the failure row instead of a fix",
                     "billing/reader.py", 1)
REPLY_REFUSED = Card(9000017, "PRRT_reply_refused",
                     "a landing whose reply GitHub refused, holding the words you wrote "
                     "for the next try",
                     "billing/header.py", 31, on_github=False)
REPLY_PROPOSED = Card(9000020, "PRRT_reply_proposed",
                      "why does the reader hold one tax table at a time?",
                      "billing/reader.py", 40)

TICKET_PROPOSED = Card(9000021, "PRRT_ticket_proposed",
                       "every export should share one tax-rate cache, not just this one",
                       "billing/cache.py", 18)

TICKET_FILING = Card(9000022, "PRRT_ticket_filing",
                     "the writer should read units from the same table as the reader",
                     "billing/units.py", 12)
TICKET_FILED = Card(9000023, "PRRT_ticket_filed",
                    "every exporter repeats this header logic; worth one helper",
                    "billing/header.py", 52)
TICKET_UNFILED = Card(9000024, "PRRT_ticket_unfiled",
                      "the CLI should report export progress, not only the result",
                      "cli/billing.py", 8)

AUTHOR_CARDS = (READY, REPLY_PROPOSED, TICKET_PROPOSED, REOPENED, DECLINED, ASSUMED_DONE, FAILED,
                REMOVED, WORKING, QUEUED, IN_SESSION, REWORKING, REBASING, WAITING, DEFERRED,
                REJECTED, LANDED, RESOLVED, PUSH_REJECTED, REPLY_REFUSED, TICKET_FILING,
                TICKET_FILED, TICKET_UNFILED)

PR_AUTHOR = "mei"
PR_AUTHOR_NAME = "Mei Placeholder"
COLLEAGUE = "tomas"
COLLEAGUE_NAME = "Tomas Testcase"


def _answer(comment_id: int, body: str, when: str) -> ThreadComment:
    return _said(comment_id, PR_AUTHOR, PR_AUTHOR_NAME, body, when)


def reviewer_cards(viewer: str) -> tuple[Card, ...]:
    return (
        Card(9200001, "PRRT_answered",
             "the author's answer to a thread you raised, at the top of Answered "
             "because it is yours",
             "billing/reader.py", 96, author=viewer, author_name="",
             replies=(_answer(9200101, "Moved the guard into _collect().",
                              "2026-09-12T10:00:00Z"),)),
        Card(9200002, "PRRT_answered_theirs",
             "an answer on a colleague's thread, under yours however new the reply is",
             "billing/invoice_writer.py", 118, author=COLLEAGUE, author_name=COLLEAGUE_NAME,
             replies=(_answer(9200102, "Renamed it everywhere, thanks.",
                              "2026-09-12T11:30:00Z"),)),
        Card(9200003, "PRRT_answered_reopened",
             "an answer that came back after you had spoken, first in Answered wearing "
             "the reopened mark",
             "billing/header.py", 40, author=viewer, author_name="",
             replies=(_answer(9200110, "Which units?", "2026-09-12T10:00:00Z"),)),
        Card(9200004, "PRRT_waiting",
             "a thread you raised and answered last, waiting on the author to come back",
             "billing/api.py", 70, author=viewer, author_name="",
             replies=(_answer(9200104, "Materialised it once.", "2026-09-12T09:30:00Z"),)),
        Card(9200005, "PRRT_waiting_theirs",
             "a colleague's thread you answered on, waiting on the author",
             "billing/parser.py", 33, author=COLLEAGUE, author_name=COLLEAGUE_NAME,
             replies=(_answer(9200106, "Split the parser in two.", "2026-09-12T09:20:00Z"),)),
        Card(9200006, "PRRT_deferred_push",
             "a thread parked until the author pushes again, with the note you wrote "
             "for yourself",
             "billing/guard.py", 44, author=viewer, author_name="",
             replies=(_answer(9200108, "Will fix in the next push.",
                              "2026-09-12T08:30:00Z"),)),
        Card(9200007, "PRRT_resolved",
             "a thread you resolved on GitHub, settled for the life of the PR",
             "billing/constants.py", 12, author=viewer, author_name="",
             replies=(_answer(9200109, "Done in b41c0d2.", "2026-09-12T07:30:00Z"),)),
        Card(9200008, "PRRT_assumed_done",
             "a thread of yours the author fixed, which an agent read as settled for "
             "you to confirm",
             "billing/units.py", 22, author=viewer, author_name="",
             replies=(_answer(9200111, "Fixed in 3e1f0aa, thanks for spotting it.",
                              "2026-09-12T08:10:00Z"),)),
        Card(9200009, "PRRT_not_mine",
             "a colleague's thread an agent read as asking nothing of you",
             "billing/format.py", 57, author=COLLEAGUE, author_name=COLLEAGUE_NAME,
             replies=(_answer(9200112, "Good catch, will do.", "2026-09-12T08:20:00Z"),)),
        Card(9200010, "PRRT_not_yet_read",
             "a colleague's comment that just arrived, my move until an agent has read it",
             "billing/columns.py", 15, author=COLLEAGUE, author_name=COLLEAGUE_NAME),
        Card(9200011, "PRRT_confirmed",
             "a thread of yours an agent read as settled and you confirmed, Done with "
             "nothing posted to GitHub",
             "billing/units.py", 48, author=viewer, author_name="",
             replies=(_answer(9200113, "Rounded once, at the end.",
                              "2026-09-12T07:50:00Z"),)),
    )


def cards(reviewer: bool, viewer: str = "") -> tuple[Card, ...]:
    return reviewer_cards(viewer) if reviewer else AUTHOR_CARDS


def _module_text(path: str, lines: int) -> str:
    body = [f'"""{path}"""', ""]
    while len(body) < lines:
        at = len(body) + 1
        body.append(f"def step_{at:03d}(line_items):")
        body.append(f"    return [item for item in line_items if item.id != {at}]")
        body.append("")
    return "\n".join(body[:lines]) + "\n"


def _git(root: Path | str, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=preview",
         "-c", "user.email=preview@example.com", *args],
        check=True, capture_output=True, text=True).stdout


def _anchors(reviewer: bool) -> tuple[tuple[str, int], ...]:
    return tuple(sorted({(card.path, card.line) for card in cards(reviewer)}))


def _rewrite(root: Path, anchors: tuple[tuple[str, int], ...], text: str,
             offset: int = 0) -> None:
    for path, line in anchors:
        target = root / path
        lines = target.read_text().splitlines()
        lines[line - 1 + offset] = text
        target.write_text("\n".join(lines) + "\n")


def _origin(worktree: Path) -> Path:
    return worktree.with_name(f"{worktree.name}-origin.git")


def build_repo(root: Path, reviewer: bool = False) -> Repo:
    anchors = _anchors(reviewer)
    longest: dict[str, int] = {}
    for path, line in anchors:
        longest[path] = max(longest.get(path, 0), line)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", BASE_BRANCH)
    for path, last in longest.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_module_text(path, last + 6))
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "the commit the PR branched from")
    _git(root, "checkout", "-q", "-b", PR_BRANCH)
    _rewrite(root, anchors, "    return sorted(line_items)")
    _git(root, "commit", "-qam", "what the PR changed")
    _git(root.parent, "init", "-q", "--bare", str(_origin(root)))
    _git(root, "remote", "add", "origin", str(_origin(root)))
    _git(root, "push", "-q", "-u", "origin", PR_BRANCH)
    return Repo(str(root), BASE_BRANCH, _git(root, "rev-parse", "HEAD").strip())


STAND_IN = 'echo "The preview opens a shell where the manager opens g $1."; exec "${SHELL:-/bin/sh}" -l'


@dataclasses.dataclass
class PreviewPanel(FakeManagerPanel):
    sessions: TerminalSessions | None = None
    worktree: str = ""

    def open_terminal(self, keys: str) -> str | None:
        if self.sessions is None:
            return super().open_terminal(keys)
        self.sessions.start(self.worktree, ["sh", "-c", STAND_IN, "sh", keys])
        return None


@dataclasses.dataclass(frozen=True)
class Outside:
    github: FakeGitHub
    agent_runs: HeldVerdicts
    pr_processes: FakePrProcesses
    change_detection: ChangeDetection


class _Seeding:
    def __init__(self, conversation_managers: ConversationManagerFactory, outside: Outside, repo: Repo) -> None:
        self.conversations: ConversationManager = conversation_managers.of(PR)
        self.news = FakeNotifications()
        self.outside = outside
        self.repo = repo

    def _off_github(self, card: Card) -> None:
        record = self.outside.github.prs[PR]
        record.threads = [one for one in record.threads if one.key != card.key]

    def open(self, card: Card, *later: ThreadComment) -> None:
        self._off_github(card)
        self.hear(card.thread(*later))
        if not card.on_github:
            self._off_github(card)

    def hear(self, thread: Thread) -> None:
        self.outside.github.add_thread(PR, thread)
        state = self.outside.github.prs[PR].state
        polled = self.conversations.poll(state)
        if polled.activity is not None:
            self.conversations.absorb(polled.activity)
        polled.commit()
        self.outside.change_detection.advance(
            PR, Poll(state=state, polled_at=MOMENT, mentions=polled.mentions), set())

    def conversation(self, card: Card) -> Conversation:
        conversation = self.conversations.get(card.key)
        if conversation is None:
            raise LookupError(f"the preview has no thread {card.key}")
        return conversation

    def lose(self, card: Card) -> None:
        before = self.conversation(card)
        self._off_github(card)
        self.conversations.recheck(before)
        deadline = time.monotonic() + RECHECK_SECONDS
        while self.conversation(card) == before and time.monotonic() < deadline:
            time.sleep(0.01)

    def report(self, card: Card,
               reported: Callable[[EditableConversation], Conversation | Denied]) -> None:
        with self.conversations.editing(card.key) as conversation:
            reported(conversation)

    def placed(self, card: Card, verdict: str) -> None:
        self.outside.agent_runs.give(verdict, key=card.key)

    def ask(self, card: Card,
            decided: Callable[[EditableConversation], Conversation | Denied]) -> None:
        with self.conversations.editing(card.key) as conversation:
            asked = decided(conversation)
        if isinstance(asked, Denied):
            raise RuntimeError(f"the preview asked {card.key} for what it refuses: "
                               f"{asked.reason}")
        self.conversations.tick(self.news, on_hold=False)

    def run(self, *, stays: bool = False) -> None:
        self.outside.agent_runs.script(RunOutcome(finishes=not stays))
        self.conversations.tick(self.news, on_hold=False)

    def accept_a_ticket(self, card: Card, title: str, *, filing: bool = False) -> None:
        self.open(card)
        self.run()
        self.report(card, lambda conversation: conversation.not_a_fix(
            Classification.OUT_OF_SCOPE, "That reaches past this PR, so I've proposed a ticket.",
            ticket_project="PROJ", ticket_title=title,
            ticket_body=f"{card.gist}.\n\nRaised on the review of the invoice writer."))
        self.outside.agent_runs.script(RunOutcome(finishes=not filing))
        self.ask(card, lambda conversation: conversation.approve(
            reply="Agreed; it reaches past this PR, so I've filed a ticket for it.",
            ticket_project="PROJ", ticket_title=title,
            ticket_body=f"{card.gist}.\n\nRaised on the review of the invoice writer."))

    def filing_ends(self, card: Card,
                    reported: Callable[[EditableConversation], Conversation | Denied]) -> None:
        self.report(card, reported)
        self.conversations.tick(self.news, on_hold=False)
        self.conversations.tick(self.news, on_hold=False)

    def _worktree_of(self, card: Card) -> str:
        for started in reversed(self.outside.agent_runs.started):
            match started.work:
                case FixingThread(fix=fix) | RebasingFix(fix=fix) | Reworking(fix=fix):
                    if fix.key == card.key:
                        return fix.worktree
        raise LookupError(f"{card.key} has no workspace to commit in")

    def commit(self, card: Card) -> str:
        checkout = self._worktree_of(card)
        _rewrite(Path(checkout), ((card.path, card.line),),
                 "    return sorted(line_items, key=str)", offset=1)
        _git(checkout, "commit", "-qam", f"what the agent proposes for {card.key}")
        return _git(checkout, "rev-parse", "HEAD").strip()

    def propose(self, card: Card, steps: tuple[str, ...] = (), *, tests: str | None = None,
                tests_note: str | None = None, agent_note: str | None = None,
                summary: str | None = None, confidence: str | None = None,
                confidence_note: str | None = None) -> None:
        self.open(card)
        self.run()
        if steps:
            self.report(card, lambda conversation: conversation.plan(
                [(step, card.path) for step in steps]))
            self.report(card, lambda conversation: conversation.step_done(
                range(1, len(steps) + 1)))
        sha = self.commit(card)
        self.report(card, lambda conversation: conversation.ready(
            sha, tests=tests, tests_note=tests_note, note=agent_note, summary=summary,
            confidence=confidence, confidence_note=confidence_note))

    def push_elsewhere(self) -> None:
        worktree = Path(self.repo.worktree)
        elsewhere = worktree.with_name(f"{worktree.name}-elsewhere")
        _git(worktree.parent, "clone", "-q", "-b", PR_BRANCH, str(_origin(worktree)),
             str(elsewhere))
        (elsewhere / "PUSHED_ELSEWHERE").write_text("a teammate's push\n")
        _git(elsewhere, "add", "-A")
        _git(elsewhere, "commit", "-qm", "a teammate's push")
        _git(elsewhere, "push", "-q")

    def move_the_pr(self, card: Card) -> None:
        worktree = Path(self.repo.worktree)
        _rewrite(worktree, ((card.path, card.line),), "    return list(line_items)",
                 offset=1)
        _git(worktree, "commit", "-qam", "a change the fix now conflicts with")


def _author_board(seeding: _Seeding) -> None:
    seeding.propose(READY, ("Raise instead of continuing past the missing tax rate",
                            "Test: the export raises on a missing tax rate",
                            "Say so in the module docstring"),
                    summary="Raise MissingTaxRate in _collect() instead of "
                            "skipping, and cover it with a test.",
                    confidence="medium",
                    confidence_note="Callers in cli/billing.py may rely on the silent "
                                    "skip. Not verified.",
                    tests="unverified", agent_note="Renamed it and moved the guard up.")
    seeding.open(TICKET_PROPOSED)
    seeding.run()
    seeding.report(TICKET_PROPOSED, lambda conversation: conversation.not_a_fix(
        Classification.OUT_OF_SCOPE,
        "Agreed, and it reaches past this PR, so I've proposed a ticket for it.",
        ticket_project="PROJ", ticket_title="Share one tax-rate cache across exports",
        ticket_body="Each export builds its own cache of tax rates, so two exports "
                    "of the same month look every rate up twice.\n\nRaised on the "
                    "review of the invoice writer."))
    seeding.open(REPLY_PROPOSED)
    seeding.run()
    seeding.report(REPLY_PROPOSED, lambda conversation: conversation.not_a_fix(
        Classification.QUESTION,
        "Each export prices one customer from start to finish, so the reader "
        "never needs two tax tables at once.\n\nHolding one keeps memory flat on the "
        "large accounts; the cache is dropped when the export ends."))
    seeding.open(DECLINED)
    seeding.run()
    seeding.report(DECLINED, lambda conversation: conversation.not_a_fix(
        Classification.NEEDS_HUMAN, "only the author can choose between the two exports"))
    seeding.open(ASSUMED_DONE)
    seeding.run()
    seeding.report(ASSUMED_DONE, lambda conversation: conversation.not_a_fix(
        Classification.ACKNOWLEDGEMENT, "thanks the author, asks for nothing"))
    seeding.open(FAILED)
    for _ in range(3):
        seeding.run()
        seeding.report(FAILED, lambda conversation: conversation.fail("tests failed twice"))
    seeding.propose(REMOVED)
    seeding.lose(REMOVED)
    seeding.open(WORKING)
    seeding.run(stays=True)
    seeding.report(WORKING, lambda conversation: conversation.plan((
        ("One cache per currency", "billing/reader.py"),
        ("Drop the global cache", "billing/reader.py"),
        ("A test two workers can race", None))))
    seeding.report(WORKING, lambda conversation: conversation.step_done((1,)))
    seeding.propose(IN_SESSION)
    seeding.ask(IN_SESSION, lambda conversation: conversation.start_session())
    seeding.propose(WAITING, summary="Take an iterable and materialise it once.",
                    confidence="low", tests="failed",
                    tests_note="the suite needs a payment sandbox this box has not got")
    seeding.ask(WAITING, lambda conversation: conversation.reply(
        "Is the sandbox the reason it failed?"))
    seeding.propose(DEFERRED)
    seeding.ask(DEFERRED, lambda conversation: conversation.place(
        ConversationState.DEFERRED, until="pr:12",
        note="Revisit once the export rewrite PR lands."))
    seeding.propose(REJECTED)
    seeding.ask(REJECTED, lambda conversation: conversation.reject())
    seeding.propose(RESOLVED)
    seeding.ask(RESOLVED, lambda conversation: conversation.resolve(
        reply="Fixed in the last push."))
    seeding.propose(LANDED, ("Spell the units out in the header",),
                    summary="Spell out net and gross in the invoice header row.", tests="passed")
    seeding.ask(LANDED, lambda conversation: conversation.approve(
        reply="Good catch — spelled them out."))
    seeding.propose(REPLY_REFUSED)
    seeding.ask(REPLY_REFUSED, lambda conversation: conversation.approve(
        reply="Renamed, thanks."))
    seeding.propose(REBASING)
    seeding.move_the_pr(REBASING)
    seeding.ask(REBASING, lambda conversation: conversation.approve(
        reply="Rebase it onto the new head."))
    seeding.run(stays=True)
    seeding.push_elsewhere()
    seeding.propose(PUSH_REJECTED)
    seeding.ask(PUSH_REJECTED, lambda conversation: conversation.approve(
        reply="Good catch — dropped it."))
    seeding.accept_a_ticket(TICKET_FILING, "Read units from one table in the reader and writer",
                            filing=True)
    seeding.accept_a_ticket(TICKET_FILED, "One helper for every exporter's header")
    seeding.filing_ends(TICKET_FILED, lambda conversation: conversation.not_a_fix(
        Classification.OUT_OF_SCOPE, "", filed_key="PROJ-22",
        filed_url="https://example.atlassian.net/browse/PROJ-22"))
    seeding.accept_a_ticket(TICKET_UNFILED, "Report export progress from the CLI")
    seeding.filing_ends(TICKET_UNFILED, lambda conversation: conversation.fail(
        "Jira refused the issue: the project PROJ has no issue type Task"))
    seeding.propose(REWORKING)
    seeding.propose(REOPENED)
    seeding.ask(REOPENED, lambda conversation: conversation.reply(
        "Does this cover the reader too?"))
    seeding.open(REOPENED, _said(9100003, "anna", "Anna Example",
                                 "Not yet — the reader skips it the same way.",
                                 "2026-09-12T10:30:00Z"))
    seeding.ask(REWORKING, lambda conversation: conversation.rework(
        note="Raise a typed error rather than the bare ValueError.",
        pointed=((REWORKING.path, REWORKING.line, "    return sorted(line_items, key=str)"),),
        include=("anna",)))
    seeding.open(QUEUED)


def _reviewer_board(seeding: _Seeding, viewer: str) -> None:
    (answered, theirs, reopened, waiting, waiting_theirs, deferred, resolved, assumed_done,
     not_mine, not_yet_read, confirmed) = reviewer_cards(viewer)
    for card in (answered, theirs, reopened, waiting, waiting_theirs, deferred, resolved):
        seeding.open(card)
        seeding.placed(card, "my-move")
    seeding.ask(reopened, lambda conversation: conversation.reply(
        "Spell them out in the header too."))
    seeding.open(reopened, _answer(9200103, "Spelled the units out in full.",
                                   "2026-09-12T10:30:00Z"))
    seeding.placed(reopened, "my-move")
    seeding.ask(waiting, lambda conversation: conversation.reply(
        "That is not what I asked about."))
    seeding.placed(waiting, "their-move")
    seeding.ask(waiting_theirs, lambda conversation: conversation.reply(
        "The second half still parses twice."))
    seeding.placed(waiting_theirs, "their-move")
    seeding.ask(deferred, lambda conversation: conversation.place(
        ConversationState.DEFERRED, until="push",
        note="Look again once the guard is in."))
    seeding.ask(resolved, lambda conversation: conversation.resolve(
        reply="Confirmed, thanks.", resolve=True))
    seeding.open(assumed_done)
    seeding.placed(assumed_done, "assumed-done")
    seeding.open(not_mine)
    seeding.placed(not_mine, "not-mine")
    seeding.open(not_yet_read)
    seeding.open(confirmed)
    seeding.placed(confirmed, "assumed-done")
    seeding.ask(confirmed, lambda conversation: conversation.place(ConversationState.DONE))
    seeding.hear(Thread(key="IC_mention", kind=CommentKind.ISSUE, comments=(
        _said(9200201, COLLEAGUE, COLLEAGUE_NAME,
              f"@{viewer} does the export still need the guard once the reader "
              "checks the units? A mention, answered with one Reply and resolve.",
              "2026-09-12T11:45:00Z"),)))


def _record_the_pr(outside: Outside, repo: Repo, viewer: str, reviewer: bool) -> None:
    head = _git(repo.worktree, "rev-parse", "HEAD").strip()
    state = PullRequestState(title=PR_TITLE, url=f"https://github.com/{PR.repo}/pull/{PR.number}",
                             branch=PR_BRANCH, base_branch=repo.base_branch,
                             head_sha=head,
                             author=PR_AUTHOR if reviewer else viewer,
                             body=(f"Splits the invoice writer in two.\n\ncc @{viewer}, the export "
                                   "side is yours." if reviewer else ""),
                             pending_reviewers=(viewer,) if reviewer else ())
    outside.github.prs[PR].state = state
    outside.change_detection.advance(PR, Poll(state=state, polled_at=MOMENT), set())


def seed(conversation_managers: ConversationManagerFactory, outside: Outside, viewer: str, repo: Repo,
         reviewer: bool = False) -> None:
    outside.github.add_pr(PR)
    _record_the_pr(outside, repo, viewer, reviewer)
    outside.pr_processes.open(PR, Path(repo.worktree))
    outside.agent_runs.ran(PR, "ci-failed", 48.0, LAST_RUN_ENDED)
    seeding = _Seeding(conversation_managers, outside, repo)
    if reviewer:
        _reviewer_board(seeding, viewer)
    else:
        _author_board(seeding)
    _record_the_pr(outside, repo, viewer, reviewer)


def worktree_in(directory: Path) -> Path:
    return directory / "worktree"


def serve(directory: Path, viewer: str, outside: Outside, port: int = 0,
          reviewer: bool = False, *, conversation_managers: ConversationManagerFactory,
          dashboards: Dashboards, board_api: BoardApi, sessions: TerminalSessions) -> str:
    repo = build_repo(worktree_in(directory), reviewer)
    seed(conversation_managers, outside, viewer, repo, reviewer)
    return board_api.start(PR, port=port, manager=manager_panel(
        running(dashboards.dashboard(PR)), sessions=sessions, worktree=repo.worktree))


def running(dashboard: Dashboard) -> Dashboard:
    return dataclasses.replace(dashboard, working_on="new-comments", elapsed_seconds=312.0,
                               silent_seconds=6.0)


def manager_panel(dashboard: Dashboard, *, sessions: TerminalSessions | None = None,
                  worktree: str = "") -> PreviewPanel:
    return PreviewPanel(
        sessions=sessions, worktree=worktree, now=dashboard,
        changes_text=("# What changed\n\n- Renamed `write_invoice` to `write_invoice_file`.\n"
                      "- Split the header writer out of the body writer.\n"),
        output=[("Reading src/writer.py", False), ("Running the tests", False),
                ("", True), ("All 212 tests pass.", False)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="serve a board of made-up conversations, one per group")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--agents-disabled", action="store_true")
    parser.add_argument("--reviewer", action="store_true")
    args = parser.parse_args(argv)
    directory = Path(tempfile.mkdtemp(prefix="review-board-preview-"))
    pr_processes = FakePrProcesses()
    github = FakeGitHub()
    agent_runs = HeldVerdicts(pr_processes)
    desktop = FakeDesktop()

    def container(agents_enabled: bool) -> tuple[dishka.Container, str]:
        return preview_container(os.environ, Path.home(), data_dir=directory, repo=PR.repo,
                                 local_path=worktree_in(directory), github=github,
                                 desktop=desktop, agent_runs=agent_runs,
                                 pr_processes=pr_processes, agents_enabled=agents_enabled)

    seeding, viewer = container(True)
    serving = container(False)[0] if args.agents_disabled else seeding
    github.account = viewer
    outside = Outside(github, agent_runs, pr_processes, seeding.get(ChangeDetection))
    board_api = serving.get(BoardApi)
    url = serve(directory, viewer, outside, port=args.port,
                reviewer=args.reviewer,
                conversation_managers=seeding.get(ConversationManagerFactory),
                dashboards=seeding.get(Dashboards), board_api=board_api,
                sessions=serving.get(TerminalSessions))
    print(url, flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        board_api.stop()
    return 0

