from importlib.resources import as_file, files
from pathlib import Path

from github_orchestrator.desktop._command import (
    Run,
    command_output,
    run_desktop_command,
)
from github_orchestrator.desktop.interface import Badge

BADGE_APPS = {Badge.READY: "GHO Ready", Badge.FAILED: "GHO Failed",
              Badge.NEEDS_YOU: "GHO Needs You", Badge.INFO: "GHO Info",
              Badge.COMMENTS: "GHO Comments"}


class MacDesktop:
    def __init__(self, run: Run, apps: Path) -> None:
        self._run = run
        self._apps = apps

    def announce(self, badge: Badge, title: str, body: str, key: str,
                 link: str | None) -> str | None:
        app = self._apps / f"{BADGE_APPS[badge]}.app"
        if not app.exists():
            return None
        opens = [] if link is None else ["--open", link]
        return self._run_desktop_command(["open", "-n", "-g", str(app), "--args",
                                          "--title", title, "--body", body, "--id", key,
                                          *opens])

    def open_url(self, url: str) -> str | None:
        return self._run_desktop_command(["open", url])

    def notifications(self, path: str) -> tuple[str, str] | None:
        with as_file(files(__package__) / "notifier") as notifier:
            newest = max(source.stat().st_mtime for source in notifier.rglob("*")
                         if source.is_file())
            build = f"sh {notifier / 'build.sh'}"
        plists = [self._apps / f"{name}.app" / "Contents" / "Info.plist"
                  for name in BADGE_APPS.values()]
        if not all(plist.exists() for plist in plists):
            problem = (f"the notifier apps are not all in {self._apps}, so no desktop "
                       "notifications are shown")
        elif any(plist.stat().st_mtime < newest for plist in plists):
            problem = f"the notifier apps in {self._apps} are older than this version's sources"
        else:
            return None
        tools = command_output(self._run, ["xcode-select", "-p"]) or ""
        return problem, build if tools.strip() else f"xcode-select --install, then {build}"

    def _run_desktop_command(self, argv: list[str]) -> str | None:
        return run_desktop_command(self._run, argv,
                                   missing=f"{argv[0]} is not on PATH (macOS only)")
