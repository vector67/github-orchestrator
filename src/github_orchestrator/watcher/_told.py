import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path

from github_orchestrator.board_api.interface import NOTHING_HELD, Held
from github_orchestrator.domain import HubState, Pr, Repo
from github_orchestrator.pr_processes import ManagerPane

log = logging.getLogger(__name__)

WriteWhole = Callable[[Path, bytes], None]


class ToldFiles:
    def __init__(self, data_dir: Path, write_whole: WriteWhole) -> None:
        self._held = data_dir / "held.json"
        self._state = data_dir / "hub_state"
        self._write_whole = write_whole

    def begin(self, state: HubState) -> None:
        self._write(self._state, state.value.encode())
        self._write(self._held, json.dumps({"told": False, "held": []}).encode())

    def show(self, managers: Mapping[Pr, ManagerPane]) -> None:
        held = [{"repo": str(pr.repo), "number": pr.number, "manager": pane.value}
                for pr, pane in managers.items()]
        self._write(self._held, json.dumps({"told": True, "held": held}).encode())

    def held(self) -> Held:
        try:
            content = self._held.read_bytes()
        except FileNotFoundError:
            return NOTHING_HELD
        except OSError as error:
            log.warning("could not read the held list %s: %s", self._held, error)
            return NOTHING_HELD
        try:
            document = json.loads(content)
            return Held(told=bool(document["told"]), managers={
                Pr(Repo.parse(one["repo"]), int(one["number"])): str(one["manager"])
                for one in document["held"]})
        except (ValueError, KeyError, TypeError) as error:
            log.warning("could not read the held list %s: %s", self._held, error)
            return NOTHING_HELD

    def state(self) -> HubState | None:
        try:
            return HubState(self._state.read_text().strip())
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            log.warning("could not read the hub state %s: %s", self._state, error)
            return None

    def _write(self, path: Path, content: bytes) -> None:
        try:
            self._write_whole(path, content)
        except OSError as error:
            log.warning("could not write %s: %s", path, error)
