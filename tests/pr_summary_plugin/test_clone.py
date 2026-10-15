import subprocess
from pathlib import Path

import pytest
from pr_summary.clone import Clone, names_repo
from pr_summary.inputs import ChangedFile, Unreadable


def git(where: Path, *args: str) -> str:
    identity = ["-c", "user.name=Octo Cat", "-c", "user.email=octocat@example.com", "-c", "init.defaultBranch=main"]
    return subprocess.run(["git", *identity, *args], cwd=where, capture_output=True, text=True, check=True).stdout.strip()


def commit(where: Path, message: str, files: dict[str, str | None]) -> str:
    for name, text in files.items():
        path = where / name
        if text is None:
            git(where, "rm", "-q", name)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        git(where, "add", name)
    git(where, "commit", "-q", "-m", message)
    return git(where, "rev-parse", "HEAD")


@pytest.fixture
def origin(tmp_path: Path) -> dict[str, str]:
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q")
    branch_point = commit(work, "start", {"src/rows.py": "x = 1\n", "src/old.py": "y = 2\n" * 5, "src/gone.py": "z = 3\n", "src/pkg/a.py": "a = 1\n"})
    git(work, "checkout", "-q", "-b", "feature")
    commit(work, "change", {"src/rows.py": "x = 2\n", "src/new.py": "y = 2\n" * 5, "src/old.py": None, "src/gone.py": None, "src/added.py": "w = 4\n"})
    head = git(work, "rev-parse", "HEAD")
    git(work, "checkout", "-q", "main")
    base = commit(work, "main moves on", {"src/later.py": "v = 5\n"})
    bare = tmp_path / "acme" / "shop.git"
    bare.parent.mkdir()
    git(tmp_path, "clone", "-q", "--bare", str(work), str(bare))
    git(bare, "update-ref", "refs/pull/7/head", head)
    git(bare, "branch", "-q", "-D", "feature")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(bare), str(clone))
    return {"clone": str(clone), "base": base, "head": head, "branch_point": branch_point}


def fetched(origin: dict[str, str]) -> Clone:
    clone = Clone.find(Path(origin["clone"]), "acme", "shop")
    assert clone is not None
    clone.fetch(7, origin["base"])
    return clone


def test_remote_urls_name_their_repository() -> None:
    assert names_repo("git@github.com:acme/shop.git", "acme", "shop")
    assert names_repo("https://github.com/Acme/Shop", "acme", "shop")
    assert names_repo("/srv/git/acme/shop.git", "acme", "shop")
    assert not names_repo("git@github.com:acme/shopfront.git", "acme", "shop")
    assert not names_repo("git@github.com:other/shop.git", "acme", "shop")


def test_a_folder_that_is_not_a_clone_of_the_repository_is_none(tmp_path: Path, origin: dict[str, str]) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    assert Clone.find(elsewhere, "acme", "shop") is None
    assert Clone.find(Path(origin["clone"]), "acme", "other") is None


def test_the_diff_base_is_where_the_pr_branched_not_the_base_tip(origin: dict[str, str]) -> None:
    clone = fetched(origin)

    assert clone.merge_base(origin["base"], origin["head"]) == origin["branch_point"]


def test_changed_files_come_from_git_against_the_merge_base(origin: dict[str, str]) -> None:
    clone = fetched(origin)

    files = sorted(clone.changed_files(origin["branch_point"], origin["head"]), key=lambda changed: changed.path)

    assert files == [
        ChangedFile("src/added.py", None, "added", 1),
        ChangedFile("src/gone.py", None, "removed", 1),
        ChangedFile("src/new.py", "src/old.py", "renamed", 0),
        ChangedFile("src/rows.py", None, "modified", 2),
    ]


def test_contents_are_the_exact_bytes_or_none_or_unreadable(origin: dict[str, str]) -> None:
    clone = fetched(origin)

    assert clone.contents(origin["head"], "src/rows.py") == b"x = 2\n"
    assert clone.contents(origin["head"], "src/old.py") is None
    with pytest.raises(Unreadable):
        clone.contents(origin["head"], "src/pkg")


def test_history_lists_the_commits_that_touched_a_path_newest_first(origin: dict[str, str]) -> None:
    clone = fetched(origin)

    assert clone.history(origin["base"], "src/rows.py", 5) == [origin["branch_point"]]
