import re
from pathlib import Path

from tests.board_api.support import THE_ROOT, client_for

LISTED = (Path(__file__).parents[2] / "frontend" / "app" / "data" / "terminal-themes.ts")

SLOTS = ("ground", "text", "cursor", "selection")


def test_every_theme_the_dialog_lists_is_served_with_its_colours():
    keys = re.findall(r"key: '([a-z-]+)'", LISTED.read_text())
    served = client_for().get(f"{THE_ROOT}/palette.css").text

    missing = [
        f"--tty-{key}-{slot}"
        for key in keys
        for slot in SLOTS
        if f"--tty-{key}-{slot}:" not in served
    ]

    assert keys, "the dialog lists no themes"
    assert missing == [], f"the dialog lists themes palette.css does not colour: {missing}"
