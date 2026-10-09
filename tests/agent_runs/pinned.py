import os
from pathlib import Path

PINNED = Path(__file__).parent / "pinned"
PYTHON = Path("/tools/github-orchestrator/bin/python")


def assert_pinned(name: str, text: str) -> None:
    said = text.replace(str(PYTHON), "<python>")
    path = PINNED / f"{name}.txt"
    if os.environ.get("REPIN_PROMPTS") == "1":
        path.write_text(said)
    assert said == path.read_text()
