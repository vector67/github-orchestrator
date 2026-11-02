import json
import os
from pathlib import Path

LAYOUT = 1


def layout_of(marker: Path) -> int:
    try:
        layout = json.loads(marker.read_text()).get("layout")
    except (OSError, ValueError, AttributeError):
        return 0
    return layout if isinstance(layout, int) else 0


def write_marker(marker: Path, version: str | None) -> None:
    written = marker.with_name(f".{marker.name}.{os.getpid()}")
    written.write_text(json.dumps({"layout": LAYOUT, "written_by": version}) + "\n")
    os.replace(written, marker)
