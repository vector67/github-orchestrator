import json
import shutil
from pathlib import Path

from github_orchestrator.harvest._chrome import Run, handed_to_chrome

HARVEST_TIME_TRACKER = "fbpiglieekigmkeebmeohkelfpjjlaia"
BOARD_PROFILE = Path(__file__).with_name("board_profile.js")
PROFILE_PATH = "js/profiles/github-orchestrator.js"
STORE_ONLY = ("key", "update_url")


def _version(manifest: Path) -> tuple[int, ...]:
    return tuple(int(part) for part in manifest.parent.name.split("_")[0].split("."))


class CopiedExtension:
    def __init__(self, chrome_dir: Path, into: Path, hub_port: int, run: Run) -> None:
        self._chrome_dir = chrome_dir
        self._into = into
        self._hub_port = hub_port
        self._run = run

    def prepare(self) -> Path | str:
        installs = list(self._chrome_dir.glob(
            f"*/Extensions/{HARVEST_TIME_TRACKER}/*/manifest.json"))
        if not installs:
            return ("Chrome has no Harvest Time Tracker installed; add it from the "
                    "Chrome Web Store, then set it up again")
        newest = max(installs, key=_version).parent
        shutil.rmtree(self._into, ignore_errors=True)
        shutil.copytree(newest, self._into, ignore=shutil.ignore_patterns("_metadata"))
        shutil.copyfile(BOARD_PROFILE, self._into / PROFILE_PATH)
        self._write_manifest()
        handed_to_chrome(self._into, self._run)
        return self._into

    def _write_manifest(self) -> None:
        path = self._into / "manifest.json"
        manifest = {key: value for key, value in json.loads(path.read_text()).items()
                    if key not in STORE_ONLY}
        manifest["content_scripts"] = [*manifest.get("content_scripts", []), {
            "matches": [f"http://127.0.0.1:{self._hub_port}/*",
                        f"http://localhost:{self._hub_port}/*"],
            "js": [PROFILE_PATH, "js/platform.js"]}]
        path.write_text(json.dumps(manifest, indent=2))
