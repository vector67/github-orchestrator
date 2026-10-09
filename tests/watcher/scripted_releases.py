import json
from dataclasses import dataclass, field

LATEST = "https://api.github.com/repos/vector67/github-orchestrator/releases/latest"
ASSETS = "https://api.github.com/repos/vector67/github-orchestrator/releases/assets"


def tagged(version: str) -> str:
    return f"https://api.github.com/repos/vector67/github-orchestrator/releases/tags/v{version}"


def wheel_asset(version: str) -> str:
    return f"{ASSETS}/{sum(map(ord, version))}"


def release_body(version: str) -> bytes:
    return json.dumps({
        "tag_name": f"v{version}",
        "assets": [
            {"name": "install.sh", "url": f"{ASSETS}/1",
             "browser_download_url": "https://github.com/x/install.sh"},
            {"name": f"github_orchestrator-{version}-py3-none-any.whl",
             "url": wheel_asset(version),
             "browser_download_url": f"https://github.com/x/github_orchestrator-{version}.whl"},
        ],
    }).encode()


@dataclass(frozen=True)
class Asked:
    url: str
    accept: str
    token: str | None


@dataclass
class ScriptedReleasesApi:
    answers: dict[str, bytes | OSError] = field(default_factory=dict)
    asked: list[Asked] = field(default_factory=list)

    def publish(self, version: str, *, latest: bool = True) -> None:
        self.answers[tagged(version)] = release_body(version)
        self.answers[wheel_asset(version)] = f"wheel {version}".encode()
        if latest:
            self.answers[LATEST] = release_body(version)

    def __call__(self, url: str, accept: str, token: str | None) -> bytes:
        self.asked.append(Asked(url, accept, token))
        answer = self.answers.get(url, OSError(f"HTTP Error 404: Not Found ({url})"))
        if isinstance(answer, OSError):
            raise answer
        return answer
