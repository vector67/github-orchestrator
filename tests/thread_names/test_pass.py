import subprocess
from dataclasses import replace

import pytest

from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.terminal_sessions import Terminals
from github_orchestrator.terminal_sessions.fake import FakeTerminals
from github_orchestrator.thread_names import HeldFolder, NameMigration
from github_orchestrator.wiring import thread_names_wiring, wire
from tests.builders import a_pr
from tests.conftest import fake_provider
from tests.disk_layout import disk_name, thread_dir, thread_file, thread_worktree

THE_PR = a_pr(7, "acme/widgets")
PREFIX = "orchestrator/thread/7/"


def _git(cwd, *args):
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    assert done.returncode == 0, (args, done.stderr)
    return done.stdout.strip()


def _build_clone(root):
    clone = root / "clone"
    subprocess.run(["git", "init", "-q", "-b", "main", str(clone)], check=True)
    _git(clone, "config", "user.email", "t@example.com")
    _git(clone, "config", "user.name", "T")
    (clone / "f").write_text("base\n")
    _git(clone, "add", "f")
    _git(clone, "commit", "-q", "-m", "base")


@pytest.fixture
def clone(tmp_path, git_template):
    git_template(_build_clone)
    return tmp_path / "clone"


def _migration(settings, clone, terminals=None) -> NameMigration:
    wiring = replace(thread_names_wiring(settings, None), clones={THE_PR.repo: clone})
    migration: NameMigration = wire(
        wiring, fake_provider(Terminals, terminals or FakeTerminals())).get(NameMigration)
    return migration


def _migrate(settings, clone):
    _migration(settings, clone).migrate()


def _bare_worktree(settings, key):
    return thread_worktree(settings.thread_worktrees_dir, THE_PR, key).with_name(key)


def _legacy_workspace(settings, clone, key, fix="the agent's fix\n"):
    old = _bare_worktree(settings, key)
    old.parent.mkdir(parents=True, exist_ok=True)
    _git(clone, "worktree", "add", "-q", "-b", PREFIX + key, str(old), "HEAD")
    (old / "f").write_text(fix)
    _git(old, "commit", "-qam", f"fix {key}")
    return old, _git(old, "rev-parse", "HEAD")


def _branch_at(path):
    return _git(path, "symbolic-ref", "--short", "HEAD")


def _new_branch(key):
    return PREFIX + disk_name(key)


def _branches(clone):
    return _git(clone, "for-each-ref", "--format=%(refname:short)", "refs/heads/orchestrator/").split()


def test_record_files_named_by_their_bare_key_take_their_new_names(tmp_path):
    settings = fake_settings(tmp_path)
    folder = thread_dir(settings.threads_dir, THE_PR)
    folder.mkdir(parents=True)
    (folder / "PRRT_abcR.json").write_text("record")
    (folder / "PRRT_abcR.intent").write_text("intent")
    (folder / "poll.cursor").write_text("{}")

    _migrate(settings, tmp_path / "no-clone")

    assert thread_file(settings.threads_dir, THE_PR, "PRRT_abcR").read_text() == "record"
    assert sorted(path.name for path in folder.iterdir()) == sorted([
        f"{disk_name('PRRT_abcR')}.json", f"{disk_name('PRRT_abcR')}.intent",
        f"{disk_name('poll')}.cursor"])


def test_a_record_file_whose_new_name_is_taken_is_left_where_it_is(tmp_path):
    settings = fake_settings(tmp_path)
    folder = thread_dir(settings.threads_dir, THE_PR)
    folder.mkdir(parents=True)
    (folder / "PRRT_a.json").write_text("old")
    thread_file(settings.threads_dir, THE_PR, "PRRT_a").write_text("new")

    _migrate(settings, tmp_path / "no-clone")

    assert (folder / "PRRT_a.json").read_text() == "old"
    assert thread_file(settings.threads_dir, THE_PR, "PRRT_a").read_text() == "new"


def test_a_start_that_finds_the_marker_renames_nothing(tmp_path):
    settings = fake_settings(tmp_path)
    _migrate(settings, tmp_path / "no-clone")
    folder = thread_dir(settings.threads_dir, THE_PR)
    folder.mkdir(parents=True)
    (folder / "PRRT_a.json").write_text("old")

    _migrate(settings, tmp_path / "no-clone")

    assert (folder / "PRRT_a.json").read_text() == "old"


def test_a_config_that_names_no_clones_yet_migrates_nothing_and_leaves_no_marker(tmp_path):
    settings = fake_settings(tmp_path)
    folder = thread_dir(settings.threads_dir, THE_PR)
    folder.mkdir(parents=True)
    (folder / "PRRT_a.json").write_text("old")
    migration: NameMigration = wire(
        replace(thread_names_wiring(settings, None), clones=None),
        fake_provider(Terminals, FakeTerminals())).get(NameMigration)

    migration.migrate()

    assert (folder / "PRRT_a.json").exists()
    assert not migration.migrated() and not settings.layout_marker.exists()


def test_a_bare_key_workspace_moves_to_its_new_name_on_its_renamed_branch(settings, clone):
    old, fix = _legacy_workspace(settings, clone, "PRRT_a")

    _migrate(settings, clone)

    new = thread_worktree(settings.thread_worktrees_dir, THE_PR, "PRRT_a")
    assert not old.exists()
    assert _branch_at(new) == _new_branch("PRRT_a")
    assert _git(new, "rev-parse", "HEAD") == fix
    assert _branches(clone) == [_new_branch("PRRT_a")]


def test_a_bare_key_folder_whose_branch_was_already_renamed_moves_to_its_new_name(settings, clone):
    old, fix = _legacy_workspace(settings, clone, "PRRT_a")
    _git(clone, "branch", "-m", PREFIX + "PRRT_a", _new_branch("PRRT_a"))

    _migrate(settings, clone)

    new = thread_worktree(settings.thread_worktrees_dir, THE_PR, "PRRT_a")
    assert not old.exists() and _git(new, "rev-parse", "HEAD") == fix


def test_a_bare_key_branch_without_a_workspace_is_renamed(settings, clone):
    _git(clone, "branch", PREFIX + "PRRT_a", "HEAD")

    _migrate(settings, clone)

    assert _branches(clone) == [_new_branch("PRRT_a")]


def test_case_twins_each_keep_their_own_fix(settings, clone):
    owner, owner_fix = _legacy_workspace(settings, clone, "IC_ab")
    _git(clone, "pack-refs", "--all")
    _git(clone, "branch", PREFIX + "IC_aB", "main")
    twin_fix = _git(clone, "rev-parse", PREFIX + "IC_aB")

    _migrate(settings, clone)

    assert _git(clone, "rev-parse", _new_branch("IC_ab")) == owner_fix
    assert _git(clone, "rev-parse", _new_branch("IC_aB")) == twin_fix
    new = thread_worktree(settings.thread_worktrees_dir, THE_PR, "IC_ab")
    assert _branch_at(new) == _new_branch("IC_ab")


def test_a_workspace_whose_new_branch_name_is_taken_keeps_its_folder_and_its_branch(settings, clone):
    old, _ = _legacy_workspace(settings, clone, "PRRT_a")
    _git(clone, "branch", _new_branch("PRRT_a"), "main")

    _migrate(settings, clone)

    assert _branch_at(old) == PREFIX + "PRRT_a"
    assert not thread_worktree(settings.thread_worktrees_dir, THE_PR, "PRRT_a").exists()


def test_a_workspace_whose_new_folder_is_taken_keeps_its_folder_and_its_branch(settings, clone):
    old, _ = _legacy_workspace(settings, clone, "PRRT_a")
    taken = thread_worktree(settings.thread_worktrees_dir, THE_PR, "PRRT_a")
    taken.mkdir()

    _migrate(settings, clone)

    assert _branch_at(old) == PREFIX + "PRRT_a"
    assert list(taken.iterdir()) == []


def test_a_locked_workspace_keeps_its_folder_and_its_branch(settings, clone):
    old, _ = _legacy_workspace(settings, clone, "PRRT_a")
    _git(clone, "worktree", "lock", str(old))

    _migrate(settings, clone)

    assert _branch_at(old) == PREFIX + "PRRT_a"


def test_a_branch_that_cannot_take_its_new_name_after_its_workspace_moved_keeps_the_migration_open(
    settings, clone
):
    _legacy_workspace(settings, clone, "PRRT_a")
    lock = clone / ".git" / "refs" / "heads" / f"{_new_branch('PRRT_a')}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.touch()
    migration = _migration(settings, clone)

    migration.migrate()
    migration.migrate()

    assert not migration.migrated() and not settings.layout_marker.exists()
    lock.unlink()
    migration.migrate()
    new = thread_worktree(settings.thread_worktrees_dir, THE_PR, "PRRT_a")
    assert migration.migrated() and _branch_at(new) == _new_branch("PRRT_a")


def test_a_branch_that_cannot_take_its_new_name_is_named_with_the_first_line_git_said_until_it_does(
    settings, clone
):
    _legacy_workspace(settings, clone, "PRRT_a")
    lock = clone / ".git" / "refs" / "heads" / f"{_new_branch('PRRT_a')}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.touch()
    _migration(settings, clone).migrate()

    stuck = _migration(settings, clone).stuck()

    assert [(one.pr, one.thread, one.branch, one.new_branch, one.clone) for one in stuck] == [
        (THE_PR, "PRRT_a", PREFIX + "PRRT_a", _new_branch("PRRT_a"), str(clone))]
    assert ".lock" in stuck[0].error and "\n" not in stuck[0].error
    lock.unlink()
    migration = _migration(settings, clone)
    migration.migrate()
    assert migration.stuck() == [] and _migration(settings, clone).stuck() == []


def test_a_stale_bare_folder_that_is_no_worktree_is_not_moved_into_the_new_name(settings, clone):
    old, fix = _legacy_workspace(settings, clone, "PRRT_a")
    (old / ".git").unlink()
    _git(clone, "worktree", "prune")

    _migrate(settings, clone)

    assert old.is_dir()
    assert not thread_worktree(settings.thread_worktrees_dir, THE_PR, "PRRT_a").exists()
    assert _git(clone, "rev-parse", _new_branch("PRRT_a")) == fix


def _in_session(terminals, worktree, pr=THE_PR):
    terminals.of(pr).start(str(worktree), ["claude"])


def test_a_session_in_a_folder_the_migration_would_move_refuses_it_and_names_that_folder(
    settings, clone
):
    old, _ = _legacy_workspace(settings, clone, "PRRT_a")
    folder = thread_dir(settings.threads_dir, THE_PR)
    folder.mkdir(parents=True)
    (folder / "PRRT_a.json").write_text("record")
    terminals = FakeTerminals()
    _in_session(terminals, old / "src")
    migration = _migration(settings, clone, terminals)

    held = migration.migrate()

    assert held == [HeldFolder(pr=THE_PR, thread="PRRT_a", folder=str(old))]
    assert _branch_at(old) == PREFIX + "PRRT_a" and (folder / "PRRT_a.json").exists()
    assert not migration.migrated()


def test_the_folders_in_the_way_are_named_without_migrating(settings, clone):
    old, _ = _legacy_workspace(settings, clone, "PRRT_a")
    terminals = FakeTerminals()
    _in_session(terminals, old)

    assert _migration(settings, clone, terminals).held() == [
        HeldFolder(pr=THE_PR, thread="PRRT_a", folder=str(old))]
    assert _branch_at(old) == PREFIX + "PRRT_a"


def test_a_session_in_a_folder_the_migration_leaves_where_it_is_does_not_refuse_it(
    settings, clone
):
    _legacy_workspace(settings, clone, "PRRT_a")
    terminals = FakeTerminals()
    _in_session(terminals, clone)

    assert _migration(settings, clone, terminals).migrate() == []
    assert thread_worktree(settings.thread_worktrees_dir, THE_PR, "PRRT_a").is_dir()


def test_closing_the_sessions_in_the_way_lets_the_migration_through(settings, clone):
    old, _ = _legacy_workspace(settings, clone, "PRRT_a")
    terminals = FakeTerminals()
    _in_session(terminals, old)
    elsewhere = a_pr(8, "acme/widgets")
    _in_session(terminals, clone, elsewhere)
    migration = _migration(settings, clone, terminals)

    migration.close_sessions()

    assert migration.migrate() == []
    assert thread_worktree(settings.thread_worktrees_dir, THE_PR, "PRRT_a").is_dir()
    assert terminals.of(THE_PR).listed() == [] and len(terminals.of(elsewhere).listed()) == 1
