import json
import logging
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from github_orchestrator.domain import UtcClock
from github_orchestrator.watcher.interface import Release

log = logging.getLogger(__name__)

API = "https://api.github.com/repos/vector67/github-orchestrator/releases"
JSON = "application/vnd.github+json"
BINARY = "application/octet-stream"
CHECK_EVERY = timedelta(hours=24)
RETRY_AFTER = timedelta(hours=1)
ASK_SECONDS = 10.0

Get = Callable[[str, str, str | None], bytes]


@dataclass(frozen=True)
class ReleasesApi:
    get: Get


def http_get(url: str, accept: str, token: str | None) -> bytes:
    request = urllib.request.Request(url, headers={
        "Accept": accept, "User-Agent": "github-orchestrator",
        "X-GitHub-Api-Version": "2022-11-28"})
    if token:
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=ASK_SECONDS) as answer:
        body: bytes = answer.read()
    return body


def _release(body: bytes) -> Release:
    data = json.loads(body)
    version = str(data["tag_name"]).removeprefix("v")
    wheels = [asset["url"] for asset in data.get("assets", [])
              if str(asset.get("name", "")).endswith(".whl")]
    return Release(version, wheels[0] if wheels else None, None)


class GitHubReleases:
    def __init__(self, get: Get, record: Path, clock: UtcClock, *, enabled: bool,
                 token: str | None) -> None:
        self._get = get
        self._record = record
        self._clock = clock
        self._enabled = enabled
        self._token = token
        self._failed_at: datetime | None = None

    def recorded(self) -> Release | None:
        if not self._enabled:
            return None
        try:
            data = json.loads(self._record.read_text())
            return Release(str(data["version"]), data.get("wheel"),
                           datetime.fromisoformat(data["checked_at"]))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def check_if_due(self) -> None:
        if not self._enabled:
            return
        now = self._clock()
        last = self.recorded()
        if last is not None and last.checked_at is not None and now - last.checked_at < CHECK_EVERY:
            return
        if self._failed_at is not None and now - self._failed_at < RETRY_AFTER:
            return
        found = self.look_up(None)
        if isinstance(found, str):
            log.warning("the daily release check failed; keeping the last answer: %s", found)
            self._failed_at = now
            return
        self._record.parent.mkdir(parents=True, exist_ok=True)
        self._record.write_text(json.dumps({"version": found.version, "wheel": found.wheel,
                                            "checked_at": now.isoformat()}))

    def look_up(self, version: str | None) -> Release | str:
        url = f"{API}/latest" if version is None else f"{API}/tags/v{version.removeprefix('v')}"
        named = "the newest release" if version is None else f"release {version}"
        try:
            return _release(self._get(url, JSON, self._token))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return f"could not look up {named} at {url}: {exc}"

    def download(self, release: Release, into: Path) -> Path | str:
        if release.wheel is None:
            return f"release {release.version} has no wheel to install"
        saved = into / f"github_orchestrator-{release.version}-py3-none-any.whl"
        try:
            saved.write_bytes(self._get(release.wheel, BINARY, self._token))
        except OSError as exc:
            return f"could not download {release.wheel}: {exc}"
        return saved
