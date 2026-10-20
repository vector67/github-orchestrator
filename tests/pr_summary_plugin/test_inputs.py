from collections.abc import Callable
from pathlib import Path

import pytest
from pr_summary.inputs import (
    ChangedFile,
    EarlierPr,
    Unreadable,
    WorkDirNotEmpty,
    work_dir,
    write_inputs,
    write_surroundings,
)
from pr_summary.pull_request import PullRequest, Remark
from pr_summary.settings import Settings
from pr_summary.witnesses import run_witnesses

BASE = "b" * 40
HEAD = "h" * 40

PR = PullRequest(
    number=7,
    url="https://github.com/acme/shop/pull/7",
    title="[SHOP-3] Hide the export button",
    body="Hides the button when exports are off.",
    created_at="2026-10-01T09:00:00Z",
    branch="SHOP-3-hide-button",
    base_sha=BASE,
    head_sha=HEAD,
    author="octocat",
    authors=frozenset({"octocat"}),
    author_names=frozenset({"Octo Cat"}),
    commit_messages=("hide the button behind the exports flag",),
    changed_file_count=6,
    remarks=(
        Remark(author="octocat", bot=False, body="Exports are being rewritten.", url="u1"),
        Remark(author="monalisa", bot=False, body="> Exports are being rewritten.\nWhich ticket covers the rewrite?", url="u2"),
        Remark(author="claude", bot=True, body="This PR hides the export button.", url="u3"),
    ),
)

CONTENTS: dict[tuple[str, str], bytes] = {
    (BASE, "src/toolbar.py"): b"def buttons():\n    return ['export']\n",
    (HEAD, "src/toolbar.py"): b"def buttons(flags):\n    # hidden while exports are rewritten\n    return ['export'] if flags.exports else []\n",
    (HEAD, "tests/test_toolbar.py"): b'def test_hidden():\n    """The button hides when exports are off."""\n    assert buttons(Off()) == []\n',
    (BASE, "README.md"): b"Export from the toolbar.\n",
    (HEAD, "README.md"): b"Export from the toolbar when enabled.\n",
    (BASE, "src/old_name.py"): b"x = 1\n",
    (HEAD, "src/new_name.py"): b"x = 2\n",
    (HEAD, "assets/logo.png"): b"\x89PNG\r\n\x1a\n\x00\xff\xfe",
    (HEAD, "uv.lock"): b"lock\n",
}

FILES = [
    ChangedFile(path="src/toolbar.py", previous=None, status="modified", changes=3),
    ChangedFile(path="tests/test_toolbar.py", previous=None, status="added", changes=3),
    ChangedFile(path="README.md", previous=None, status="modified", changes=2),
    ChangedFile(path="src/new_name.py", previous="src/old_name.py", status="renamed", changes=2),
    ChangedFile(path="assets/logo.png", previous=None, status="added", changes=0),
    ChangedFile(path="uv.lock", previous=None, status="modified", changes=1),
]

EARLIER = [
    EarlierPr(
        number=3,
        url="https://github.com/acme/shop/pull/3",
        title="Rewrite the exporter",
        body="First step of the export rewrite.",
        author="monalisa",
        merged_at="2026-09-20T10:00:00Z",
        remarks=(
            Remark(author="hubot", bot=False, body="Exports time out on large shops; the button must go until this lands.", url="e1"),
            Remark(author="octocat", bot=False, body="I will hide the button meanwhile.", url="e2"),
        ),
    ),
    EarlierPr(
        number=5,
        url="https://github.com/acme/shop/pull/5",
        title="[SHOP-3] Tidy the toolbar",
        body="Moves buttons around.",
        author="octocat",
        merged_at="2026-09-25T10:00:00Z",
        remarks=(Remark(author="hubot", bot=False, body="The data team asked for this split.", url="e3"),),
    ),
]


def contents(sha: str, path: str) -> bytes | None:
    return CONTENTS.get((sha, path))


def written(tmp_path: Path, ticket: str | None = "SHOP-3", settings: Settings | None = None, limit: int = 300_000) -> dict[str, Path]:
    return write_inputs(PR, FILES, contents, EARLIER, settings or Settings(), ticket, tmp_path, limit=limit)


def everything_in(folder: Path) -> str:
    return "\n".join(path.read_text() for path in sorted(folder.rglob("*")) if path.is_file())


def test_every_witness_gets_its_own_folder(tmp_path: Path) -> None:
    manifest = written(tmp_path)

    assert sorted(manifest) == ["alignment", "claimed", "implementation", "primer", "requested", "tests", "why"]
    assert all(folder.parent == tmp_path for folder in manifest.values())


def test_a_named_work_dir_is_created_when_missing(tmp_path: Path) -> None:
    named = tmp_path / "summaries" / "7"

    assert work_dir(named) == named
    assert named.is_dir()


def test_a_named_work_dir_that_holds_anything_is_refused(tmp_path: Path) -> None:
    (tmp_path / "why").mkdir()
    (tmp_path / "why" / "output.json").write_text("{}")

    with pytest.raises(WorkDirNotEmpty):
        work_dir(tmp_path)


def test_each_witness_leaves_its_output_in_its_own_folder_of_the_work_dir(tmp_path: Path) -> None:
    named = work_dir(tmp_path / "work")

    def launch(witness: str, folder: Path) -> bool:
        (folder / "output.json").write_text("{}")
        return True

    run_witnesses(written(named), launch, lambda seconds: None)

    assert sorted(path.relative_to(named).as_posix() for path in named.glob("*/output.json")) == [
        "alignment/output.json",
        "claimed/output.json",
        "implementation/output.json",
        "primer/output.json",
        "requested/output.json",
        "tests/output.json",
        "why/output.json",
    ]


def test_implementation_sees_stripped_production_code_and_nothing_of_the_author(tmp_path: Path) -> None:
    seen = everything_in(written(tmp_path)["implementation"])

    assert "+    return ['export'] if flags.exports else []" in seen
    assert "+x = 2" in seen
    assert "hidden while exports" not in seen
    assert "test_hidden" not in seen
    assert "SHOP-3" not in seen
    assert "Hide the export button" not in seen
    assert "hide the button behind" not in seen
    assert "Export from the toolbar" not in seen
    assert "lock" not in seen


def test_primer_sees_production_code_with_its_comments_and_what_the_pull_request_says_it_is(tmp_path: Path) -> None:
    primer = written(tmp_path)["primer"]
    seen = everything_in(primer)

    assert "+    # hidden while exports are rewritten" in seen
    assert "# hidden while exports are rewritten" in (primer / "files" / "src" / "toolbar.py").read_text()
    assert "Hide the export button" in seen
    assert "Hides the button when exports are off." in seen
    assert (primer / "ticket.txt").read_text() == "SHOP-3\n"
    assert "test_hidden" not in seen


def test_code_witnesses_also_get_each_changed_file_whole_and_stripped(tmp_path: Path) -> None:
    manifest = written(tmp_path)

    toolbar = (manifest["implementation"] / "files" / "src" / "toolbar.py").read_text()
    test_file = (manifest["tests"] / "files" / "tests" / "test_toolbar.py").read_text()
    assert "return ['export'] if flags.exports else []" in toolbar
    assert "hidden while exports" not in toolbar
    assert "assert buttons(Off()) == []" in test_file
    assert "hides when exports are off" not in test_file
    assert not (manifest["implementation"] / "files" / "assets").exists()


def test_implementation_also_gets_the_unchanged_production_code_with_its_comments(tmp_path: Path) -> None:
    head = {
        "src/toolbar.py": "# hidden while exports are off\n",
        "src/flags.py": "# exports default to on\nexports = True\n",
        "tests/test_flags.py": "def test_flags(): ...\n",
        "docs/flags.md": "Flags\n",
        "web/yarn.lock": "lock\n",
    }

    def export(into: Path, keep: Callable[[str], bool]) -> None:
        for path, text in head.items():
            if keep(path):
                (into / path).parent.mkdir(parents=True, exist_ok=True)
                (into / path).write_text(text)

    write_surroundings(tmp_path, [ChangedFile("src/toolbar.py", None, "modified", 2)], Settings(), export)

    repo = tmp_path / "repo"
    assert [str(path.relative_to(repo)) for path in repo.rglob("*") if path.is_file()] == ["src/flags.py"]
    assert (repo / "src/flags.py").read_text() == head["src/flags.py"]


def test_a_renamed_file_diffs_against_its_previous_path(tmp_path: Path) -> None:
    seen = everything_in(written(tmp_path)["implementation"])

    assert "-x = 1" in seen


def test_a_renamed_file_names_its_old_path_and_a_pure_rename_still_shows(tmp_path: Path) -> None:
    moved = {(BASE, "src/old.py"): b"x = 1\n", (HEAD, "src/new.py"): b"x = 1\n"}

    def read(sha: str, path: str) -> bytes | None:
        return moved.get((sha, path))

    folder = write_inputs(PR, [ChangedFile("src/new.py", "src/old.py", "renamed", 0)], read, [], Settings(), None, tmp_path)["implementation"]

    assert (folder / "changes.diff").read_text() == "rename from src/old.py\nrename to src/new.py\n"


def test_the_diff_of_an_edited_rename_starts_from_the_old_path(tmp_path: Path) -> None:
    seen = everything_in(written(tmp_path)["implementation"])

    assert "--- a/src/old_name.py\n+++ b/src/new_name.py\n" in seen


def test_an_unreadable_file_such_as_a_submodule_is_skipped(tmp_path: Path) -> None:
    def read(sha: str, path: str) -> bytes | None:
        raise Unreadable(path)

    folder = write_inputs(PR, [ChangedFile("vendor/lib", None, "modified", 2)], read, [], Settings(), None, tmp_path)["implementation"]

    assert (folder / "skipped.txt").read_text() == "vendor/lib\n"
    assert not (folder / "changes.diff").exists()


def test_prose_folders_are_capped_too(tmp_path: Path) -> None:
    manifest = written(tmp_path, limit=60)

    for witness in ["claimed", "why"]:
        files = [path for path in manifest[witness].rglob("*") if path.is_file() and path.name != "truncated.txt"]
        assert sum(len(path.read_text()) for path in files) <= 60, witness
        assert (manifest[witness] / "truncated.txt").exists(), witness


def test_binary_files_are_skipped_and_named(tmp_path: Path) -> None:
    folder = written(tmp_path)["implementation"]

    assert (folder / "skipped.txt").read_text() == "assets/logo.png\n"


def test_tests_see_only_stripped_test_code(tmp_path: Path) -> None:
    seen = everything_in(written(tmp_path)["tests"])

    assert "+    assert buttons(Off()) == []" in seen
    assert "hides when exports are off" not in seen
    assert "flags.exports" not in seen


def test_claimed_gets_every_word_the_authors_wrote(tmp_path: Path) -> None:
    seen = everything_in(written(tmp_path)["claimed"])

    assert "Hide the export button" in seen
    assert "Hides the button when exports are off." in seen
    assert "Exports are being rewritten." in seen
    assert "hide the button behind the exports flag" in seen
    assert "# hidden while exports are rewritten" in seen
    assert '"""The button hides when exports are off."""' in seen
    assert "+Export from the toolbar when enabled." in seen
    assert "Which ticket covers" not in seen


def test_why_never_sees_the_authors_or_bots(tmp_path: Path) -> None:
    seen = everything_in(written(tmp_path)["why"])

    assert "Which ticket covers the rewrite?" in seen
    assert "Exports time out on large shops" in seen
    assert "Rewrite the exporter" in seen
    assert "Exports are being rewritten" not in seen
    assert "Hide the export button" not in seen
    assert "I will hide the button meanwhile" not in seen
    assert "Tidy the toolbar" not in seen
    assert "This PR hides" not in seen


def test_why_knows_who_the_authors_are_so_it_can_skip_them_elsewhere(tmp_path: Path) -> None:
    assert (written(tmp_path)["why"] / "authors.txt").read_text() == "Octo Cat\noctocat\n"


def test_an_earlier_pr_by_an_author_keeps_its_ticket_and_date_but_not_its_title(tmp_path: Path) -> None:
    seen = everything_in(written(tmp_path)["why"])

    assert "# #5 (https://github.com/acme/shop/pull/5): merged 2026-09-25, tickets SHOP-3" in seen
    assert "The data team asked for this split." in seen
    assert "# #3 Rewrite the exporter (https://github.com/acme/shop/pull/3): merged 2026-09-20" in seen


def test_an_earlier_pr_opened_by_a_bot_keeps_neither_title_nor_body(tmp_path: Path) -> None:
    by_bot = EarlierPr(
        number=9,
        url="https://github.com/acme/shop/pull/9",
        title="bump compress from 1.2 to 1.3",
        body="Release notes for compress.",
        author="dependabot",
        merged_at="2026-09-01T10:00:00Z",
        remarks=(Remark(author="monalisa", bot=False, body="Needed for the exporter.", url="e9"),),
        bot=True,
    )

    seen = everything_in(write_inputs(PR, FILES, contents, [by_bot], Settings(), "SHOP-3", tmp_path)["why"])

    assert "Needed for the exporter." in seen
    assert "bump compress" not in seen
    assert "Release notes" not in seen


def test_an_earlier_pr_body_loses_its_quoted_lines(tmp_path: Path) -> None:
    quoting = EarlierPr(
        number=8,
        url="https://github.com/acme/shop/pull/8",
        title="Split exports",
        body="> I will hide the button meanwhile.\nSplitting exports so they stop timing out.",
        author="monalisa",
        merged_at="2026-09-01T10:00:00Z",
        remarks=(),
    )

    seen = everything_in(write_inputs(PR, FILES, contents, [quoting], Settings(), "SHOP-3", tmp_path)["why"])

    assert "Splitting exports so they stop timing out." in seen
    assert "hide the button meanwhile" not in seen


def test_why_and_requested_get_the_ticket_key(tmp_path: Path) -> None:
    manifest = written(tmp_path, settings=Settings(why_guidance="Decisions live in the ENG space."))

    assert (manifest["requested"] / "ticket.txt").read_text() == "SHOP-3\n"
    assert (manifest["why"] / "ticket.txt").read_text() == "SHOP-3\n"
    assert (manifest["why"] / "guidance.md").read_text() == "Decisions live in the ENG space.\n"


def test_without_a_ticket_requested_has_no_folder_and_why_is_told(tmp_path: Path) -> None:
    manifest = written(tmp_path, ticket=None)

    assert "requested" not in manifest
    assert (manifest["why"] / "ticket.txt").read_text() == "No ticket found.\n"


def test_oversized_inputs_drop_the_largest_files_first(tmp_path: Path) -> None:
    folder = written(tmp_path, limit=150)["implementation"]

    assert (folder / "truncated.txt").read_text() == "src/toolbar.py\n"
    assert "+x = 2" in everything_in(folder)
