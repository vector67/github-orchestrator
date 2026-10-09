import os
import sys
from collections.abc import Mapping

from github_orchestrator.cli._config import Run
from github_orchestrator.cli._hub import HealthBody, HubHealth
from github_orchestrator.cli._service import Service
from github_orchestrator.desktop import Desktop
from github_orchestrator.domain import Sleep

HUB_ATTEMPTS = 30
HUB_POLL_SECONDS = 1.0


def await_hub(hub_url: str, hub_health: HubHealth, sleep: Sleep) -> HealthBody:
    for attempt in range(HUB_ATTEMPTS):
        answer = hub_health(hub_url)
        if answer is not None:
            return answer
        if attempt < HUB_ATTEMPTS - 1:
            sleep(HUB_POLL_SECONDS)
    print(f"The watcher started, but its hub at {hub_url} did not answer within "
          f"{HUB_ATTEMPTS}s. github-orchestrator logs shows why.")
    sys.exit(1)


def start(service: Service, hub_url: str, hub_health: HubHealth, sleep: Sleep) -> None:
    if service.running():
        print(f"The watcher is already running. Hub: {hub_url}")
        return
    service.start()
    print(f"Started the watcher. {hub_line(hub_url, await_hub(hub_url, hub_health, sleep))}")


def hub_line(hub_url: str, answer: HealthBody) -> str:
    return f"Hub: {hub_url} ({answer.get('state', 'state unknown')})"


def open_board(service: Service, hub_url: str, hub_health: HubHealth, sleep: Sleep,
               desktop: Desktop, *, graphical: bool, page: str = "") -> None:
    if service.running():
        await_hub(hub_url, hub_health, sleep)
    else:
        start(service, hub_url, hub_health, sleep)
    url = f"{hub_url}{page}"
    if graphical:
        print(f"Opening {url}", flush=True)
        desktop.open_url(url)
    print(f"If your browser didn't open, go to {url}")


def start_in_foreground(run: Run, python: str, environment: Mapping[str, str]) -> None:
    try:
        watcher = run([python, "-m", "github_orchestrator.watcher", "--loop"],
                      env={**os.environ, **environment})
    except KeyboardInterrupt:
        return
    sys.exit(watcher.returncode)
