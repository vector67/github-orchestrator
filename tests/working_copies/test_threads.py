import subprocess
from pathlib import Path

import pytest

from github_orchestrator.domain import Sha
from tests.builders import a_pr
from tests.disk_layout import thread_worktree
from tests.working_copies.support import copies_for

GIT_TIMEOUT = 60
SQUASH_FAILED = "the fix's commits could not be squashed into one"

REPO = "acme/widgets"
PR = 7
THE_PR = a_pr(PR, REPO)
THREAD_KEY = "PRRT_101"
NO_WORKTREE = a_pr(99, REPO)


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True
    )


def _build_pr_worktree(root):
    bare = root / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    repo = root / "prwork"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    (repo / "f").write_text("base\n")
    _git(repo, "add", "f")
    assert _git(repo, "commit", "-q", "-m", "base").returncode == 0
    _git(repo, "remote", "add", "origin", str(bare))
    push = _git(repo, "push", "-q", "-u", "origin", "main")
    assert push.returncode == 0, push.stderr


@pytest.fixture
def remote(tmp_path, git_template):
    git_template(_build_pr_worktree)
    return tmp_path / "origin.git"


@pytest.fixture
def pr_worktree(tmp_path, remote):
    return tmp_path / "prwork"


@pytest.fixture
def worktrees_dir(settings):
    return settings.thread_worktrees_dir


@pytest.fixture
def git(settings, pr_worktree):
    return copies_for(settings, THE_PR, pr_worktree)


def _in(git, pr=THE_PR):
    return git.checkout(pr)


def _held(git, pr_worktree, base_sha=None, key=THREAD_KEY):
    return _in(git).workspace(key, base_sha)


def _cut(git, pr_worktree, key=THREAD_KEY, base_sha=None):
    return _held(git, pr_worktree, base_sha, key).ensure().workspace


def _git_answers(monkeypatch, answer):
    real = subprocess.run
    seen = []

    def run(argv, *args, **kwargs):
        if argv[0] == "git" and "-C" in argv and kwargs.get("stdin") is subprocess.DEVNULL:
            at = argv.index("-C")
            cwd, rest = argv[at + 1], tuple(argv[at + 2:])
            seen.append(rest)
            answered = answer(cwd, rest)
            if answered is not None:
                return answered
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    return seen


def _never_git(monkeypatch, why):
    def refuse(cwd, args):
        pytest.fail(why)

    return _git_answers(monkeypatch, refuse)


def test_a_workspace_is_cut_off_the_pr_head_on_its_own_branch(
    git, pr_worktree, worktrees_dir
):
    head = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    cut = _cut(git, pr_worktree)

    wt, branch = cut.path, cut.branch
    assert wt == str(thread_worktree(worktrees_dir, THE_PR, THREAD_KEY))
    assert (Path(wt) / "f").read_text() == "base\n"
    assert branch == f"orchestrator/thread/{PR}/{THREAD_KEY}"
    assert str(cut.base_sha) == head
    verify = _git(pr_worktree, "rev-parse", "--verify", branch)
    assert verify.returncode == 0
    assert verify.stdout.strip() == head


def test_a_workspace_cut_over_a_stale_one_starts_clean(git, pr_worktree):
    first = _cut(git, pr_worktree)
    wt, _ = first.path, first.branch
    (Path(wt) / "leftover").write_text("stale attempt")

    again = _cut(git, pr_worktree)

    assert (again.path, again.branch) == (first.path, first.branch)
    assert Path(wt).is_dir()
    assert not (Path(wt) / "leftover").exists()
    listing = _git(pr_worktree, "worktree", "list", "--porcelain").stdout
    assert listing.count(wt) == 1


def test_the_new_worktree_command_initialises_a_workspace_it_just_cut(settings, pr_worktree):
    git = copies_for(settings, THE_PR, pr_worktree, new_worktree_command=(
        'printf %s "$GITHUB_ORCHESTRATOR_SOURCE_REPO" > initialised'))

    cut = _cut(git, pr_worktree)

    assert (Path(cut.path) / "initialised").read_text() == str(pr_worktree)


def test_a_worktree_add_git_refuses_raises(git, pr_worktree, worktrees_dir):
    worktrees_dir.mkdir(parents=True)
    (worktrees_dir / "acme").write_text("in the way")

    assert _held(git, pr_worktree).ensure().workspace is None


def test_a_cut_that_failed_leaves_a_branch_the_next_cut_clears(
    git, pr_worktree, worktrees_dir
):
    head = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()
    branch = f"orchestrator/thread/{PR}/{THREAD_KEY}"

    worktrees_dir.mkdir(parents=True)
    blocker = worktrees_dir / "acme"
    blocker.write_text("in the way")
    assert _held(git, pr_worktree).ensure().workspace is None
    assert _git(pr_worktree, "rev-parse", "--verify", branch).returncode == 0

    blocker.unlink()
    cut = _cut(git, pr_worktree)

    wt, _ = cut.path, cut.branch
    assert (Path(wt) / "f").read_text() == "base\n"
    assert str(cut.base_sha) == head
    verify = _git(pr_worktree, "rev-parse", "--verify", branch)
    assert verify.returncode == 0
    assert verify.stdout.strip() == head


def test_a_workspace_that_is_still_there_is_handed_back_with_its_base(
    git, pr_worktree, worktrees_dir
):
    first = _cut(git, pr_worktree)
    (pr_worktree / "f").write_text("moved on\n")
    _git(pr_worktree, "add", "f")
    _git(pr_worktree, "commit", "-q", "-m", "move")

    again = _cut(git, pr_worktree, base_sha=first.base_sha)

    assert (again.path, again.branch) == (first.path, first.branch)
    assert again.base_sha == first.base_sha


def test_a_workspace_whose_directory_is_gone_is_cut_again(
    git, pr_worktree, worktrees_dir
):
    first = _cut(git, pr_worktree)
    worktree, _ = first.path, first.branch
    _git(pr_worktree, "worktree", "remove", "--force", worktree)
    (pr_worktree / "f").write_text("moved on\n")
    _git(pr_worktree, "add", "f")
    _git(pr_worktree, "commit", "-q", "-m", "move")
    head = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    again = _cut(git, pr_worktree, base_sha=first.base_sha)

    assert (again.path, again.branch) == (first.path, first.branch)
    assert str(again.base_sha) == head
    assert again.path == worktree


def test_a_clean_pr_worktree_is_clean(git, pr_worktree):
    assert _in(git).is_clean() is True


@pytest.mark.parametrize("staged", [False, True], ids=["unstaged", "staged"])
def test_a_tracked_change_makes_the_pr_worktree_dirty(git, pr_worktree, staged):
    (pr_worktree / "f").write_text("uncommitted tracked change\n")
    if staged:
        _git(pr_worktree, "add", "f")

    assert _in(git).is_clean() is False


def test_an_untracked_file_leaves_the_pr_worktree_clean(git, pr_worktree):
    (pr_worktree / "agent-changes.md").write_text("# changes\n")

    assert _in(git).is_clean() is True


def test_dropping_a_workspace_removes_its_checkout_and_its_branch(
    git, pr_worktree, worktrees_dir
):
    cut = _cut(git, pr_worktree)
    branch = cut.branch

    cut.drop()

    assert not thread_worktree(worktrees_dir, THE_PR, THREAD_KEY).exists()
    assert _git(pr_worktree, "rev-parse", "--verify", branch).returncode != 0


def test_dropping_a_fix_that_never_had_a_workspace_runs_no_git(
    git, pr_worktree, monkeypatch
):
    _never_git(monkeypatch, "no worktree to remove and no branch to delete")

    _held(git, pr_worktree).drop()


def _fix_in_a_workspace(git, pr_worktree, key=THREAD_KEY, name="f",
                        text="fixed\n"):
    cut = _cut(git, pr_worktree, key)
    worktree, _ = cut.path, cut.branch
    (Path(worktree) / name).write_text(text)
    _git(worktree, "add", name)
    assert _git(worktree, "commit", "-q", "-m", f"fix {key}").returncode == 0
    return cut, _git(worktree, "rev-parse", "HEAD").stdout.strip()


def _commit_in(worktree, name, text, message, author, date):
    (Path(worktree) / name).write_text(text)
    _git(worktree, "add", name)
    done = _git(worktree, "commit", "-q", "-m", message, f"--author={author}",
                f"--date={date}")
    assert done.returncode == 0, done.stderr
    return _git(worktree, "rev-parse", "HEAD").stdout.strip()


def _spied_git(monkeypatch):
    return _git_answers(monkeypatch, lambda cwd, args: None)


def _move_the_pr_head(pr_worktree, text):
    (pr_worktree / "f").write_text(text)
    _git(pr_worktree, "add", "f")
    assert _git(pr_worktree, "commit", "-q", "-m", "move").returncode == 0


@pytest.mark.parametrize("base_sha,thread_sha", [
    ("a" * 40, "--output=/tmp/pwned"),
    ("--output=/tmp/pwned", "b" * 40),
    ("a" * 40, "HEAD"),
])
def test_a_pick_whose_revs_are_not_commits_never_reaches_git(
    git, monkeypatch, base_sha, thread_sha,
):
    _never_git(monkeypatch, "git was handed a rev that is not a commit")
    workspace = _held(git, "/tmp/prwork", base_sha)

    refused = workspace.pick(thread_sha)

    assert refused.not_commits


@pytest.mark.parametrize("onto,head", [
    ("--output=/tmp/pwned", "e" * 40),
    ("e" * 40, "--output=/tmp/pwned"),
])
def test_the_revs_a_rebase_is_judged_on_never_reach_git_as_options(
    git, monkeypatch, onto, head,
):
    _never_git(monkeypatch, "git was handed a rev that is not a commit")
    workspace = _held(git, "/tmp/prwork", "a" * 40)

    assert workspace.descends(onto, head) is False


def test_two_commits_the_rebase_can_be_judged_on_still_reach_git(git, monkeypatch):
    seen = _git_answers(monkeypatch,
                        lambda cwd, args: subprocess.CompletedProcess(["git"], 0, "", ""))
    workspace = _held(git, "/tmp/prwork", "a" * 40)

    workspace.descends("d" * 40, "e" * 40)

    assert seen and "--end-of-options" in seen[0]
    assert seen[0].index("--end-of-options") < seen[0].index("d" * 40)


def test_a_pick_folds_every_commit_the_fix_left_into_the_tips_one(git,
                                                                  pr_worktree):
    cut, _ = _fix_in_a_workspace(git, pr_worktree)
    worktree, _ = cut.path, cut.branch
    _commit_in(worktree, "g", "second\n", "second attempt",
               "Ada Lovelace <ada@example.com>", "2026-02-02T02:02:02Z")
    tip = _commit_in(worktree, "h", "third\n", "the fix as it now stands",
                     "Grace Hopper <grace@example.com>", "2026-03-03T03:03:03Z")
    before = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    picked = cut.pick(tip)

    assert picked.landed_sha is not None
    assert str(picked.landed_base) == before
    assert str(picked.landed_sha) == _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()
    assert _git(pr_worktree, "rev-list", "--count",
                f"{before}..HEAD").stdout.strip() == "1"
    assert _git(pr_worktree, "log", "-1",
                "--format=%s%n%an <%ae>%n%aI").stdout == (
        "the fix as it now stands\n"
        "Grace Hopper <grace@example.com>\n"
        "2026-03-03T03:03:03Z\n")
    assert (_git(pr_worktree, "rev-parse", "HEAD^{tree}").stdout.strip()
            == _git(worktree, "rev-parse", f"{tip}^{{tree}}").stdout.strip())
    assert (pr_worktree / "f").read_text() == "fixed\n"
    assert (pr_worktree / "g").read_text() == "second\n"
    assert (pr_worktree / "h").read_text() == "third\n"


def test_a_squash_that_fails_puts_the_pr_head_back_and_refuses(
    git, pr_worktree, monkeypatch
):
    cut, _ = _fix_in_a_workspace(git, pr_worktree)
    worktree, _ = cut.path, cut.branch
    tip = _commit_in(worktree, "g", "second\n", "second attempt",
                     "Ada Lovelace <ada@example.com>", "2026-02-02T02:02:02Z")
    before = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    def fake_git(cwd, args):
        if args[0] == "commit":
            return subprocess.CompletedProcess(
                args, 1, "", "error: could not write the squashed commit\n")
        return None

    _git_answers(monkeypatch, fake_git)

    refused = cut.pick(tip)

    assert refused.refusal is not None
    assert "could not write the squashed commit" in refused.refusal
    assert "the PR branch is back at" in refused.refusal
    assert _git(pr_worktree, "rev-parse", "HEAD").stdout.strip() == before
    assert _git(pr_worktree, "status", "--porcelain").stdout.strip() == ""
    assert not (pr_worktree / "g").exists()


def _two_commit_fix(git, pr_worktree):
    cut, _ = _fix_in_a_workspace(git, pr_worktree)
    worktree, _ = cut.path, cut.branch
    tip = _commit_in(worktree, "g", "second\n", "second attempt",
                     "Ada Lovelace <ada@example.com>", "2026-02-02T02:02:02Z")
    return cut, tip


def test_a_squash_that_raises_puts_the_pr_head_back_and_refuses(
    git, pr_worktree, monkeypatch
):
    cut, tip = _two_commit_fix(git, pr_worktree)
    before = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    def fake_git(cwd, args):
        if args[0] == "commit":
            raise subprocess.TimeoutExpired(["git", "commit"], GIT_TIMEOUT)
        return None

    _git_answers(monkeypatch, fake_git)

    refused = cut.pick(tip)

    assert refused.refusal is not None
    assert refused.refusal.startswith(f"{SQUASH_FAILED} — ")
    assert "timed out" in refused.refusal
    assert "the PR branch is back at" in refused.refusal
    assert _git(pr_worktree, "rev-parse", "HEAD").stdout.strip() == before
    assert _git(pr_worktree, "status", "--porcelain").stdout.strip() == ""
    assert not (pr_worktree / "g").exists()


def test_a_rewind_that_fails_leaves_the_range_landed_and_refuses(
    git, pr_worktree, monkeypatch
):
    cut, tip = _two_commit_fix(git, pr_worktree)
    before = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    def fake_git(cwd, args):
        if args[:2] == ("reset", "--soft"):
            return subprocess.CompletedProcess(
                args, 1, "", "fatal: Could not reset index file\n")
        return None

    _git_answers(monkeypatch, fake_git)

    refused = cut.pick(tip)

    assert refused.refusal is not None
    assert "Could not reset index file" in refused.refusal
    assert "the PR branch is back at" in refused.refusal
    assert _git(pr_worktree, "rev-parse", "HEAD").stdout.strip() == before
    assert _git(pr_worktree, "status", "--porcelain").stdout.strip() == ""


def test_a_squash_whose_restore_fails_sends_the_operator_to_the_worktree(
    git, pr_worktree, monkeypatch
):
    cut, tip = _two_commit_fix(git, pr_worktree)

    def fake_git(cwd, args):
        if args[0] == "commit":
            return subprocess.CompletedProcess(
                args, 1, "", "error: could not write the squashed commit\n")
        if args[:2] == ("reset", "--hard"):
            return subprocess.CompletedProcess(
                args, 1, "", "fatal: Unable to create '.git/index.lock'\n")
        return None

    _git_answers(monkeypatch, fake_git)

    refused = cut.pick(tip)

    assert refused.refusal is not None
    assert "could not write the squashed commit" in refused.refusal
    assert "could not be put back" in refused.refusal
    assert "index.lock" in refused.refusal
    assert "check the PR worktree" in refused.refusal
    assert "staged" not in refused.refusal
    assert "the PR branch is back at" not in refused.refusal


def test_a_head_that_will_not_read_leaves_the_landing_alone_and_says_so(
    git, pr_worktree, monkeypatch
):
    cut, tip = _two_commit_fix(git, pr_worktree)
    before = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()
    reads = []

    def fake_git(cwd, args):
        if args[:2] == ("rev-parse", "HEAD"):
            reads.append(args)
            if len(reads) > 1:
                raise subprocess.TimeoutExpired(["git", "rev-parse"],
                                                GIT_TIMEOUT)
        return None

    _git_answers(monkeypatch, fake_git)

    refused = cut.pick(tip)

    assert refused.refusal is not None
    assert "is on the PR branch" in refused.refusal
    assert _git(pr_worktree, "rev-list", "--count",
                f"{before}..HEAD").stdout.strip() == "1"
    assert (pr_worktree / "g").read_text() == "second\n"


def test_a_range_that_undoes_itself_says_there_was_nothing_left_to_land(
    git, pr_worktree
):
    cut, _ = _fix_in_a_workspace(git, pr_worktree)
    worktree, _ = cut.path, cut.branch
    tip = _commit_in(worktree, "f", "base\n", "and back again",
                     "Ada Lovelace <ada@example.com>", "2026-02-02T02:02:02Z")
    before = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    refused = cut.pick(tip)

    assert refused.refusal is not None
    assert "nothing left to land" in refused.refusal
    assert "could not be squashed" not in refused.refusal
    assert _git(pr_worktree, "rev-parse", "HEAD").stdout.strip() == before
    assert _git(pr_worktree, "status", "--porcelain").stdout.strip() == ""


def test_a_count_that_raises_leaves_the_range_landed_unsquashed(
    git, pr_worktree, monkeypatch
):
    cut, tip = _two_commit_fix(git, pr_worktree)
    before = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    def fake_git(cwd, args):
        if args[0] == "rev-list":
            raise subprocess.TimeoutExpired(["git", "rev-list"], GIT_TIMEOUT)
        return None

    _git_answers(monkeypatch, fake_git)

    picked = cut.pick(tip)

    assert picked.landed_sha is not None
    assert str(picked.landed_base) == before
    assert str(picked.landed_sha) == _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()
    assert _git(pr_worktree, "rev-list", "--count",
                f"{before}..HEAD").stdout.strip() == "2"


def test_the_squash_commit_never_runs_the_repos_hooks(git, pr_worktree):
    cut, tip = _two_commit_fix(git, pr_worktree)
    hooks = pr_worktree / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    before = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    picked = cut.pick(tip)

    assert picked.landed_sha is not None
    assert _git(pr_worktree, "rev-list", "--count",
                f"{before}..HEAD").stdout.strip() == "1"
    assert (pr_worktree / "g").read_text() == "second\n"


def test_an_abbreviated_thread_sha_names_the_same_commit_and_lands(
    git, pr_worktree
):
    cut, sha = _fix_in_a_workspace(git, pr_worktree)

    picked = cut.pick(sha[:9])

    assert picked.landed_sha is not None
    assert str(picked.landed_sha) == _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()


def test_an_abbreviated_thread_sha_the_tip_moved_past_is_still_refused(
    git, pr_worktree
):
    cut, reviewed = _fix_in_a_workspace(git, pr_worktree)
    worktree, _ = cut.path, cut.branch
    (Path(worktree) / "g").write_text("unreviewed\n")
    _git(worktree, "add", "g")
    assert _git(worktree, "commit", "-q", "-m", "unreviewed").returncode == 0

    refused = cut.pick(reviewed[:9])

    assert refused.changed_since_review


def test_a_branch_git_cannot_resolve_is_refused_with_what_git_said(
    git, pr_worktree
):
    cut, sha = _fix_in_a_workspace(git, pr_worktree)
    worktree, branch = cut.path, cut.branch
    assert _git(pr_worktree, "worktree", "remove", "--force",
                worktree).returncode == 0
    assert _git(pr_worktree, "branch", "-D", branch).returncode == 0
    before = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    refused = cut.pick(sha)

    assert refused.missing_branch is not None
    assert refused.missing_branch == branch
    assert refused.diagnostic.startswith("fatal:")
    assert _git(pr_worktree, "rev-parse", "HEAD").stdout.strip() == before


def test_a_fix_with_no_workspace_is_refused_rather_than_raising(git, pr_worktree):
    refused = _held(git, pr_worktree).pick("deadbeef")

    assert refused.refusal == (
        "approve intent on a thread with no branch or base_sha")


def test_a_conflicting_pick_is_aborted_and_names_the_head_it_hit(
    git, pr_worktree
):
    cut, _ = _fix_in_a_workspace(git, pr_worktree, text="thread\n")
    worktree, _ = cut.path, cut.branch
    (Path(worktree) / "g").write_text("from the fix\n")
    _git(worktree, "add", "g")
    assert _git(worktree, "commit", "-q", "-m", "add g").returncode == 0
    sha = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    _move_the_pr_head(pr_worktree, "moved\n")
    head = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    conflicted = cut.pick(sha)

    assert conflicted.conflict is not None
    assert str(conflicted.conflict_head) == head
    assert "could not apply" in conflicted.diagnostic
    assert "hint:" not in conflicted.diagnostic
    assert _git(pr_worktree, "rev-parse", "HEAD").stdout.strip() == head
    assert _git(pr_worktree, "status", "--porcelain").stdout.strip() == ""
    assert not (pr_worktree / "g").exists()


def test_a_conflict_says_how_far_the_pr_head_is_from_the_fixs_base(
    git, pr_worktree
):
    cut, sha = _fix_in_a_workspace(git, pr_worktree, text="thread\n")
    for n in range(3):
        _move_the_pr_head(pr_worktree, f"moved {n}\n")

    conflicted = cut.pick(sha)

    assert conflicted.conflict is not None
    assert "3 commits from the thread's base" in conflicted.conflict
    assert "could not apply" in conflicted.conflict


def test_the_diagnosis_leads_the_conflict_and_gits_hints_go(git, pr_worktree):
    cut, sha = _fix_in_a_workspace(git, pr_worktree, text="thread\n")
    _move_the_pr_head(pr_worktree, "moved\n")

    conflicted = cut.pick(sha)

    assert "hint:" not in conflicted.conflict
    assert (conflicted.conflict.index("1 commit from")
            < conflicted.conflict.index("could not apply"))


def test_a_divergence_lookup_that_fails_degrades_to_the_plain_conflict(
    git, pr_worktree, monkeypatch
):
    cut, sha = _fix_in_a_workspace(git, pr_worktree, text="thread\n")
    _move_the_pr_head(pr_worktree, "moved\n")

    def fake_git(cwd, args):
        if args[0] == "rev-list":
            raise subprocess.TimeoutExpired(["git", "rev-list"], GIT_TIMEOUT)
        return None

    _git_answers(monkeypatch, fake_git)

    conflicted = cut.pick(sha)

    assert conflicted.conflict is not None
    assert "could not apply" in conflicted.conflict
    assert "commits from" not in conflicted.conflict


def test_a_cherry_pick_that_times_out_is_aborted_and_refused(
    git, pr_worktree, monkeypatch
):
    cut, sha = _fix_in_a_workspace(git, pr_worktree, text="thread\n")
    _move_the_pr_head(pr_worktree, "moved\n")
    real_git = subprocess.run
    aborts = []

    def fake_git(cwd, args):
        if args[:2] == ("cherry-pick", "--abort"):
            aborts.append(args)
        result = real_git(["git", "-C", cwd, *args], capture_output=True, text=True)
        if args[0] == "cherry-pick" and args[1] != "--abort":
            raise subprocess.TimeoutExpired(["git", "cherry-pick"], GIT_TIMEOUT)
        return result

    _git_answers(monkeypatch, fake_git)

    refused = cut.pick(sha)

    assert refused.refusal == (
        f"cherry-pick timed out after {GIT_TIMEOUT}s and was aborted")
    assert aborts
    assert _git(pr_worktree, "status", "--porcelain").stdout.strip() == ""


def test_an_abort_that_fails_says_the_worktree_may_be_left_unclean(
    git, pr_worktree, monkeypatch
):
    cut, sha = _fix_in_a_workspace(git, pr_worktree)

    def fake_git(cwd, args):
        if args[:2] == ("cherry-pick", "--abort"):
            return subprocess.CompletedProcess(
                args, 1, "", "error: no cherry-pick in progress\n")
        if args[0] == "cherry-pick":
            raise subprocess.TimeoutExpired(["git", "cherry-pick"], GIT_TIMEOUT)
        return None

    _git_answers(monkeypatch, fake_git)

    refused = cut.pick(sha)

    assert refused.refusal == (
        f"cherry-pick timed out after {GIT_TIMEOUT}s and the abort failed — "
        f"the PR worktree may be left unclean: "
        f"error: no cherry-pick in progress")


def test_an_abort_that_raises_says_the_worktree_may_be_left_unclean(
    git, pr_worktree, monkeypatch
):
    cut, sha = _fix_in_a_workspace(git, pr_worktree)

    def fake_git(cwd, args):
        if args[0] == "cherry-pick":
            raise subprocess.TimeoutExpired(["git", "cherry-pick"], GIT_TIMEOUT)
        return None

    _git_answers(monkeypatch, fake_git)

    refused = cut.pick(sha)

    assert "the abort raised" in refused.refusal
    assert "may be left unclean" in refused.refusal


def test_a_push_with_no_remote_keeps_gits_fatal_line_and_drops_its_advice(
    git, pr_worktree
):
    _git(pr_worktree, "remote", "remove", "origin")

    error = _in(git).push()

    assert error.startswith("fatal:")
    assert "git remote add" not in error
    assert "Either specify the URL" not in error
    assert len(error.splitlines()) == 1


def test_a_push_to_a_remote_that_is_gone_keeps_both_fatal_lines(
    git, pr_worktree, tmp_path
):
    _git(pr_worktree, "remote", "set-url", "origin", str(tmp_path / "gone.git"))

    error = _in(git).push()

    assert "does not appear to be a git repository" in error
    assert "Please make sure you have the correct access rights" not in error
    assert len(error.splitlines()) == 2


def test_a_rebased_workspace_descends_from_what_it_was_rebased_onto(
    git, pr_worktree
):
    cut, _ = _fix_in_a_workspace(git, pr_worktree, name="g", text="fix\n")
    worktree, _ = cut.path, cut.branch
    _move_the_pr_head(pr_worktree, "moved\n")
    onto = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()
    assert _git(worktree, "rebase", onto).returncode == 0
    rebased = _git(worktree, "rev-parse", "HEAD").stdout.strip()

    assert cut.descends(onto, rebased) is True


def test_descending_is_answered_about_the_sha_given_not_the_workspaces_head(
    git, pr_worktree
):
    cut, before = _fix_in_a_workspace(git, pr_worktree, name="g", text="fix\n")
    worktree, _ = cut.path, cut.branch
    _move_the_pr_head(pr_worktree, "moved\n")
    onto = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()
    assert _git(worktree, "rebase", onto).returncode == 0
    rebased = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    assert _git(worktree, "reset", "--hard", before).returncode == 0

    assert cut.descends(onto, rebased) is True


def test_a_fix_with_no_workspace_has_no_progress_to_count(git):
    assert _held(git, "/tmp/prwork").progress() is None


def test_the_commit_message_is_the_whole_message_the_agent_wrote(git,
                                                                 pr_worktree):
    cut, _ = _fix_in_a_workspace(git, pr_worktree)
    worktree, _ = cut.path, cut.branch
    tip = _commit_in(worktree, "g", "second\n",
                     "Rename the helper\n\nIt said the wrong thing.",
                     "Ada Lovelace <ada@example.com>", "2026-02-02T02:02:02Z")

    assert _in(git).commit_message(Sha(tip)) == (
        "Rename the helper\n\nIt said the wrong thing.")


def test_a_commit_git_does_not_know_has_no_message(git, pr_worktree):
    assert _in(git).commit_message(Sha("e" * 40)) is None


def test_a_pick_given_a_message_lands_its_one_commit_with_it(git, pr_worktree):
    cut, sha = _fix_in_a_workspace(git, pr_worktree)
    before = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    picked = cut.pick(sha,
                      message="Rename the helper\n\nAs Anna asked.")

    assert picked.landed_sha is not None
    assert _git(pr_worktree, "rev-list", "--count",
                f"{before}..HEAD").stdout.strip() == "1"
    assert _git(pr_worktree, "log", "-1", "--format=%B").stdout == (
        "Rename the helper\n\nAs Anna asked.\n\n")
    assert (pr_worktree / "f").read_text() == "fixed\n"


def test_a_pick_given_a_message_folds_every_commit_into_one_with_it(
    git, pr_worktree
):
    cut, _ = _fix_in_a_workspace(git, pr_worktree)
    worktree, _ = cut.path, cut.branch
    tip = _commit_in(worktree, "g", "second\n", "second attempt",
                     "Ada Lovelace <ada@example.com>", "2026-02-02T02:02:02Z")
    before = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    picked = cut.pick(tip,
                      message="Rename the helper")

    assert picked.landed_sha is not None
    assert _git(pr_worktree, "rev-list", "--count",
                f"{before}..HEAD").stdout.strip() == "1"
    assert _git(pr_worktree, "log", "-1", "--format=%s").stdout.strip() == (
        "Rename the helper")
    assert (pr_worktree / "g").read_text() == "second\n"
