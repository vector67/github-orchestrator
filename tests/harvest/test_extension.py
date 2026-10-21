import json
import subprocess
from pathlib import Path
from typing import Any

from github_orchestrator.harvest import BoardExtension
from github_orchestrator.wiring import HarvestWiring, wire

HARVEST = "fbpiglieekigmkeebmeohkelfpjjlaia"
HUB_PORT = 8720


def installed(chrome: Path, version: str, profile: str = "Default") -> Path:
    folder = chrome / profile / "Extensions" / HARVEST / f"{version}_0"
    (folder / "js" / "profiles").mkdir(parents=True)
    (folder / "_metadata").mkdir()
    (folder / "_metadata" / "verified_contents.json").write_text("[]")
    (folder / "js" / "platform.js").write_text(f"// platform {version}\n")
    (folder / "js" / "profiles" / "github.js").write_text("// github\n")
    (folder / "manifest.json").write_text(json.dumps({
        "name": "Harvest Time Tracker", "version": version, "key": "MIGf",
        "update_url": "https://clients2.google.com/service/update2/crx",
        "content_scripts": [{"matches": ["https://github.com/*"],
                             "js": ["js/profiles/github.js", "js/platform.js"]}],
    }))
    return folder


class Ran:
    def __init__(self) -> None:
        self.argv: list[list[str]] = []
        self.input: list[str | None] = []

    def __call__(self, argv: list[str], *, input: str | None = None,
                 **_: Any) -> subprocess.CompletedProcess[str]:
        self.argv.append(argv)
        self.input.append(input)
        return subprocess.CompletedProcess(argv, 0, "", "")


def extension(tmp_path: Path, ran: Ran | None = None) -> BoardExtension:
    board: BoardExtension = wire(HarvestWiring(
        tmp_path / "Chrome", tmp_path / "data" / "harvest-extension", HUB_PORT,
        ran or Ran())).get(BoardExtension)
    return board


def manifest(folder: Path) -> Any:
    return json.loads((folder / "manifest.json").read_text())


def test_the_newest_installed_extension_is_copied_with_the_board_s_profile_added(tmp_path):
    installed(tmp_path / "Chrome", "4.1.38")
    installed(tmp_path / "Chrome", "4.1.39", profile="Profile 1")

    folder = extension(tmp_path).prepare()

    assert folder == tmp_path / "data" / "harvest-extension"
    assert isinstance(folder, Path)
    assert (folder / "js" / "platform.js").read_text() == "// platform 4.1.39\n"
    assert (folder / "js" / "profiles" / "github-orchestrator.js").exists()
    assert manifest(folder)["content_scripts"] == [
        {"matches": ["https://github.com/*"], "js": ["js/profiles/github.js", "js/platform.js"]},
        {"matches": [f"http://127.0.0.1:{HUB_PORT}/*", f"http://localhost:{HUB_PORT}/*"],
         "js": ["js/profiles/github-orchestrator.js", "js/platform.js"]},
    ]


def test_the_copy_drops_what_ties_it_to_the_store(tmp_path):
    installed(tmp_path / "Chrome", "4.1.39")

    folder = extension(tmp_path).prepare()

    assert isinstance(folder, Path)
    assert not (folder / "_metadata").exists()
    assert "key" not in manifest(folder)
    assert "update_url" not in manifest(folder)


def test_preparing_again_replaces_the_earlier_copy(tmp_path):
    installed(tmp_path / "Chrome", "4.1.39")
    first = extension(tmp_path).prepare()
    assert isinstance(first, Path)
    (first / "stale.js").write_text("")

    again = extension(tmp_path).prepare()

    assert again == first
    assert not (first / "stale.js").exists()
    assert len(manifest(first)["content_scripts"]) == 2


def test_the_copy_is_opened_for_loading_in_chrome(tmp_path):
    installed(tmp_path / "Chrome", "4.1.39")
    ran = Ran()

    folder = extension(tmp_path, ran).prepare()

    assert ran.argv == [["open", "-a", "Google Chrome", "chrome://extensions/"],
                        ["open", "-R", str(folder)],
                        ["pbcopy"]]
    assert ran.input[-1] == str(folder)


def test_chrome_without_the_extension_is_told_to_install_it_first(tmp_path):
    ran = Ran()

    said = extension(tmp_path, ran).prepare()

    assert isinstance(said, str)
    assert "Chrome Web Store" in said
    assert ran.argv == []
    assert not (tmp_path / "data" / "harvest-extension").exists()
