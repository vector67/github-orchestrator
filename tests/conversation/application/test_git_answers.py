from github_orchestrator.conversation import ConversationState
from github_orchestrator.domain import Sha
from tests.conversation.support import (
    THE_PR,
    drain,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    world,
)

KEY = "PRRT_101"
PR_WORKTREE = "/work/widgets"


def _commented(settings):
    here = world(settings)
    base = repo_at(here.working_copies, PR_WORKTREE, {"f": "base\n"})
    threads = here.threads(worktree=PR_WORKTREE)
    on_github(here.github, KEY, said(101, "fix f"))
    hear(threads)
    return here, threads, base


def _proposed(settings):
    here, threads, base = _commented(settings)
    propose(here, threads, KEY, {"f": "base\nfixed\n"})
    return here, threads, base, threads.get(KEY)


def _approve(threads):
    with threads.editing(KEY) as editable:
        editable.approve()
    drain(threads)
    return threads.get(KEY)


def test_a_landed_fix_comes_across_as_it_landed(settings):
    here, threads, base, _ = _proposed(settings)

    landed = _approve(threads)

    assert landed.fix.picked
    assert landed.fix.landed_base == Sha(base)
    assert landed.fix.landed_sha == Sha(here.working_copies.branches["main"])
    assert Sha(here.working_copies.origin["main"]) == landed.fix.landed_sha


def test_a_conflicting_fix_comes_across_with_the_head_and_the_conflict(settings):
    here, threads, _, _ = _proposed(settings)
    head = Sha(here.working_copies.commit(PR_WORKTREE, {"f": "moved on\n"}, "moved"))

    rebasing = _approve(threads)

    assert rebasing.standing is ConversationState.LANDING
    assert rebasing.fix.run.is_rebase
    assert rebasing.fix.run.onto == head
    assert rebasing.fix.run.conflict == "CONFLICT (content): Merge conflict in f"


def test_a_fix_changed_after_review_asks_for_a_fresh_report(settings):
    here, threads, _, proposed = _proposed(settings)
    checkout = here.working_copies.thread_checkout(THE_PR, KEY)
    here.working_copies.commit(checkout, {"f": "base\nfixed again\n"}, "more")

    refused = _approve(threads)

    assert refused.fix.is_proposed
    assert "was changed after" in refused.fix.reason
    assert "cli thread ready --sha" in refused.fix.reason
    assert "send back for rework" in refused.fix.reason
    assert str(proposed.fix.thread_sha)[:12] not in refused.fix.reason


def test_a_fix_whose_branch_is_gone_says_what_git_said(settings):
    here, threads, _, _ = _proposed(settings)
    branch = f"orchestrator/thread/{THE_PR.number}/{KEY}"
    here.working_copies.branches.pop(branch)

    refused = _approve(threads)

    assert refused.fix.is_proposed
    assert branch in refused.fix.reason
    assert "could not be resolved" in refused.fix.reason
    assert "fatal:" in refused.fix.reason
    assert "send back for rework" in refused.fix.reason


def test_the_fold_shows_the_commit_the_agent_left_until_it_lands(settings):
    _, _, base, proposed = _proposed(settings)

    assert proposed.fix.commits == (Sha(base), proposed.fix.thread_sha)


def test_the_fold_shows_the_pr_head_either_side_once_the_fix_lands(settings):
    _, threads, _, proposed = _proposed(settings)

    landed = _approve(threads)

    assert landed.fix.commits == (landed.fix.landed_base, landed.fix.landed_sha)
    assert landed.fix.commits != proposed.fix.commits


def test_a_fix_that_has_committed_nothing_has_no_range_to_show(settings):
    _, threads, _ = _commented(settings)

    assert threads.get(KEY).fix.commits is None

