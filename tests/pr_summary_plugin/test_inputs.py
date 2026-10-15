from pathlib import Path

from pr_summary.inputs import ChangedFile, EarlierPr, write_inputs
from pr_summary.pull_request import PullRequest, Remark
from pr_summary.settings import Settings

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
    commit_messages=("hide the button behind the exports flag",),
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
        remarks=(
            Remark(author="hubot", bot=False, body="Exports time out on large shops; the button must go until this lands.", url="e1"),
            Remark(author="octocat", bot=False, body="I will hide the button meanwhile.", url="e2"),
        ),
    ),
    EarlierPr(number=5, url="https://github.com/acme/shop/pull/5", title="Tidy the toolbar", body="Moves buttons around.", author="octocat", remarks=()),
]


def contents(sha: str, path: str) -> bytes | None:
    return CONTENTS.get((sha, path))


def written(tmp_path: Path, ticket: str | None = "SHOP-3", settings: Settings | None = None, limit: int = 300_000) -> dict[str, Path]:
    return write_inputs(PR, FILES, contents, EARLIER, settings or Settings(), ticket, tmp_path, limit=limit)


def everything_in(folder: Path) -> str:
    return "\n".join(path.read_text() for path in sorted(folder.rglob("*")) if path.is_file())


def test_every_witness_gets_its_own_folder(tmp_path: Path) -> None:
    manifest = written(tmp_path)

    assert sorted(manifest) == ["alignment", "claimed", "implementation", "requested", "tests", "why"]
    assert all(folder.parent == tmp_path for folder in manifest.values())


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


def test_a_renamed_file_diffs_against_its_previous_path(tmp_path: Path) -> None:
    seen = everything_in(written(tmp_path)["implementation"])

    assert "-x = 1" in seen


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
