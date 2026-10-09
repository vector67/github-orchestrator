import tempfile
from pathlib import Path

from github_orchestrator.desktop import Desktop
from github_orchestrator.desktop.fake import FakeDesktop
from github_orchestrator.wiring import DesktopWiring, wire
from tests.desktop.scripted_mac import BADGE_APPS, ScriptedMac

NOTIFIER_APPS = Path(tempfile.mkdtemp(prefix="notifier-apps-"))
for _name in BADGE_APPS:
    (NOTIFIER_APPS / _name).mkdir()


def real_desktop(world: FakeDesktop | None = None, mac: ScriptedMac | None = None, *,
                 apps: Path = NOTIFIER_APPS) -> Desktop:
    run = mac if mac is not None else ScriptedMac(world)
    desktop: Desktop = wire(DesktopWiring(run, apps, platform="darwin")).get(Desktop)
    return desktop
