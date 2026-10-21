import json
import typing
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from email.message import Message
from typing import Any

ME = 42
TOKEN = "pat-secret"
ACCOUNT = 900


@dataclass
class Entry:
    id: int
    user_id: int
    project_id: int
    task_id: int
    spent_date: str
    is_running: bool = True


@dataclass
class ScriptedHarvest:
    entries: list[Entry] = field(default_factory=list)
    refusing: int | None = None
    sent: list[urllib.request.Request] = field(default_factory=list)

    def __call__(self, request: urllib.request.Request) -> bytes:
        self.sent.append(request)
        if self.refusing is not None:
            raise urllib.error.HTTPError(request.full_url, self.refusing, "Unauthorized",
                                         Message(), None)
        assert request.get_header("Authorization") == f"Bearer {TOKEN}"
        assert request.get_header("Harvest-account-id") == str(ACCOUNT)
        assert request.get_header("User-agent")
        address = urllib.parse.urlsplit(request.full_url)
        assert address.netloc == "api.harvestapp.com"
        return json.dumps(self._answer(request.get_method(), address.path.removeprefix("/v2"),
                                       urllib.parse.parse_qs(address.query),
                                       json.loads(typing.cast(bytes, request.data)) if request.data else {})).encode()

    def _answer(self, method: str, path: str, query: dict[str, list[str]],
                body: dict[str, Any]) -> object:
        if (method, path) == ("GET", "/users/me"):
            return {"id": ME}
        if (method, path) == ("GET", "/time_entries"):
            return {"time_entries": [self._shown(entry) for entry in self.entries
                                     if entry.is_running == (query["is_running"] == ["true"])
                                     and entry.user_id == int(query["user_id"][0])]}
        if (method, path) == ("POST", "/time_entries"):
            for entry in self.entries:
                if entry.user_id == ME:
                    entry.is_running = False
            started = Entry(len(self.entries) + 1, ME, body["project_id"], body["task_id"],
                            body["spent_date"])
            self.entries.append(started)
            return self._shown(started)
        if method == "PATCH" and path.endswith("/stop"):
            stopped = next(entry for entry in self.entries
                           if path == f"/time_entries/{entry.id}/stop")
            stopped.is_running = False
            return self._shown(stopped)
        raise AssertionError(f"Harvest's stand-in does not know {method} {path}")

    def _shown(self, entry: Entry) -> dict[str, Any]:
        return {"id": entry.id, "user": {"id": entry.user_id},
                "project": {"id": entry.project_id}, "task": {"id": entry.task_id},
                "spent_date": entry.spent_date, "is_running": entry.is_running}

    def running(self) -> list[tuple[int, int]]:
        return [(entry.project_id, entry.task_id) for entry in self.entries if entry.is_running]
