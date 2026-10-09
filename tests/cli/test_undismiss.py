import pytest

from tests.builders import a_pr
from tests.change_detection.support import polled_on_disk, seen
from tests.settings.support import disk_dismissals

REPO = "octocat/hello-world"


@pytest.fixture
def undismiss_dirs(settings):
    settings.dismissed_dir.mkdir()
    settings.state_dir.mkdir()


def _track(settings, pr):
    polled_on_disk(settings.state_dir, a_pr(pr, REPO),
                   seen(settings.config.gh_account))


def test_undismiss_a_dismissed_pr_says_it_cleared_the_flag(undismiss_dirs, run_cli, settings):
    disk_dismissals(settings.data_dir).dismiss_forever(a_pr(61, REPO))
    _track(settings, 61)
    ran = run_cli("undismiss", "--repo", REPO, "61")
    assert ran.out == (
        "Cleared dismissal for octocat/hello-world#61; "
        "the window reopens on the next poll cycle (~1 min).\n")


def test_undismiss_clears_a_flag_that_outlived_its_state_file(undismiss_dirs, run_cli, settings):
    disk_dismissals(settings.data_dir).dismiss_forever(a_pr(77, REPO))
    ran = run_cli("undismiss", "--repo", REPO, "77")
    assert "Cleared dismissal" in ran.out
    assert ran.err == ""


def test_undismiss_a_tracked_pr_that_was_never_dismissed_says_nothing_to_do(
    undismiss_dirs, run_cli, settings,
):
    _track(settings, 61)
    ran = run_cli("undismiss", "--repo", REPO, "61")
    assert "Cleared dismissal" not in ran.out
    assert "was not dismissed" in ran.out
    assert ran.err == ""


def test_undismiss_an_untracked_pr_warns_without_failing(undismiss_dirs, run_cli):
    ran = run_cli("undismiss", "--repo", REPO, "99999")
    assert ran.code == 0
    assert "Cleared dismissal" not in ran.out
    assert "was not dismissed" in ran.out
    assert "99999" in ran.err
    assert "not tracking" in ran.err
    assert "check the PR number" not in ran.err


def test_undismiss_names_the_repo_since_a_hub_watches_more_than_one(undismiss_dirs, run_cli):
    ran = run_cli("undismiss", "61")

    assert ran.code == 2
    assert "--repo" in ran.err
