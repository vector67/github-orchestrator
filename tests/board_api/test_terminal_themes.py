import re
from pathlib import Path

from tests.board_api.support import THE_ROOT, client_for

LISTED = (Path(__file__).parents[2] / "frontend" / "app" / "data" / "terminal-themes.ts")

SLOTS = ("ground", "text", "cursor", "selection")


def listed_keys() -> list[str]:
    return re.findall(r"key: '([a-z-]+)'", LISTED.read_text())


def test_every_theme_the_dialog_lists_is_served_with_its_colours():
    keys = listed_keys()
    served = client_for().get(f"{THE_ROOT}/palette.css").text

    missing = [
        f"--tty-{key}-{slot}"
        for key in keys
        for slot in SLOTS
        if f"--tty-{key}-{slot}:" not in served
    ]

    assert keys, "the dialog lists no themes"
    assert missing == [], f"the dialog lists themes palette.css does not colour: {missing}"


def test_every_theme_palette_css_colours_is_listed_in_the_dialog():
    served = client_for().get(f"{THE_ROOT}/palette.css").text
    coloured = set(re.findall(r"--tty-([a-z-]+)-selection:", served))

    unlisted = sorted(coloured - set(listed_keys()))

    assert coloured, "palette.css colours no themes"
    assert unlisted == [], f"palette.css colours themes the dialog never offers: {unlisted}"
