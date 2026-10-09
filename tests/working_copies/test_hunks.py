import subprocess

import pytest

from github_orchestrator.domain import Sha
from tests.builders import a_pr
from tests.working_copies.support import copies_for

WRITER = """\
import sys


def write(items):
    begin()
    middle()
    header()
    for a in items:
        emit(a)
    footer()
"""

RENAMED = "".join(f"line {n}\n" for n in range(1, 30))


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _build_history(root):
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    (repo / "billing").mkdir()
    (repo / "billing" / "invoice_writer.py").write_text(WRITER)
    (repo / "old").mkdir()
    (repo / "old" / "name.py").write_text(RENAMED)
    (repo / "gone.py").write_text("nothing here\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "billing" / "invoice_writer.py").write_text(WRITER.replace(
        "    for a in items:\n",
        "    for item in items:\n        check(item)\n"))
    (repo / "new").mkdir()
    _git(repo, "mv", "old/name.py", "new/name.py")
    (repo / "new" / "name.py").write_text(RENAMED.replace("line 1\n", "line one\n"))
    (repo / "logo.png").write_bytes(bytes(range(256)))
    _git(repo, "rm", "-q", "gone.py")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "head")
    return base, _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def copies(settings, tmp_path):
    return copies_for(settings, a_pr(1, "o/n"), tmp_path / "repo")


@pytest.fixture
def changed(tmp_path, git_template, copies):
    base, head = git_template(_build_history)
    files = copies.checkout(a_pr(1, "o/n")).diff_files(Sha(base.strip()), Sha(head.strip()))
    return {diff.path: diff for diff in files}


def test_a_hunk_carries_its_lines_with_both_numberings(changed):
    writer = changed["billing/invoice_writer.py"]

    assert writer.status == "modified"
    assert (writer.added, writer.removed) == (2, 1)
    [hunk] = writer.hunks
    assert (hunk.old_start, hunk.old_lines) == (5, 6)
    assert (hunk.new_start, hunk.new_lines) == (5, 7)
    assert hunk.section == "def write(items):"
    assert [(line.kind, line.old_line, line.new_line, line.text)
            for line in hunk.lines] == [
        ("context", 5, 5, "    begin()"),
        ("context", 6, 6, "    middle()"),
        ("context", 7, 7, "    header()"),
        ("removed", 8, None, "    for a in items:"),
        ("added", None, 8, "    for item in items:"),
        ("added", None, 9, "        check(item)"),
        ("context", 9, 10, "        emit(a)"),
        ("context", 10, 11, "    footer()"),
    ]


def test_a_renamed_file_keeps_the_name_it_came_from(changed):
    renamed = changed["new/name.py"]

    assert renamed.old_path == "old/name.py"
    assert renamed.status == "renamed"


def test_a_binary_file_is_named_and_has_no_hunks(changed):
    logo = changed["logo.png"]

    assert logo.status == "added"
    assert logo.is_binary is True
    assert logo.hunks == ()


def test_a_deleted_file_is_named_by_the_side_it_came_from(changed):
    gone = changed["gone.py"]

    assert gone.status == "removed"
    assert (gone.added, gone.removed) == (0, 1)


def test_the_files_come_back_in_the_order_git_printed_them(tmp_path, git_template, copies):
    base, head = git_template(_build_history)

    files = copies.checkout(a_pr(1, "o/n")).diff_files(Sha(base.strip()), Sha(head.strip()))

    assert [one.path for one in files] == [
        "billing/invoice_writer.py", "gone.py", "logo.png", "new/name.py"]


def test_a_commit_against_itself_changes_nothing(tmp_path, git_template, copies):
    _, head = git_template(_build_history)

    assert copies.checkout(a_pr(1, "o/n")).diff_files(Sha(head.strip()), Sha(head.strip())) == ()
