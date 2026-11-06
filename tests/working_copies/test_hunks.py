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
    files = copies.checkout(a_pr(1, "o/n")).revisions.diff_files(Sha(base.strip()), Sha(head.strip()))
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

    files = copies.checkout(a_pr(1, "o/n")).revisions.diff_files(Sha(base.strip()), Sha(head.strip()))

    assert [one.path for one in files] == [
        "billing/invoice_writer.py", "gone.py", "logo.png", "new/name.py"]


def test_a_commit_against_itself_changes_nothing(tmp_path, git_template, copies):
    _, head = git_template(_build_history)

    assert copies.checkout(a_pr(1, "o/n")).revisions.diff_files(Sha(head.strip()), Sha(head.strip())) == ()


def _write(path, content):
    if content is None:
        path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _two_commits(root, config, before, after):
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    for path, content in before:
        _write(repo / path, content)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    for path, content in after:
        _write(repo / path, content)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "head")
    for key, value in config:
        _git(repo, "config", key, value)
    return base, _git(repo, "rev-parse", "HEAD")


def _diffed(git_template, copies, config=(), before=(), after=()):
    base, head = git_template(_two_commits, config, before, after)
    files = copies.checkout(a_pr(1, "o/n")).revisions.diff_files(Sha(base), Sha(head))
    return {diff.path: diff for diff in files}


SOURCE = b"".join(b"line %d\n" % n for n in range(1, 30))


def test_a_line_that_is_not_utf8_reads_with_a_replacement_character(git_template, copies):
    files = _diffed(git_template, copies, after=(("menu.txt", "café\n".encode("latin-1")),))

    [hunk] = files["menu.txt"].hunks
    assert [line.text for line in hunk.lines] == ["caf�"]


def test_a_config_that_detects_copies_still_shows_a_copy_as_an_added_file(git_template, copies):
    files = _diffed(git_template, copies, config=(("diff.renames", "copies"),),
                    before=(("original.txt", SOURCE),),
                    after=(("original.txt", SOURCE.replace(b"line 1\n", b"line one\n")),
                           ("a_copy.txt", SOURCE)))

    assert [(path, diff.status, diff.old_path) for path, diff in files.items()] == [
        ("a_copy.txt", "added", None), ("original.txt", "modified", None)]


def test_an_external_diff_tool_in_the_config_is_not_used(git_template, copies):
    files = _diffed(git_template, copies, config=(("diff.external", "true"),),
                    after=(("notes.txt", b"hello\n"),))

    assert list(files) == ["notes.txt"]


def test_a_textconv_filter_in_the_config_is_not_used(git_template, copies):
    files = _diffed(git_template, copies, config=(("diff.shout.textconv", "rev"),),
                    before=((".gitattributes", b"*.txt diff=shout\n"),),
                    after=(("notes.txt", b"hello\n"),))

    [hunk] = files["notes.txt"].hunks
    assert [line.text for line in hunk.lines] == ["hello"]


def test_a_blank_context_line_keeps_the_numbers_when_the_config_suppresses_its_space(
        git_template, copies):
    files = _diffed(git_template, copies, config=(("diff.suppressBlankEmpty", "true"),),
                    before=(("notes.txt", b"one\n\ntwo\n"),),
                    after=(("notes.txt", b"one\n\nthree\n"),))

    [hunk] = files["notes.txt"].hunks
    assert [(line.kind, line.old_line, line.new_line) for line in hunk.lines] == [
        ("context", 1, 1), ("context", 2, 2), ("removed", 3, None), ("added", None, 3)]


@pytest.mark.parametrize("name", ["x b/y.txt", "café.txt", "tab\there.txt", 'say "hi".txt'])
def test_a_file_name_comes_back_as_it_is_on_disk(git_template, copies, name):
    files = _diffed(git_template, copies, after=((name, b"hello\n"),))

    assert list(files) == [name]
    assert files[name].status == "added"


def test_a_renamed_file_keeps_both_names_as_they_are_on_disk(git_template, copies):
    files = _diffed(git_template, copies, before=(("old name.txt", SOURCE),),
                    after=(("old name.txt", None), ("x b/café.txt", SOURCE)))

    renamed = files["x b/café.txt"]
    assert (renamed.status, renamed.old_path) == ("renamed", "old name.txt")
