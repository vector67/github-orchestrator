from dataclasses import replace

import pytest

from github_orchestrator.agent_runs.fake import Outcome as RunOutcome
from github_orchestrator.conversation import (
    Classification,
    ConversationState,
    Denied,
    ErrorCode,
    OperationKind,
    OperationState,
)
from github_orchestrator.domain import Sha
from github_orchestrator.github import CommentKind, ThreadComment
from github_orchestrator.github.fake import FakeGitHub, GhError
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.conversation.support import (
    PR,
    REPO,
    WORKTREE,
    at,
    commit_fix,
    drain,
    first_poll,
    hear,
    lost,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    without_runs,
    world,
)

THE_PR = a_pr(PR, REPO)

NOW = "2026-09-16T11:00:00Z"
KEY = "PRRT_one"
BOT = "octocat"


class GitHub(FakeGitHub):
    refusing = False

    def reply_to_thread(self, key: str, body: str) -> ThreadComment | None:
        if self.refusing:
            raise GhError("HTTP 403")
        return super().reply_to_thread(key, body)


class Landing:
    def __init__(self, settings, *, key=KEY, kind=CommentKind.REVIEW, replies=(),
                 author="reviewer"):
        self.key = key
        self.github = GitHub()
        self.here = world(settings, github=self.github,
                          working_copies=FakeWorkingCopies(self.github), clock=at(NOW))
        self.working_copies = self.here.working_copies
        repo_at(self.working_copies, WORKTREE, {"f.py": "old\n"})
        self.threads = self.here.threads()
        first_poll(self.github, self.threads)
        on_github(self.github, key, said(1, "rename this", author=author), *replies, kind=kind,
                  path="f.py")
        hear(self.threads)

    def stored(self):
        return self.threads.get(self.key)

    def propose(self, files=None, **ready):
        propose(self.here, self.threads, self.key, files or {"f.py": "new\n"}, **ready)
        return self.stored()

    def approve(self, reply="", **approving):
        with self.threads.editing(self.key) as editable:
            asked = editable.approve(reply=reply, **approving)
        if not isinstance(asked, Denied):
            drain(self.threads)
        return asked

    def pr_tree(self):
        return self.working_copies.commits[self.working_copies.branches["main"]].tree

    def answers(self):
        thread = self.github.thread(self.key)
        return [] if thread is None else [
            comment.body for comment in thread.comments if comment.author == BOT]

    def workspace_dropped(self):
        return not self.working_copies.holds_thread(THE_PR, self.key)

    def conflicting(self):
        return Sha(self.working_copies.commit(WORKTREE, {"f.py": "theirs\n"}, "someone else"))

    def rebasing(self, *, finishes=False):
        self.propose()
        head = self.conflicting()
        with self.threads.editing(self.key) as editable:
            editable.approve()
        self.here.agent_runs.script(RunOutcome(finishes=finishes))
        drain(self.threads)
        assert self.stored().fix.run.kind is OperationKind.REBASE
        return head

    def rebased(self, head, **ready):
        checkout = self.working_copies.thread_checkout(THE_PR, self.key)
        self.working_copies.branches[self.working_copies.branch_at(checkout)] = str(head)
        sha = commit_fix(self.here, self.key, {"f.py": "new\n"})
        with self.threads.editing(self.key) as editable:
            reported = editable.ready(sha, **ready)
        assert not isinstance(reported, Denied), reported
        drain(self.threads)
        return self.stored()

    def without_runs(self):
        here = self.here
        self.threads = world(without_runs(here.settings), github=here.github,
                             working_copies=here.working_copies,
                             agent_runs=here.agent_runs, thread_records=here.thread_records,
                             clock=here.clock, pr_processes=here.pr_processes).threads()

    def root_deleted(self):
        self.github.delete_comment(THE_PR, self.github.thread(self.key).kind, 1)
        lost(self.threads, self.key)
        assert self.stored().comment_deleted


def _approval(landing):
    return landing.stored().latest_approval


def test_a_second_approve_while_the_first_waits_for_the_drain_is_refused(settings):
    landing = Landing(settings)
    landing.propose()
    with landing.threads.editing(KEY) as editable:
        editable.approve()

    with landing.threads.editing(KEY) as editable:
        outcome = editable.approve()

    assert isinstance(outcome, Denied)
    assert outcome.code == ErrorCode.OPERATION_OUTSTANDING


def _running(landing):
    start_run(landing.here, landing.threads, finishes=False)


NOT_PROPOSED = {
    "running": _running,
}


@pytest.mark.parametrize("state", sorted(NOT_PROPOSED))
def test_only_a_proposed_fix_is_landed(settings, state):
    landing = Landing(settings)
    NOT_PROPOSED[state](landing)

    assert isinstance(landing.approve(), Denied)
    assert landing.pr_tree()["f.py"] == "old\n"


def test_a_conversation_github_has_lost_can_still_land_its_fix(settings):
    landing = Landing(settings)
    landing.propose()
    landing.root_deleted()
    assert landing.stored().is_removed

    outcome = landing.approve()

    assert not isinstance(outcome, Denied)
    assert landing.pr_tree()["f.py"] == "new\n"


def test_a_picked_fix_is_landing_with_the_commits_either_side_of_it(settings):
    landing = Landing(settings)
    head = landing.rebasing()
    landing.working_copies.refuse_pushes("fatal: the remote hung up")

    landing.rebased(head, tests="passed")

    fix = landing.stored().fix
    assert fix.picked and not fix.pushed
    assert fix.commits == (head, Sha(landing.working_copies.branches["main"]))
    assert fix.reason is None
    assert fix.decision_error is None
    assert fix.run.kind is OperationKind.FIRST, "the rebase it was cut for is over"


def test_a_pick_the_git_adapter_refused_hands_the_card_back(settings):
    landing = Landing(settings)
    landing.propose()
    commit_fix(landing.here, KEY, {"f.py": "newer\n"}, message="changed after review")

    outcome = landing.approve()

    assert not isinstance(outcome, Denied), (
        "git saying no settles the approve; it refuses no request")
    fix = landing.stored().fix
    assert fix.is_proposed
    assert fix.reason is not None
    assert fix.reason.startswith("the fix was changed after the board reviewed it")
    assert landing.pr_tree()["f.py"] == "old\n"


def test_a_conflicting_pick_queues_a_rebase_onto_the_head_and_keeps_the_approve(settings):
    landing = Landing(settings)
    landing.propose()
    landing.without_runs()
    head = landing.conflicting()

    landing.approve()

    queued = landing.stored()
    assert _approval(landing).state is OperationState.REQUEUED, "the approve waits for the rebase"
    fix = queued.fix
    assert queued.standing is ConversationState.LANDING
    assert (fix.run.kind, fix.run.onto, fix.run.conflict) == (
        OperationKind.REBASE, head, "CONFLICT (content): Merge conflict in f.py")
    assert fix.base_sha == head
    assert queued.run_holder.attempts == 0
    assert fix.commits is None
    assert fix.tests is None and fix.tests_note is None
    assert fix.agent_note is None and fix.reason is None
    assert fix.decision_error is None


def test_a_rebase_that_reports_a_fix_still_on_the_old_base_is_refused(settings):
    landing = Landing(settings)
    head = landing.rebasing()
    sha = commit_fix(landing.here, KEY, {"f.py": "still mine\n"})

    with landing.threads.editing(KEY) as editable:
        reported = editable.ready(sha, tests="passed")

    assert isinstance(reported, Denied)
    assert f"rebase your commit onto {head}" in reported.reason
    assert landing.stored().fix.run.kind is OperationKind.REBASE


def test_a_conflict_against_a_head_that_moved_since_the_rebase_queues_another(settings):
    landing = Landing(settings)
    first = landing.rebasing()
    moved = Sha(landing.working_copies.commit(WORKTREE, {"f.py": "theirs again\n"}, "and again"))
    landing.here.agent_runs.script(RunOutcome(finishes=False))

    landing.rebased(first, tests="passed")

    queued = landing.stored()
    assert _approval(landing).state is OperationState.REQUEUED, "the approve waits for the new rebase"
    assert (queued.fix.run.kind, queued.fix.run.onto, queued.fix.run.conflict) == (
        OperationKind.REBASE, moved, "CONFLICT (content): Merge conflict in f.py")
    assert queued.fix.base_sha == moved


def test_a_conflict_hands_the_card_back_when_no_rebase_may_be_queued(settings):
    landing = Landing(settings)
    proposed = landing.propose()
    landing.conflicting()
    unable = landing.here.threads(agents_enabled=False)

    with unable.editing(KEY) as editable:
        editable.approve()
    drain(unable)

    handed_back = unable.get(KEY)
    assert handed_back.fix.is_proposed
    assert handed_back.fix.reason == (
        "CONFLICT (content): Merge conflict in f.py; send back for rework and "
        "rebase the thread there"
    )
    assert handed_back.fix.run == proposed.fix.run, (
        "no rebase was queued, so nothing about the last one has changed")


def test_a_conflict_on_a_conversation_github_has_lost_queues_no_rebase(settings):
    landing = Landing(settings)
    proposed = landing.propose()
    landing.root_deleted()
    landing.conflicting()

    landing.approve()

    handed_back = landing.stored()
    assert handed_back.fix.is_proposed
    assert handed_back.fix.run == proposed.fix.run


def _push_refused(landing, reply=""):
    landing.propose()
    landing.working_copies.refuse_pushes("fatal: the remote hung up")
    landing.approve(reply)
    landing.working_copies.refuse_pushes(None)
    return landing.stored()


def test_a_push_that_landed_clears_the_error_it_used_to_carry(settings):
    landing = Landing(settings)
    refused = _push_refused(landing)
    assert refused.fix.push_error
    picked = landing.working_copies.branches["main"]

    landing.approve("renamed it")

    fix = landing.stored().fix
    assert fix.pushed
    assert fix.push_error is None
    assert landing.working_copies.branches["main"] == picked, (
        "the fix was not picked a second time")
    assert Sha(landing.working_copies.origin["main"]) == fix.commits[1]


def test_a_failed_push_keeps_the_commit_local_and_says_why(settings):
    landing = Landing(settings)

    refused = _push_refused(landing)

    fix = refused.fix
    assert fix.push_error == "fatal: the remote hung up"
    assert fix.picked and not fix.pushed
    assert Sha(landing.working_copies.origin["main"]) != fix.commits[1]
    assert refused.decidable_at == NOW, (
        "a failed push is yours to decide from the moment it failed")


def _with_a_reply(settings):
    return Landing(settings, replies=(said(2, "and the test too"),))


def test_a_delete_tick_on_a_root_github_has_already_lost_answers_nothing(settings):
    me = GitHub().account
    landing = Landing(settings, author=me,
                      replies=(said(2, "and the test too", author=me),))
    landing.propose()
    landing.root_deleted()

    landing.approve(delete_comment=True)

    assert landing.github.thread(KEY) is not None, "nothing was asked of GitHub"
    landed = landing.stored()
    assert landed.fix.picked and landed.fix.pushed and landed.fix.answered
    assert landing.workspace_dropped()


def test_a_posted_answer_joins_the_transcript_the_panel_shows(settings):
    landing = Landing(settings)
    landing.propose()
    landing.github.refusing = True
    landing.approve("renamed it")
    landing.github.refusing = False
    before = landing.stored()
    assert before.fix.reply_error == "HTTP 403"

    landing.approve("renamed it")

    answered = landing.stored()
    posted = landing.github.thread(KEY).comments[-1]
    assert [(one.id, one.body) for one in answered.comments] == [
        *((one.id, one.body) for one in before.comments), (posted.id, posted.body)]
    assert answered.fix.answered
    assert answered.fix.reply_error is None


def test_an_answer_github_refused_keeps_the_card_and_says_why(settings):
    landing = Landing(settings)
    landing.propose()
    landing.github.refusing = True

    outcome = landing.approve("renamed it")

    assert not isinstance(outcome, Denied)
    refused = landing.stored()
    assert refused.fix.reply_error == "HTTP 403"
    assert refused.fix.picked and refused.fix.pushed and not refused.fix.answered
    assert refused.decidable_at == NOW, (
        "a refused answer is yours to decide from the moment it failed")


def test_an_approve_waits_while_the_rebase_run_is_in_flight(settings):
    landing = Landing(settings)
    landing.rebasing()
    before = landing.stored().fix

    drain(landing.threads)

    assert landing.stored().fix == before
    assert _approval(landing).state is OperationState.REQUEUED


def test_an_approve_waits_while_the_rebase_run_is_queued(settings):
    landing = Landing(settings)
    landing.propose()
    landing.without_runs()
    landing.conflicting()
    landing.approve()
    before = landing.stored().fix

    drain(landing.threads)

    assert landing.stored().fix == before
    assert _approval(landing).state is OperationState.REQUEUED


def test_a_failed_rebase_run_drops_the_approve_and_keeps_the_failure(settings):
    landing = Landing(settings)
    landing.rebasing(finishes=True)
    for _ in range(landing.stored().run_holder.attempts_allowed - 1):
        with landing.threads.editing(KEY) as editable:
            editable.fail("run exited without rebasing")
        start_run(landing.here, landing.threads)
    with landing.threads.editing(KEY) as editable:
        editable.fail("run exited without rebasing")
    drain(landing.threads)
    failed = landing.stored()
    assert failed.fix.has_failed

    outcome = landing.approve()

    assert isinstance(outcome, Denied)
    assert landing.stored().fix == failed.fix, "the failure is what the card must go on saying"


@pytest.mark.parametrize("tests", ["failed", None])
def test_a_rebased_fix_whose_tests_did_not_pass_is_handed_back_once(settings, tests):
    landing = Landing(settings)
    head = landing.rebasing()

    landing.rebased(head, tests=tests)

    fix = landing.stored().fix
    assert fix.is_proposed
    assert fix.reason == (
        f"the rebased fix reports tests {tests}; approve again to land it anyway"
    )
    assert fix.run.kind is OperationKind.FIRST, "approving again lands it"
    assert landing.pr_tree()["f.py"] == "theirs\n"


def test_approving_the_handed_back_rebase_again_lands_it(settings):
    landing = Landing(settings)
    head = landing.rebasing()
    landing.rebased(head, tests="failed")

    landing.approve()

    assert landing.stored().standing is ConversationState.DONE
    assert landing.pr_tree()["f.py"] == "new\n"


def test_a_rebase_that_finds_the_work_done_hands_back_its_reply_and_posts_nothing(settings):
    landing = Landing(settings)
    landing.rebasing()

    with landing.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.ALREADY_DONE, "The PR already renames it.")
    drain(landing.threads)

    stored = landing.stored()
    assert stored.standing is ConversationState.READY
    assert (stored.proposal.kind, stored.proposal.reply) == (
        "reply", "The PR already renames it.")
    assert stored.fix.reason == ("the rebase found the work already done and proposes a "
                                 "reply instead; read it and accept it if it stands")
    assert stored.fix.run.kind is OperationKind.FIRST
    assert landing.github.thread(KEY).comments[1:] == ()
    assert _approval(landing).state is OperationState.REFUSED


def test_a_rebased_fix_whose_tests_passed_lands_without_asking_again(settings):
    landing = Landing(settings)
    head = landing.rebasing()

    landed = landing.rebased(head, tests="passed")

    assert landed.standing is ConversationState.DONE
    assert landed.fix.answered


def test_a_comment_during_a_landing_leaves_the_approve_and_its_words_alone(settings):
    landing = Landing(settings)
    refused = _push_refused(landing, "renamed it")
    record = landing.github.prs[THE_PR]
    [thread] = record.threads
    record.threads.remove(thread)
    landing.github.add_thread(THE_PR, replace(
        thread, comments=(*thread.comments, said(3, "thanks"))))

    hear(landing.threads)

    assert landing.stored().fix == refused.fix
