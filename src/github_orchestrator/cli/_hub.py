import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping

HealthBody = Mapping[str, object]
HubHealth = Callable[[str], HealthBody | None]

PROBE_SECONDS = 1.0


def hub_health(hub_url: str) -> HealthBody | None:
    try:
        with urllib.request.urlopen(f"{hub_url}/api/health", timeout=PROBE_SECONDS) as answer:
            if answer.status != 200:
                return None
            body = json.load(answer)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return body if isinstance(body, dict) else None
