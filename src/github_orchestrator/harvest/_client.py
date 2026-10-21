import json
import logging
import subprocess
import urllib.request
from collections.abc import Callable
from datetime import date
from typing import Any

from github_orchestrator.harvest._keychain import KEYCHAIN_SERVICE

log = logging.getLogger(__name__)

API = "https://api.harvestapp.com/v2"
TIMEOUT = 20
USER_AGENT = "github-orchestrator (https://github.com/vector67/github-orchestrator)"

Send = Callable[[urllib.request.Request], bytes]


class Refused(Exception):
    pass


def sent(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        answer: bytes = response.read()
    return answer


class HarvestTimesheet:
    def __init__(self, account_id: int, token: Callable[[], str], send: Send,
                 today: Callable[[], date]) -> None:
        self._account_id = account_id
        self._token = token
        self._send = send
        self._today = today

    def running(self, project_id: int, task_id: int) -> bool | None:
        try:
            return self._running_entry(project_id, task_id) is not None
        except Refused as refused:
            log.warning("%s", refused)
            return None

    def start(self, project_id: int, task_id: int) -> str | None:
        try:
            self._call("POST", "/time_entries", {
                "project_id": project_id, "task_id": task_id,
                "spent_date": self._today().isoformat()})
        except Refused as refused:
            return str(refused)
        return None

    def stop(self, project_id: int, task_id: int) -> str | None:
        try:
            entry = self._running_entry(project_id, task_id)
            if entry is not None:
                self._call("PATCH", f"/time_entries/{entry}/stop")
        except Refused as refused:
            return str(refused)
        return None

    def _running_entry(self, project_id: int, task_id: int) -> int | None:
        me = self._call("GET", "/users/me")["id"]
        entries = self._call("GET", f"/time_entries?is_running=true&user_id={me}")["time_entries"]
        return next((entry["id"] for entry in entries
                     if entry["project"]["id"] == project_id and entry["task"]["id"] == task_id),
                    None)

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        try:
            token = self._token()
        except (OSError, subprocess.SubprocessError) as exc:
            raise Refused(f"no Harvest token in the keychain item {KEYCHAIN_SERVICE}: {exc}") from exc
        request = urllib.request.Request(
            f"{API}{path}", method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {token}",
                     "Harvest-Account-Id": str(self._account_id),
                     "User-Agent": USER_AGENT, "Content-Type": "application/json"})
        try:
            return json.loads(self._send(request))
        except (OSError, ValueError) as exc:
            raise Refused(f"Harvest refused {method} {path}: {exc}") from exc
