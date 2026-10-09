from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from github_orchestrator.change_detection import Poll
from github_orchestrator.conversation import (
    Classification,
    Conversation,
    ConversationState,
    Denied,
)
from github_orchestrator.github import PullRequestState, ThreadComment
from github_orchestrator.github.fake import FakeGitHub, GhError
from github_orchestrator.settings.fake import fake_settings
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    Moment,
    World,
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

KEY = "PRRT_one"
ROOT = 101
NOW = "2026-09-01T10:05:00Z"
STAMPED = "2026-09-01T10:06:00Z"
OTHER = "someone-else"


class SaysNoWhenAsked(FakeGitHub):
    refusing = False

    def reply_to_thread(self, key, body):
        if self.refusing:
            raise GhError("HTTP 502")
        return super().reply_to_thread(key, body)


@dataclass
class Bench:
    here: World
    github: SaysNoWhenAsked
    clock: Moment
    threads: Any

    def conversation(self) -> Conversation:
        found: Conversation = self.threads.get(KEY)
        return found

    def standing(self) -> ConversationState:
        return self.conversation().standing

    def says(self, *comments: ThreadComment) -> None:
        record = self.github.prs[THE_PR]
        record.threads = [replace(thread, comments=(*thread.comments, *comments))
                          if thread.key == KEY else thread for thread in record.threads]
        hear(self.threads)

    def resolved_on_github(self, is_resolved: bool) -> None:
        record = self.github.prs[THE_PR]
        record.threads = [replace(thread, is_resolved=is_resolved)
                          if thread.key == KEY else thread for thread in record.threads]
        hear(self.threads)

    def reported(self, verb) -> None:
        with self.threads.editing(KEY) as conversation:
            verb(conversation)

    def asked(self, verb) -> None:
        with self.threads.editing(KEY) as conversation:
            asked = verb(conversation)
        assert not isinstance(asked, Denied), asked
        drain(self.threads)


def _bench(settings, *, is_author: bool = True) -> Bench:
    github = SaysNoWhenAsked()
    clock = Moment(NOW)
    here = world(settings, github=github, clock=clock)
    repo_at(here.working_copies, WORKTREE, {"helper.py": "old"})
    head = here.working_copies.commit(WORKTREE, {"g": "a line\n"}, "add g")
    author = github.account if is_author else f"not-{github.account}"
    github.add_pr(THE_PR, PullRequestState(author=author, base_branch="main", head_sha=head))
    here.change_detection.advance(THE_PR, Poll(state=github.pr_state(THE_PR), polled_at=NOW),
                                  set())
    here.pr_processes.open(THE_PR, Path(WORKTREE))
    return Bench(here, github, clock, here.conversation_managers.of(THE_PR))


@pytest.fixture
def bench(tmp_path):
    return _bench(fake_settings(tmp_path, agents_enabled=True))


@pytest.fixture
def reviewing(tmp_path):
    return _bench(fake_settings(tmp_path, agents_enabled=True), is_author=False)


def _queued(b: Bench) -> None:
    on_github(b.github, KEY, said(ROOT, "rename this"))
    hear(b.threads)


def _working(b: Bench) -> None:
    _queued(b)
    start_run(b.here, b.threads, finishes=False)


def _proposed(b: Bench) -> None:
    _queued(b)
    propose(b.here, b.threads, KEY, {"helper.py": "renamed"})


def _declined(b: Bench) -> None:
    _queued(b)
    start_run(b.here, b.threads)
    with b.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.RISKY, "no")


def _fail_every_attempt(b: Bench) -> None:
    for _ in range(b.conversation().run_holder.attempts_allowed):
        start_run(b.here, b.threads)
        with b.threads.editing(KEY) as editable:
            editable.fail("boom")


def _failed(b: Bench) -> None:
    _queued(b)
    _fail_every_attempt(b)


def _landed(b: Bench) -> None:
    _proposed(b)
    b.asked(lambda conversation: conversation.approve())


def _resolved(b: Bench) -> None:
    _proposed(b)
    b.asked(lambda conversation: conversation.resolve())


def _ready(b: Bench, sha: str | None = None) -> Any:
    with b.threads.editing(KEY) as editable:
        return editable.ready(sha or commit_fix(b.here, KEY, {"helper.py": "again"}),
                              tests="passed")


def _answered(b: Bench) -> None:
    on_github(b.github, KEY, said(ROOT, "rename this", author=b.github.account),
              said(ROOT + 1, "have a look", author=OTHER))
    hear(b.threads)


def _mine_alone(b: Bench) -> None:
    on_github(b.github, KEY, said(ROOT, "rename this", author=b.github.account))
    hear(b.threads)


ALLOWED = [
    ("working -> failed", _queued, _fail_every_attempt, lambda c: c.fix.has_failed),
    ("ready -> resolved", _proposed, lambda b: b.asked(lambda conversation: conversation.resolve()),
     lambda c: c.standing is ConversationState.DONE and c.fix.is_proposed),
    ("skipped -> resolved", _declined, lambda b: b.asked(lambda conversation: conversation.resolve()),
     lambda c: c.standing is ConversationState.DONE and c.fix.is_declined),
    ("failed -> resolved", _failed, lambda b: b.asked(lambda conversation: conversation.resolve()),
     lambda c: c.standing is ConversationState.DONE and c.fix.has_failed),
    ("ready -> ready", _proposed, _ready, lambda c: c.fix.is_proposed),
    ("answered -> answered, not yet read, when you speak", _answered,
     lambda b: b.says(said(ROOT + 9, "and this too", author=b.github.account)),
     lambda c: c.standing is ConversationState.READY and c.unread),
    ("answered -> done", _answered, lambda b: b.resolved_on_github(True),
     lambda c: c.standing is ConversationState.DONE),
    ("done -> answered", lambda b: (_answered(b), b.resolved_on_github(True)),
     lambda b: b.resolved_on_github(False), lambda c: c.standing is ConversationState.READY),
    ("done -> answered, not yet read", lambda b: (_mine_alone(b), b.resolved_on_github(True)),
     lambda b: b.resolved_on_github(False),
     lambda c: c.standing is ConversationState.READY and c.unread),
]

REVIEWING = {"answered -> answered, not yet read, when you speak", "answered -> done",
             "done -> answered", "done -> answered, not yet read"}


@pytest.mark.parametrize("name,before,act,landed", ALLOWED,
                         ids=[row[0] for row in ALLOWED])
def test_a_transition_the_board_has_always_allowed(tmp_path, name, before, act, landed):
    b = _bench(fake_settings(tmp_path, agents_enabled=True), is_author=name not in REVIEWING)
    before(b)

    outcome = act(b)

    assert not isinstance(outcome, Denied), outcome
    assert landed(b.conversation())


DISALLOWED = [
    ("queued -> ready", _queued, lambda conversation: conversation.ready("abc1234", tests="passed")),
    ("queued -> failed", _queued, lambda conversation: conversation.fail("boom")),
    ("ready -> failed", _proposed, lambda conversation: conversation.fail("boom")),
    ("skipped -> ready", _declined,
     lambda conversation: conversation.ready("abc1234", tests="passed")),
    ("approved -> ready", _landed,
     lambda conversation: conversation.ready("abc1234", tests="passed")),
    ("resolved -> ready", _resolved,
     lambda conversation: conversation.ready("abc1234", tests="passed")),
]


@pytest.mark.parametrize("before,verb", [row[1:] for row in DISALLOWED],
                         ids=[row[0] for row in DISALLOWED])
def test_a_transition_the_board_has_always_refused(bench, before, verb):
    before(bench)
    was = bench.conversation()
    started = len(bench.here.agent_runs.started)
    sessions = len(bench.here.agent_runs.sessions)

    with bench.threads.editing(KEY) as conversation:
        outcome = verb(conversation)

    assert isinstance(outcome, Denied)
    now = bench.conversation()
    assert now.standing is was.standing
    assert now.fix == was.fix
    assert len(bench.here.agent_runs.started) == started
    assert len(bench.here.agent_runs.sessions) == sessions


def test_a_reviewers_thread_never_takes_a_run(reviewing):
    _answered(reviewing)

    drain(reviewing.threads)

    assert reviewing.here.agent_runs.started == []
    assert reviewing.standing() is ConversationState.READY


def test_a_command_that_moves_the_thread_stamps_the_moment_it_moved(bench):
    _queued(bench)
    bench.clock.iso = STAMPED

    start_run(bench.here, bench.threads, finishes=False)

    assert bench.conversation().state_changed_at == STAMPED


def test_a_command_that_leaves_the_thread_where_it_was_stamps_nothing(bench):
    _working(bench)
    moved_at = bench.conversation().state_changed_at
    bench.clock.iso = STAMPED

    with bench.threads.editing(KEY) as editable:
        editable.plan([("rename the helper", "helper.py")])

    assert bench.conversation().state_changed_at == moved_at


def test_a_refusal_stamps_no_move_because_none_happened(bench):
    _queued(bench)
    moved_at = bench.conversation().state_changed_at
    bench.clock.iso = STAMPED

    with bench.threads.editing(KEY) as editable:
        outcome = editable.approve()

    assert isinstance(outcome, Denied)
    assert bench.conversation().state_changed_at == moved_at
