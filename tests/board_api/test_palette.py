import re

import pytest

from tests.board_api.support import client_for, css_variables
from tests.contrast import contrast_ratio, relative_luminance

HEX = re.compile(r"^#[0-9a-f]{6}$")

BLACK = "#000000"
WHITE = "#ffffff"
GREY_TINT = "#f4f4f4"

TRANSLUCENT = {"--scrim"}


def over(primary: str, alpha: float, ground: str) -> str:
    def channel(colour, at):
        return int(colour[at:at + 2], 16)

    return "#" + "".join(
        f"{int(alpha * channel(primary, at) + (1 - alpha) * channel(ground, at) + 0.5):02x}"
        for at in (1, 3, 5))


@pytest.fixture
def bound():
    return css_variables(client_for().get("/palette.css").text)


def _neutral(colour):
    return len({colour[1:3], colour[3:5], colour[5:7]}) == 1


CHROME = ("--page", "--card", "--text", "--muted", "--hairline", "--border-strong",
          "--grey", "--grey-fill", "--selected", "--range-highlight", "--diff-ground",
          "--diff-text", "--diff-file", "--diff-expander", "--diff-expander-num",
          "--diff-line-number", "--diff-hunk-text")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_chrome_of_both_modes_is_drawn_from_black_and_white(bound, theme):
    tinted = {name: bound[theme][name] for name in CHROME if not _neutral(bound[theme][name])}

    assert tinted == {}, (
        f"{theme} tints {tinted}; the board is black type on white, and dark is "
        "that system turned over, not another product's canvas")


def test_light_stays_black_on_white(bound):
    light = bound["light"]

    assert (light["--text"], light["--page"]) == (BLACK, WHITE)
    assert (light["--card"], light["--diff-ground"]) == (WHITE, WHITE)
    assert light["--grey-fill"] == GREY_TINT


def test_dark_turns_the_light_system_over(bound):
    light, dark = bound["light"], bound["dark"]

    assert relative_luminance(dark["--page"]) < relative_luminance(dark["--text"])
    assert dark["--diff-ground"] == dark["--page"]
    for name in ("--yellow", "--green"):
        assert dark[name] == light[name], (
            "a fill keeps its hue across both modes")


def test_a_dialog_lifts_off_the_page_it_dims_in_dark(bound):
    dark = bound["dark"]
    alpha = float(dark["--scrim"].rpartition(",")[2].rstrip(") "))
    dimmed = over(BLACK, alpha, dark["--page"])

    assert contrast_ratio(dark["--card"], dimmed) >= 1.3, (
        "a dialog on the same ground as the page it veils reads as one more "
        "panel, not as the thing on top")


def test_dark_rules_recede_behind_the_type(bound):
    dark = bound["dark"]
    rule = contrast_ratio(dark["--border-strong"], dark["--page"])

    assert rule < contrast_ratio(dark["--text"], dark["--page"]) - 4, (
        "a 2px rule painted in the type's own colour is the brightest line on "
        "a dark page")
    assert rule >= 3, "and it still marks a region"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_focus_ring_stands_off_the_page(bound, theme):
    named = bound[theme]

    assert contrast_ratio(named["--blue"], named["--page"]) >= 3.5


def test_both_modes_keep_the_expander_row_the_file_headers_grey(bound):
    for theme in ("light", "dark"):
        values = bound[theme]
        assert (values["--diff-expander"], values["--diff-expander-num"]) == (
            values["--diff-file"], values["--diff-file"])


def test_every_colour_a_palette_names_is_a_six_digit_hex(bound):
    for theme, values in bound.items():
        for name, value in values.items():
            if name in TRANSLUCENT:
                continue
            assert HEX.match(value), (
                f"{theme} {name} is {value!r}; the page's CSS "
                f"variables are all #rrggbb"
            )
