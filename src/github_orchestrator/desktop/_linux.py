import shutil

from github_orchestrator.desktop._command import Run, run_desktop_command
from github_orchestrator.desktop.interface import Badge


def _missing(program: str) -> str:
    return f"{program} is not on PATH"


class LinuxDesktop:
    def __init__(self, run: Run) -> None:
        self._run = run

    def announce(self, badge: Badge, title: str, body: str, key: str,
                 link: str | None) -> str | None:
        return run_desktop_command(
            self._run, ["notify-send", "--app-name", "github-orchestrator", title, body],
            missing=None)

    def open_url(self, url: str) -> str | None:
        return run_desktop_command(self._run, ["xdg-open", url], missing=_missing("xdg-open"))

    def notifications(self, path: str) -> tuple[str, str] | None:
        if shutil.which("notify-send", path=path) is not None:
            return None
        return (f"notify-send is not on the watcher's PATH ({path}), so no desktop notifications "
                "are shown",
                "install notify-send: libnotify-bin on Debian and Ubuntu, libnotify on Fedora "
                "and Arch")
