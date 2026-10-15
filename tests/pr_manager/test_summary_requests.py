from dataclasses import replace

from github_orchestrator.pr_summaries import PrSummaries
from tests.builders import a_pr
from tests.pr_event_queue.support import head_moved, review_requested
from tests.pr_manager.support import PR, REPO, manager_over

THE_PR = a_pr(PR, REPO)


def _requested(settings, tmp_path, *, is_author):
    manager = manager_over(settings, worktree=tmp_path, is_author=is_author)
    manager.event_queue.add(THE_PR, review_requested("Fix bug", "https://example.com"))
    return manager.run()


def _summaries(manager) -> PrSummaries:
    summaries: PrSummaries = manager.container.get(PrSummaries)
    return summaries


def test_a_review_request_on_a_pr_you_review_makes_its_summary_due(settings, tmp_path):
    manager = _requested(settings, tmp_path, is_author=False)

    assert _summaries(manager).due(set()) == [THE_PR]


def test_a_review_request_on_your_own_pr_never_makes_its_summary_due(settings, tmp_path):
    manager = _requested(settings, tmp_path, is_author=True)

    assert _summaries(manager).due(set()) == []


def test_a_push_after_the_summary_ran_does_not_make_it_due(settings, tmp_path):
    manager = _requested(settings, tmp_path, is_author=False)
    summaries = _summaries(manager)
    ran = summaries.load(THE_PR)
    assert ran is not None
    summaries.save(THE_PR, replace(ran, answered=ran.wanted))

    manager.event_queue.add(THE_PR, head_moved("sha1", "sha2"))
    manager.run()

    assert summaries.due(set()) == []
