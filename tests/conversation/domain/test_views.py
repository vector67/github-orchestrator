from github_orchestrator.conversation import Denied, OperationKind
from github_orchestrator.domain import Sha
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.conversation.support import (
    WORKTREE,
    at,
    drain,
    first_poll,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    world,
)

KEY = "PRRT_one"


class Thread:
    def __init__(self, settings):
        github = FakeGitHub()
        self.here = world(settings, github=github, working_copies=FakeWorkingCopies(github),
                          clock=at("2026-09-16T11:00:00Z"))
        self.working_copies = self.here.working_copies
        repo_at(self.working_copies, WORKTREE, {"f.py": "old\n"})
        self.threads = self.here.threads()
        first_poll(self.here.github, self.threads)
        on_github(self.here.github, KEY, said(1, "rename this"), path="f.py")
        hear(self.threads)

    def stored(self):
        return self.threads.get(KEY)

    def propose(self):
        propose(self.here, self.threads, KEY, {"f.py": "new\n"})
        return self.stored()

    def ask(self, verb, **asked):
        with self.threads.editing(KEY) as editable:
            outcome = getattr(editable, verb)(**asked)
        assert not isinstance(outcome, Denied), outcome
        drain(self.threads)
        return self.stored()

    def reworking(self):
        self.propose()
        with self.threads.editing(KEY) as editable:
            editable.rework(note="the other way", pointed=[("f.py", 1, "old")])
        start_run(self.here, self.threads, finishes=False)
        with self.threads.editing(KEY) as editable:
            editable.plan([("rename it", "f.py"), ("update the callers", None)])
        with self.threads.editing(KEY) as editable:
            editable.step_done([1])
        return self.stored()


def _view(conversation, kind):
    [view] = [view for view in conversation.views if view.operation.kind == kind]
    return view


def test_every_operation_has_one_view_in_the_order_it_was_asked(settings):
    thread = Thread(settings)

    conversation = thread.reworking()

    assert [view.operation.id for view in conversation.views] == [
        operation.id for operation in conversation.operations]


def test_only_the_run_the_thread_is_on_carries_its_plan_and_brief(settings):
    thread = Thread(settings)

    conversation = thread.reworking()

    first = _view(conversation, OperationKind.FIRST)
    rework = _view(conversation, OperationKind.REWORK)
    assert not first.current
    assert (first.plan, first.brief, first.steps_done, first.steps_total) == ((), None, None, None)
    assert rework.current
    assert [step.text for step in rework.plan] == ["rename it", "update the callers"]
    assert (rework.steps_done, rework.steps_total) == (1, 2)
    assert rework.brief.note == "the other way"


def test_a_run_still_going_has_left_no_proposal(settings):
    thread = Thread(settings)

    conversation = thread.reworking()

    assert conversation.proposal is None
    assert _view(conversation, OperationKind.FIRST).proposal is None
    assert _view(conversation, OperationKind.REWORK).proposal is None


def test_the_proposal_is_named_after_the_run_that_left_it(settings):
    thread = Thread(settings)

    conversation = thread.propose()

    run = _view(conversation, OperationKind.FIRST)
    assert conversation.proposal.id == f"{KEY}.1.proposal"
    assert conversation.proposal.operation == f"{KEY}.1"
    assert run.proposal == conversation.proposal.id
    assert conversation.proposal.commits is not None


def test_only_the_latest_approve_carries_how_far_the_landing_got(settings):
    thread = Thread(settings)
    thread.propose()
    thread.working_copies.refuse_pushes("fatal: the remote hung up")
    thread.ask("approve", reply="first words")
    thread.working_copies.refuse_pushes(None)

    conversation = thread.ask("approve", reply="renamed it")

    earlier, latest = [view for view in conversation.views
                       if view.operation.kind == OperationKind.APPROVE]
    assert not earlier.current
    assert (earlier.landing.picked, earlier.landing.pushed, earlier.landing.landed_sha,
            earlier.proposal, earlier.posted_comment) == (False, False, None, None, None)
    assert earlier.text == "first words"
    assert latest.current
    assert (latest.landing.picked, latest.landing.pushed) == (True, True)
    assert latest.landing.landed_sha == Sha(thread.working_copies.branches["main"])
    assert latest.proposal == f"{KEY}.1.proposal"
    assert latest.posted_comment == conversation.approved_reply_id
    assert latest.posted_comment in conversation.posted_by_board

