from github_orchestrator.desktop.interface import Announcement as Announcement
from github_orchestrator.desktop.interface import Badge


def _missing(program: str) -> str:
    return f"{program} is not on PATH (macOS only)"


class FakeDesktop:
    def __init__(self, *, macos: bool = True, notifier_apps: bool = True) -> None:
        self.macos = macos
        self.notifier_apps = notifier_apps
        self.announcements: list[Announcement] = []
        self.opened: list[str] = []

    def announce(self, badge: Badge, title: str, body: str, key: str,
                 link: str | None) -> str | None:
        if self.macos and self.notifier_apps:
            self.announcements.append(Announcement(badge, title, body, key, link))
        return None

    def open_url(self, url: str) -> str | None:
        if not self.macos:
            return _missing("open")
        self.opened.append(url)
        return None

    def notifications(self, path: str) -> tuple[str, str] | None:
        if self.notifier_apps:
            return None
        return "the notifier apps are missing", "sh build.sh"
