import json
from pathlib import Path

from github_orchestrator.atomic_write import write_atomically

LAYOUT = 1


def layout_of(marker: Path) -> int:
    try:
        layout = json.loads(marker.read_text()).get("layout")
    except (OSError, ValueError, AttributeError):
        return 0
    return layout if isinstance(layout, int) else 0


def write_marker(marker: Path, version: str | None) -> None:
    write_atomically(marker,
                     (json.dumps({"layout": LAYOUT, "written_by": version}) + "\n").encode())
