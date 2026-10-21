import csv
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from github_orchestrator.domain import UtcClock
from github_orchestrator.github._gh_cli import Run

COLUMNS = ("at", "account", "method", "url", "exit", "status", "bytes", "retry_after",
           "ratelimit_limit", "ratelimit_remaining", "ratelimit_reset",
           "ratelimit_resource", "ratelimit_used")

_KEPT_ON_403 = {"retry-after": "retry_after",
                **{f"x-ratelimit-{name}": f"ratelimit_{name}"
                   for name in ("limit", "remaining", "reset", "resource", "used")}}


@dataclass
class _Request:
    url: str = ""
    method: str = ""
    status: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: list[str] = field(default_factory=list)
    in_body: bool = False

    def row(self) -> dict[str, str]:
        kept = ({column: self.headers.get(header, "") for header, column in _KEPT_ON_403.items()}
                if self.status == "403" else {})
        size = str(len("\n".join(self.body).strip().encode())) if self.status else ""
        return {"method": self.method, "url": self.url, "status": self.status,
                "bytes": size, **kept}


def _split(stderr: str) -> tuple[list[_Request], str]:
    requests: list[_Request] = []
    own: list[str] = []
    request: _Request | None = None
    for line in stderr.splitlines(keepends=True):
        text = line.rstrip("\n")
        if text.startswith("* Request at "):
            request = _Request()
        elif request is None:
            own.append(line)
        elif text.startswith("* Request took "):
            requests.append(request)
            request = None
        elif request.in_body:
            request.body.append(text)
        elif text.startswith("* Request to "):
            request.url = text.removeprefix("* Request to ")
        elif text.startswith("> ") and not request.method:
            request.method = text[2:].split(" ", 1)[0]
        elif text.startswith("< HTTP/"):
            request.status = text.split(" ")[2]
        elif text.startswith("< "):
            name, _, value = text[2:].partition(":")
            request.headers[name.strip().lower()] = value.strip()
        elif not text and request.status:
            request.in_body = True
    return requests, "".join(own)


class Traffic:
    def __init__(self, path: Path, clock: UtcClock) -> None:
        self._path = path
        self._clock = clock

    def traced(self, run: Run, account: str) -> Run:
        def traced_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            env = kwargs.pop("env", None)
            kwargs["env"] = {**(os.environ if env is None else env), "GH_DEBUG": "api"}
            try:
                result = run(cmd, **kwargs)
            except subprocess.CalledProcessError as exc:
                exc.stderr = self._record(account, exc.returncode, exc.stderr or "")
                raise
            result.stderr = self._record(account, result.returncode, result.stderr)
            return result
        return traced_run

    def _record(self, account: str, returncode: int, stderr: str) -> str:
        requests, own = _split(stderr)
        if requests:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", newline="") as file:
                writer = csv.DictWriter(file, COLUMNS, restval="")
                if file.tell() == 0:
                    writer.writeheader()
                at = self._clock().isoformat()
                writer.writerows({"at": at, "account": account, "exit": str(returncode),
                                  **request.row()} for request in requests)
        return own
