import pytest

from github_orchestrator.desktop import Badge
from github_orchestrator.domain import Sha
from github_orchestrator.github import PullRequestState
from tests.builders import a_pr
from tests.working_copies.support import (
    BRANCH,
    PR,
    REPO,
    FakeWorld,
    GitWorld,
    build_origin,
    settle_progress,
)

THE_PR = a_pr(PR, REPO)

KEY = "PRRT_kwDOabc"


@pytest.fixture(params=["fake", "git"])
def world(request, tmp_path, settings, git_template):
    if request.param == "fake":
        return FakeWorld(tmp_path)
    git_template(build_origin)
    return GitWorld(tmp_path, settings)


@pytest.fixture
def copies(world):
    return world.copies


@pytest.fixture
def pr_worktree(world):
    return world.copies.pr_worktree(world.repo_dir, THE_PR, None, None)


@pytest.fixture
def pr_checkout(world, pr_worktree):
    return world.copies.checkout(THE_PR)


@pytest.fixture
def cut(pr_checkout):
    return pr_checkout.workspace(KEY, None).ensure().workspace


GRACE = 3600
RUN_IDLE = 300
OTHER = a_pr(PR + 1, REPO)


def _report(world, worktree, *, now, expected="expected", run_output_at=None, pr=THE_PR):
    return world.copies.report_branch(pr, str(worktree), expected, now=now,
                                      run_output_at=run_output_at)


def test_a_prs_checkout_reads_the_worktree_its_head_branch_is_checked_out_in(
        world, pr_worktree):
    head = Sha(world.head_of(pr_worktree))

    assert world.copies.checkout(THE_PR).commit_message(head) == "feature work"


def test_a_prs_checkout_with_no_worktree_says_so_and_every_read_fails(world):
    checkout = world.copies.checkout(THE_PR)
    head = Sha("a" * 40)

    assert BRANCH in checkout.no_worktree()
    assert checkout.commit_message(head) is None
    assert checkout.diff_files(head, head) is None
    assert checkout.is_clean() is False
    assert checkout.push() == checkout.no_worktree()
    assert checkout.workspace(KEY, None).ensure().failure == checkout.no_worktree()


def test_a_pr_github_will_not_name_a_branch_for_has_no_worktree(world):
    missing = a_pr(PR + 100, REPO)

    assert str(missing) in world.copies.checkout(missing).no_worktree()


def test_a_prs_checkout_with_its_worktree_says_nothing_is_missing(world, pr_worktree):
    assert world.copies.checkout(THE_PR).no_worktree() is None


def test_a_worktree_on_its_branch_has_nothing_wrong(world, pr_worktree):
    assert _report(world, pr_worktree, now=1.0, expected=BRANCH) is None
    assert world.copies.verdict(THE_PR, None, expected=BRANCH, window_open=True, now=2.0,
                                       manager_running=True) is None


def test_a_worktree_that_is_not_there_has_nothing_wrong(world, tmp_path):
    assert _report(world, tmp_path / "gone", now=1.0) is None


def test_a_wrong_branch_holds_for_the_whole_grace_from_when_it_was_first_seen(world, pr_worktree):
    first = _report(world, pr_worktree, now=100.0)
    later = _report(world, pr_worktree, now=1300.0)

    assert (first.worktree, first.here, first.expected) == (str(pr_worktree), BRANCH, "expected")
    assert (first.hands_off, first.seconds_left, first.run_working) == (False, GRACE, False)
    assert (later.hands_off, later.seconds_left) == (False, GRACE - 1200)


@pytest.mark.parametrize("world", ["fake"], indirect=True)
def test_a_wrong_branch_past_its_grace_is_handed_off(world, pr_worktree):
    _report(world, pr_worktree, now=100.0)

    verdict = _report(world, pr_worktree, now=100.0 + GRACE)

    assert (verdict.hands_off, verdict.seconds_left) == (True, 0.0)


@pytest.mark.parametrize("world", ["fake"], indirect=True)
def test_a_run_still_talking_holds_past_the_grace_until_it_goes_quiet(world, pr_worktree):
    _report(world, pr_worktree, now=100.0)
    end = 100.0 + GRACE

    talking = _report(world, pr_worktree, now=end, run_output_at=end - 100)
    quiet = _report(world, pr_worktree, now=end + 10, run_output_at=end - RUN_IDLE)

    assert (talking.hands_off, talking.run_working, talking.seconds_left) == (
        False, True, RUN_IDLE - 100)
    assert (quiet.hands_off, quiet.run_working) == (True, False)


@pytest.mark.parametrize("world", ["fake"], indirect=True)
def test_a_run_talking_inside_the_grace_counts_down_whichever_ends_later(world, pr_worktree):
    verdict = _report(world, pr_worktree, now=100.0, run_output_at=100.0)

    assert (verdict.run_working, verdict.seconds_left) == (True, GRACE)


@pytest.mark.parametrize("world", ["fake"], indirect=True)
def test_the_watcher_starts_the_grace_from_what_the_managers_pane_shows(world, pr_worktree):
    verdict = world.copies.verdict(THE_PR, str(pr_worktree), expected="expected", window_open=True, now=50.0,
                                          manager_running=True)
    reported = _report(world, pr_worktree, now=60.0)

    assert (verdict.hands_off, verdict.seconds_left, verdict.here) == (False, GRACE, BRANCH)
    assert reported.seconds_left == GRACE - 10


@pytest.mark.parametrize("world", ["fake"], indirect=True)
def test_the_watcher_starts_nothing_without_a_live_manager_or_a_known_branch(world, pr_worktree):
    assert world.copies.verdict(THE_PR, str(pr_worktree), expected="expected", window_open=True, now=1.0,
                                       manager_running=False) is None
    assert world.copies.verdict(THE_PR, str(pr_worktree), expected=None, window_open=True, now=1.0,
                                       manager_running=True) is None
    assert world.copies.verdict(THE_PR, None, expected="expected", window_open=True, now=1.0,
                                       manager_running=True) is None


@pytest.mark.parametrize("world", ["fake"], indirect=True)
def test_the_watcher_waits_for_a_run_only_while_its_manager_lives(world, pr_worktree):
    end = 100.0 + GRACE
    _report(world, pr_worktree, now=100.0)
    _report(world, pr_worktree, now=end, run_output_at=end - 1)

    alive = world.copies.verdict(THE_PR, None, expected="expected", window_open=True, now=end, manager_running=True)
    dead = world.copies.verdict(THE_PR, None, expected="expected", window_open=True, now=end, manager_running=False)

    assert (alive.hands_off, alive.run_working) == (False, True)
    assert (dead.hands_off, dead.run_working) == (True, False)


def test_a_requested_release_hands_off_at_once_and_survives_the_next_report(world, pr_worktree):
    _report(world, pr_worktree, now=100.0, run_output_at=100.0)

    assert world.copies.request_release(THE_PR) is True
    again = _report(world, pr_worktree, now=101.0, run_output_at=101.0)

    assert (again.hands_off, again.release_requested) == (True, True)


@pytest.mark.parametrize("world", ["fake"], indirect=True)
def test_a_wrong_branch_is_there_to_ask_about_until_the_right_branch_is_back(world, pr_worktree):
    _report(world, pr_worktree, now=100.0)
    world.copies.request_release(THE_PR)

    asked = world.copies.wrong_branch(THE_PR, now=400.0)
    _report(world, pr_worktree, now=500.0, expected=BRANCH)

    assert (asked.worktree, asked.here, asked.expected) == (str(pr_worktree), BRANCH, "expected")
    assert asked.release_requested is True
    assert world.copies.wrong_branch(THE_PR, now=600.0) is None


@pytest.mark.parametrize("world", ["fake"], indirect=True)
def test_asking_about_a_wrong_branch_never_starts_one(world, pr_worktree):
    assert world.copies.wrong_branch(THE_PR, now=1.0) is None
    assert world.copies.request_release(THE_PR) is False


def test_the_right_branch_again_forgets_the_trouble_and_its_release(world, pr_worktree):
    _report(world, pr_worktree, now=1.0)
    world.copies.request_release(THE_PR)

    assert _report(world, pr_worktree, now=2.0, expected=BRANCH) is None

    fresh = _report(world, pr_worktree, now=3.0)
    assert (fresh.release_requested, fresh.seconds_left) == (False, GRACE)


@pytest.mark.parametrize("world", ["fake"], indirect=True)
def test_a_handed_off_worktree_is_forgotten_and_said_once(world, pr_worktree):
    _report(world, pr_worktree, now=1.0)
    _report(world, pr_worktree, now=1.0, pr=OTHER)

    world.copies.handed_off(THE_PR, "name/#7-defunct")

    assert world.copies.verdict(THE_PR, None, expected="expected", window_open=True, now=2.0,
                                       manager_running=True) is None
    assert world.copies.verdict(OTHER, None, expected="expected", window_open=True, now=2.0,
                                       manager_running=True) is not None
    assert [(n.badge, n.title, n.body) for n in world.notifications.posted] == [
        (Badge.FAILED, f"PR #{PR} left on the wrong branch",
         "Window kept as name/#7-defunct; building a fresh worktree")]


def _sharing(world, worktree, others, now):
    return world.copies.verdict(THE_PR, worktree, now=now, window_open=False, others=others)


def _said(world):
    return [n.title for n in world.notifications.posted]


@pytest.mark.parametrize("world", ["fake"], indirect=True)
def test_a_worktree_no_other_window_is_in_is_not_shared(world, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    assert _sharing(world, tmp_path, {}, 1.0) is None
    assert _sharing(world, tmp_path, {OTHER: str(elsewhere)}, 1.0) is None
    assert world.notifications.posted == []


def test_a_shared_worktree_holds_and_says_so_on_the_first_and_every_fifth_check(world, tmp_path):
    verdicts = [_sharing(world, tmp_path, {OTHER: str(tmp_path)}, 100.0 + 60 * i)
                for i in range(5)]

    assert [v.hands_off for v in verdicts] == [False] * 5
    assert [v.seconds_left for v in verdicts] == [1200.0, 1140.0, 1080.0, 1020.0, 960.0]
    assert _said(world) == [f"PR #{PR} shares a worktree"] * 2
    assert world.notifications.posted[0].body == (
        f"{tmp_path.name} is already PR #{PR + 1}'s — not opening a window; "
        f"press w on PR #{PR + 1}'s screen to release it")


@pytest.mark.parametrize("world", ["fake"], indirect=True)
def test_another_windows_directory_is_compared_resolved(world, tmp_path):
    shared = tmp_path / "wt"
    shared.mkdir()
    link = tmp_path / "link"
    link.symlink_to(shared)

    assert not _sharing(world, shared, {OTHER: str(link)}, 1.0).hands_off


@pytest.mark.parametrize("world", ["fake"], indirect=True)
def test_a_worktree_still_shared_after_twenty_minutes_is_handed_off_and_forgotten(world, tmp_path):
    _sharing(world, tmp_path, {OTHER: str(tmp_path)}, 100.0)

    verdict = _sharing(world, tmp_path, {OTHER: str(tmp_path)}, 100.0 + 20 * 60)
    again = _sharing(world, tmp_path, {OTHER: str(tmp_path)}, 5000.0)

    assert verdict.hands_off is True
    assert world.notifications.posted[1].body == (
        f"{tmp_path.name} is still PR #{PR + 1}'s after 20 min — opening it anyway")
    assert (again.hands_off, again.seconds_left) == (False, 1200.0)


@pytest.mark.parametrize("world", ["fake"], indirect=True)
def test_a_shared_worktree_that_moves_or_stops_being_shared_starts_counting_again(world, tmp_path):
    moved = tmp_path / "moved"
    moved.mkdir()
    _sharing(world, tmp_path, {OTHER: str(tmp_path)}, 100.0)

    elsewhere = _sharing(world, moved, {OTHER: str(moved)}, 700.0)
    _sharing(world, moved, {}, 800.0)
    back = _sharing(world, moved, {OTHER: str(moved)}, 900.0)

    assert elsewhere.seconds_left == 1200.0
    assert back.seconds_left == 1200.0
    assert len(_said(world)) == 3


def test_a_pr_with_no_worktree_gets_one_cut_on_its_branch(world):
    cut = world.copies.pr_worktree(world.repo_dir, THE_PR, BRANCH, None)

    assert cut == world.repo_dir.parent / BRANCH
    assert world.branch_at(cut) == BRANCH


def test_a_pr_whose_branch_has_a_worktree_gets_that_one_back(world, pr_worktree):
    assert world.copies.pr_worktree(world.repo_dir, THE_PR, BRANCH, None) == pr_worktree


def test_the_main_checkout_on_the_prs_branch_goes_back_to_main_for_a_fresh_cut(world):
    world.check_out(world.repo_dir, BRANCH)

    cut = world.copies.pr_worktree(world.repo_dir, THE_PR, BRANCH, None)

    assert cut == world.repo_dir.parent / BRANCH
    assert world.branch_at(world.repo_dir) == "main"
    assert world.branch_at(cut) == BRANCH


def test_a_pr_whose_worktree_cannot_be_cut_gets_none(world):
    world.github.add_pr(a_pr(PR + 1, REPO), PullRequestState(branch="not-on-origin"))

    assert world.copies.pr_worktree(world.repo_dir, a_pr(PR + 1, REPO), None, None) is None
    assert not (world.repo_dir.parent / "not-on-origin").exists()


def test_a_reused_worktree_whose_branch_will_not_fetch_says_so(world, tmp_path):
    world.local_worktree(tmp_path / "local", "local-only")

    reused = world.copies.pr_worktree(world.repo_dir, THE_PR, "local-only", None, fetch=True)

    assert reused == tmp_path / "local"
    assert [(n.badge, n.title) for n in world.notifications.posted] == [
        (Badge.FAILED, f"PR #{PR} fetch failed")]


def test_a_branch_that_will_not_fetch_says_so(world, tmp_path):
    world.local_worktree(tmp_path / "local", "local-only")

    world.copies.fetch_pr_branch(world.repo_dir, THE_PR, "local-only", None)

    assert [(n.badge, n.title, n.body) for n in world.notifications.posted] == [
        (Badge.FAILED, f"PR #{PR} fetch failed",
         "Could not fetch local-only; the previous head's objects may be gone")]


def test_a_branch_origin_has_fetches_quietly(world, pr_worktree):
    world.copies.fetch_pr_branch(world.repo_dir, THE_PR, BRANCH, None)

    assert world.notifications.posted == []


def _base_of(checkout, head):
    diff = checkout.pr_diff("main", Sha(head))
    return None if diff is None else diff.base


def test_refreshing_a_prs_branch_fetches_its_base_too(world, pr_worktree, pr_checkout):
    base, head = world.advance_base()

    world.copies.fetch_pr_branch(world.repo_dir, THE_PR, BRANCH, "main")

    assert _base_of(pr_checkout, head) == Sha(base)


def test_a_new_worktree_fetches_the_prs_base_too(world):
    base, head = world.advance_base()

    world.copies.pr_worktree(world.repo_dir, THE_PR, BRANCH, "main")

    assert _base_of(world.copies.checkout(THE_PR), head) == Sha(base)


def test_a_base_that_will_not_fetch_leaves_the_head_fetched_and_says_nothing(
        world, pr_worktree, pr_checkout):
    _, head = world.advance_base()

    world.copies.fetch_pr_branch(world.repo_dir, THE_PR, BRANCH, "gone")

    assert pr_checkout.has_commit(Sha(head))
    assert world.notifications.posted == []


def test_fetching_a_prs_checkout_moves_its_origin_head_and_not_its_local_one(
        world, pr_worktree, pr_checkout):
    pushed = world.head_of(pr_worktree)
    _, head = world.advance_base()
    before = pr_checkout.origin_head()

    assert pr_checkout.fetch("main") is None

    assert (before, pr_checkout.origin_head(), pr_checkout.local_head()) == (
        Sha(pushed), Sha(head), Sha(pushed))


def test_a_commit_not_pushed_moves_only_the_local_head(world, pr_worktree, pr_checkout):
    pushed = world.head_of(pr_worktree)

    local = world.commit(pr_worktree, {"h": "x\n"}, "local work")

    assert (pr_checkout.origin_head(), pr_checkout.local_head()) == (Sha(pushed), Sha(local))


def test_a_branch_no_worktree_holds_is_not_fetched(world):
    world.copies.fetch_pr_branch(world.repo_dir, THE_PR, "local-only", None)

    assert world.notifications.posted == []


def test_a_pr_branch_already_checked_out_gets_no_second_worktree(world, pr_worktree):
    assert world.copies.pr_worktree(world.repo_dir, THE_PR, None, None) is None


def test_forgetting_a_pr_whose_branch_is_in_the_main_worktree_leaves_the_main_one(world):
    world.check_out(world.repo_dir, BRANCH)

    assert world.copies.forget_pr(world.repo_dir, THE_PR, BRANCH) is True

    assert world.branch_at(world.repo_dir) == BRANCH


def test_the_commits_since_a_sha_name_each_commit_on_head_after_it(world, pr_worktree):
    pushed = world.head_of(pr_worktree)

    assert world.copies.commits_since(pr_worktree, pushed) == ()
    world.commit(pr_worktree, {"h": "x\n"}, "local work")
    [line] = world.copies.commits_since(pr_worktree, pushed)
    sha, subject = line.split(" ", 1)
    assert (world.head_of(pr_worktree).startswith(sha), subject) == (True, "local work")
    assert world.copies.commits_since(pr_worktree, None) is None
    assert world.copies.commits_since(pr_worktree, "0" * 40) is None


def test_a_thread_gets_its_own_worktree_at_the_pr_head(world, pr_worktree, cut):
    checkout = cut.path

    assert cut.base_sha == Sha(world.head_of(pr_worktree))
    assert cut.head_sha() == cut.base_sha
    assert world.branch_at(checkout) == f"orchestrator/thread/{PR}/{KEY}"
    assert checkout != str(pr_worktree)


def test_a_thread_key_that_is_no_file_name_is_encoded_into_its_branch_and_worktree(
    world, pr_checkout,
):
    cut = pr_checkout.workspace("MDI0/UmV2=", None).ensure().workspace

    assert world.branch_at(cut.path) == f"orchestrator/thread/{PR}/MDI0%2FUmV2%3D"
    assert cut.path.endswith(f"/{PR}/MDI0%2FUmV2%3D")


@pytest.mark.parametrize("key", ["", ".", ".."])
def test_a_thread_key_that_names_no_worktree_of_its_own_is_refused(pr_checkout, key):
    with pytest.raises(ValueError):
        pr_checkout.workspace(key, None).ensure().workspace


def test_a_thread_whose_base_is_recorded_and_whose_worktree_is_there_keeps_it(
        world, pr_checkout, cut):
    worked = Sha(world.commit(cut.path, {"h": "x\n"}, "half done"))

    again = pr_checkout.workspace(KEY, cut.base_sha).ensure().workspace

    assert (again.path, again.branch, again.base_sha) == (cut.path, cut.branch, cut.base_sha)
    assert again.head_sha() == worked


def test_a_worktree_no_record_adopted_is_cut_afresh(world, pr_checkout, cut):
    world.commit(cut.path, {"h": "x\n"}, "left by a cut nobody saved")

    again = pr_checkout.workspace(KEY, None).ensure().workspace

    assert again.path == cut.path
    assert again.head_sha() == again.base_sha == cut.base_sha


def test_a_thread_nobody_adopted_names_no_worktree_or_branch(pr_checkout):
    held = pr_checkout.workspace(KEY, None)

    assert (held.path, held.branch, held.head_sha()) == (None, None, None)


def test_a_dropped_workspace_is_gone(world, pr_worktree, cut):
    cut.drop()

    assert cut.head_sha() is None
    assert world.branch_at(cut.path) is None


THREAD_BRANCH = f"orchestrator/thread/{PR}/{KEY}"


def test_forgetting_a_pr_takes_its_worktree_its_thread_workspaces_and_their_branches(world, pr_worktree, cut):
    assert world.copies.forget_pr(world.repo_dir, THE_PR, BRANCH) is True

    assert world.branch_at(pr_worktree) is None
    assert world.branch_at(cut.path) is None
    assert not world.has_branch(THREAD_BRANCH)
    assert world.branch_at(world.repo_dir) == "main"


def test_forgetting_a_pr_leaves_another_prs_thread_workspaces(world, pr_worktree, cut):
    elsewhere = a_pr(PR * 10, REPO)
    world.github.add_pr(elsewhere, PullRequestState(branch=BRANCH))
    other = world.copies.checkout(elsewhere).workspace(KEY, None).ensure().workspace

    assert world.copies.forget_pr(world.repo_dir, THE_PR, BRANCH) is True

    assert other.head_sha() == other.base_sha


def test_forgetting_a_pr_takes_a_thread_branch_whose_worktree_already_went(world, pr_worktree, cut):
    world.lose_worktree(cut.path)

    assert world.copies.forget_pr(world.repo_dir, THE_PR, BRANCH) is True

    assert not world.has_branch(THREAD_BRANCH)


def test_a_thread_branch_that_will_not_go_fails_the_forget_for_a_retry(world, pr_worktree, cut):
    world.lose_worktree(cut.path)
    world.check_out(world.repo_dir, THREAD_BRANCH)

    assert world.copies.forget_pr(world.repo_dir, THE_PR, BRANCH) is False

    assert world.branch_at(pr_worktree) is None


def test_forgetting_a_pr_forgets_its_branch_trouble(world, pr_worktree):
    _report(world, pr_worktree, now=1.0)

    assert world.copies.forget_pr(world.repo_dir, THE_PR, BRANCH) is True

    assert world.copies.request_release(THE_PR) is False


def test_forgetting_a_pr_forgets_that_its_worktree_was_shared(world, pr_worktree, tmp_path):
    _sharing(world, tmp_path, {OTHER: str(tmp_path)}, 100.0)

    assert world.copies.forget_pr(world.repo_dir, THE_PR, None) is True

    assert _sharing(world, tmp_path, {OTHER: str(tmp_path)}, 700.0).seconds_left == 1200.0


@pytest.mark.parametrize("branch", [BRANCH, None])
def test_forgetting_a_pr_that_left_nothing_is_fine(world, branch):
    assert world.copies.forget_pr(world.repo_dir, THE_PR, branch) is True


def test_a_workspace_with_nothing_done_has_no_progress(world, cut):
    assert cut.progress() is None


def test_progress_counts_commits_and_changed_files(world, cut):
    checkout = cut.path
    world.commit(checkout, {"g": "one\n2\nthree\n"}, "fix")
    world.edit(checkout, "f", "changed\n")

    cut.progress()
    settle_progress()
    assert cut.progress() == "1 commit, 1 file changed"


def test_a_fix_descends_from_its_base_and_not_the_other_way(world, cut):
    tip = Sha(world.commit(cut.path, {"g": "one\n2\nthree\n"}, "fix"))

    assert cut.descends(cut.base_sha, tip) is True
    assert cut.descends(tip, cut.base_sha) is False


def test_a_picked_fix_lands_on_the_pr_branch(world, pr_worktree, cut, pr_checkout):
    tip = Sha(world.commit(cut.path, {"g": "one\n2\nthree\n"}, "fix the middle"))

    landed = cut.pick(tip)

    assert landed.landed_sha is not None
    assert landed.landed_base == cut.base_sha
    assert Sha(world.head_of(pr_worktree)) == landed.landed_sha
    assert pr_checkout.blob(landed.landed_sha, "g") == b"one\n2\nthree\n"
    assert pr_checkout.commit_message(landed.landed_sha) == "fix the middle"


def test_a_fix_of_several_commits_lands_as_one(world, pr_worktree, cut, pr_checkout):
    checkout = cut.path
    world.commit(checkout, {"g": "one\n2\nthree\n"}, "first half")
    tip = Sha(world.commit(checkout, {"h": "new\n"}, "second half"))

    landed = cut.pick(tip)

    assert len(world.copies.commits_since(pr_worktree, str(cut.base_sha))) == 1
    assert pr_checkout.commit_message(landed.landed_sha) == "second half"


def test_a_fix_lands_with_the_message_it_is_given(world, pr_worktree, cut, pr_checkout):
    tip = Sha(world.commit(cut.path, {"g": "one\n2\nthree\n"}, "wip"))

    landed = cut.pick(tip, "Fix the middle line")

    assert pr_checkout.commit_message(landed.landed_sha) == "Fix the middle line"


def test_a_fix_that_names_no_commit_is_not_picked(world, pr_worktree, cut):
    head = Sha(world.head_of(pr_worktree))

    refused = cut.pick(None)

    assert refused.not_commits
    assert Sha(world.head_of(pr_worktree)) == head


def test_a_fix_changed_after_review_is_not_picked(world, pr_worktree, cut):
    checkout = cut.path
    reviewed = Sha(world.commit(checkout, {"g": "one\n2\nthree\n"}, "fix"))
    world.commit(checkout, {"h": "sneaky\n"}, "later")

    refused = cut.pick(reviewed)

    assert refused.changed_since_review


def test_a_fix_whose_branch_is_gone_is_not_picked(world, pr_worktree, cut):
    tip = Sha(world.commit(cut.path, {"g": "one\n2\nthree\n"}, "fix"))
    cut.drop()

    refused = cut.pick(tip)

    assert refused.missing_branch is not None
    assert refused.missing_branch == cut.branch


def test_a_fix_that_conflicts_leaves_the_pr_branch_where_it_was(world, pr_worktree, cut,
                                                                 pr_checkout):
    tip = Sha(world.commit(cut.path, {"g": "one\n2\nthree\n"}, "fix"))
    moved = Sha(world.commit(pr_worktree, {"g": "one\nTWO\nthree\n"}, "meanwhile"))

    conflict = cut.pick(tip)

    assert conflict.conflict is not None
    assert conflict.conflict_head == moved
    assert Sha(world.head_of(pr_worktree)) == moved
    assert pr_checkout.is_clean() is True


def test_a_landed_fix_can_be_pushed(world, pr_worktree, cut, pr_checkout):
    tip = Sha(world.commit(cut.path, {"g": "one\n2\nthree\n"}, "fix"))
    landed = cut.pick(tip)

    assert pr_checkout.push() is None
    assert world.copies.forget_pr(world.repo_dir, THE_PR, BRANCH) is True

    again = world.copies.pr_worktree(world.repo_dir, THE_PR, None, None)
    assert Sha(world.head_of(again)) == landed.landed_sha


def test_an_unpushed_pick_comes_off_the_pr_branch(world, pr_worktree, cut, pr_checkout):
    landed = cut.pick(Sha(world.commit(cut.path, {"g": "one\n2\nthree\n"}, "fix")))

    assert pr_checkout.unpick(landed.landed_base, landed.landed_sha) is None
    assert Sha(world.head_of(pr_worktree)) == landed.landed_base
    assert pr_checkout.is_clean() is True


def test_a_pr_branch_moved_past_the_pick_is_left_where_it_is(world, pr_worktree, cut,
                                                            pr_checkout):
    landed = cut.pick(Sha(world.commit(cut.path, {"g": "one\n2\nthree\n"}, "fix")))
    moved = Sha(world.commit(pr_worktree, {"h": "meanwhile\n"}, "meanwhile"))

    refused = pr_checkout.unpick(landed.landed_base, landed.landed_sha)

    assert refused is not None and str(moved)[:12] in refused
    assert Sha(world.head_of(pr_worktree)) == moved


def test_a_pr_worktree_with_changes_keeps_its_pick(world, pr_worktree, cut, pr_checkout):
    landed = cut.pick(Sha(world.commit(cut.path, {"g": "one\n2\nthree\n"}, "fix")))
    world.edit(pr_worktree, "f", "half done\n")

    refused = pr_checkout.unpick(landed.landed_base, landed.landed_sha)

    assert refused is not None
    assert Sha(world.head_of(pr_worktree)) == landed.landed_sha
    assert pr_checkout.is_clean() is False


def test_a_diff_is_files_hunks_and_numbered_lines(world, cut, pr_checkout):
    checkout = cut.path
    tip = Sha(world.commit(checkout, {"g": "one\n2\nthree\n", "h": "new\n"}, "fix"))

    files = {diff.path: diff for diff in pr_checkout.diff_files(cut.base_sha, tip)}

    assert (files["h"].status, files["h"].added, files["h"].removed) == ("added", 1, 0)
    changed = files["g"]
    assert (changed.status, changed.added, changed.removed) == ("modified", 1, 1)
    [hunk] = changed.hunks
    assert [(line.kind, line.old_line, line.new_line, line.text) for line in hunk.lines] == [
        ("context", 1, 1, "one"),
        ("removed", 2, None, "two"),
        ("added", None, 2, "2"),
        ("context", 3, 3, "three"),
    ]


def test_the_prs_diff_runs_from_where_the_branch_left_main_to_its_head(
        world, pr_worktree, cut, pr_checkout):
    diff = pr_checkout.pr_diff("main", cut.base_sha)

    assert diff is not None
    assert pr_checkout.commit_message(diff.base) == "first"
    assert diff.head == cut.base_sha
    assert [(file.path, file.status) for file in diff.files] == [("g", "added")]
    assert pr_checkout.pr_diff(None, cut.base_sha) == diff
    assert pr_checkout.pr_diff("--nope", cut.base_sha) == diff


def test_commits_and_files_are_found_only_where_they_are(cut, pr_checkout):
    assert pr_checkout.has_commit(cut.base_sha) is True
    assert pr_checkout.has_commit(Sha("0" * 40)) is False
    assert pr_checkout.blob(cut.base_sha, "g") == b"one\ntwo\nthree\n"
    assert pr_checkout.blob(cut.base_sha, "missing") is None
