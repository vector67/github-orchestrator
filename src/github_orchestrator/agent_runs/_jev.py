import json
import logging
import subprocess
import urllib.request
from collections.abc import Callable, Mapping

log = logging.getLogger(__name__)

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-1.13.0"
JEV_TIMEOUT = 60
KEYCHAIN_SERVICE = "typesafe-api"
QUESTION = "verdict"

Ask = Callable[[bytes], bytes]


def post_to_jev(body: bytes) -> bytes:
    key = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                         capture_output=True, text=True, check=True).stdout.strip()
    request = urllib.request.Request(JEV_URL, data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=JEV_TIMEOUT) as response:
        answer: bytes = response.read()
    return answer


def choose(ask: Ask, state: str, instructions: str, options: Mapping[str, str]) -> str | None:
    body = json.dumps({"state": state, "model": JEV_MODEL, "questions": {QUESTION: {
        "type": "choice", "instructions": instructions, "criteria": dict(options)}}}).encode()
    try:
        choice = json.loads(ask(body))["answers"][QUESTION]["choice"]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        log.warning("Jev gave no verdict: %s", exc)
        return None
    return choice if isinstance(choice, str) and choice in options else None
