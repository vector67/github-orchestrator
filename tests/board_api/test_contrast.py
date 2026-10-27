import re
from pathlib import Path

from tests.board_api.support import THE_ROOT, client_for, css_variables
from tests.contrast import WCAG_AA_NORMAL_TEXT, WCAG_NON_TEXT, contrast_ratio

APP_CSS = (Path(__file__).parents[2] / "frontend" / "app" / "styles" / "app.css")

TYPE_ON_GROUND = (
    ("the board's own type", "--text", "--page"),
    ("type on the selected row", "--text", "--selected"),
    ("muted type", "--muted", "--page"),
    ("the lines a pull request adds", "--green-text", "--page"),
    ("the lines a pull request removes", "--red-text", "--page"),
    ("muted type on the selected row", "--muted", "--selected"),
    ("muted type on a reopened selected row", "--muted", "--grey-fill"),
    ("the action bar's primary button", "--page", "--text"),
    ("type on a pushed banner", "--text", "--green-fill"),
    ("type on a queued banner", "--text", "--grey-fill"),
    ("type on a rework banner", "--text", "--blue-fill"),
    ("type on a card that wants you", "--yellow-text", "--yellow"),
    ("muted type on a card that wants you", "--yellow-muted", "--yellow"),
    ("the detailed reviewer flag", "--yellow", "--flag"),
    ("type on a frozen action band", "--text", "--red-fill"),
    ("muted type on a frozen action band", "--muted", "--red-fill"),
    ("type on a ready card", "--ready-text", "--ready-ground"),
    ("muted type on a ready card", "--ready-muted", "--ready-ground"),
    ("a dialog's type", "--text", "--card"),
    ("muted type in a dialog", "--muted", "--card"),
    ("a link in a comment", "--link", "--card"),
    ("a link in a reply", "--link", "--grey-fill"),
    ("code in a comment", "--text", "--hairline"),
    ("diff type", "--diff-text", "--diff-ground"),
    ("a large file's Load diff", "--blue", "--diff-ground"),
    ("the note under a large file's Load diff", "--muted", "--diff-ground"),
    ("diff type on an added line", "--diff-text", "--diff-added"),
    ("diff type on a removed line", "--diff-text", "--diff-removed"),
    ("a line number", "--diff-line-number", "--diff-ground"),
    ("a line number on an elided row", "--diff-line-number",
     "--diff-expander"),
    ("a hunk header", "--diff-hunk-text", "--diff-ground"),
    ("a line number on an added row", "--diff-text", "--diff-added-gutter"),
    ("a line number on a removed row", "--diff-text", "--diff-removed-gutter"),
    ("the changed words on an added line", "--diff-text", "--diff-added-emph"),
    ("the changed words on a removed line", "--diff-text",
     "--diff-removed-emph"),
    ("the commented range in the code context", "--diff-text",
     "--range-highlight"),
    ("an elided row", "--diff-hunk-text", "--diff-expander"),
    ("the arrow that expands it", "--diff-text", "--diff-expander-num"),
    ("a file header", "--diff-text", "--diff-file"),
    ("a note", "--diff-note-text", "--diff-note"),
    ("a diff error", "--diff-error", "--diff-ground"),
    ("the terminal's type when light", "--tty-light-text", "--tty-light-ground"),
    ("the terminal's type when dark", "--tty-dark-text", "--tty-dark-ground"),
    *(
        (f"{token} code on {where}", f"--syntax-{token}", ground)
        for token in ("keyword", "string", "comment", "constant", "title",
                      "type", "name")
        for where, ground in (
            ("the diff's ground", "--diff-ground"),
            ("an added line", "--diff-added"),
            ("a removed line", "--diff-removed"),
            ("the commented range", "--range-highlight"),
        )
    ),
)

_PAINTS_TYPE_RE = re.compile(r"(?<![-\w])color: var\((--[a-z0-9-]+)")


THEMES = ("light", "dark")


def test_every_pair_the_board_sets_type_in_clears_aa():
    bound = css_variables(client_for().get(f"{THE_ROOT}/palette.css").text)

    under_aa = [
        f"{what} is {ratio:.2f}:1 in {theme}"
        for theme in THEMES
        for what, ink, ground in TYPE_ON_GROUND
        if (ratio := contrast_ratio(bound[theme][ink], bound[theme][ground]))
        < WCAG_AA_NORMAL_TEXT
    ]

    assert under_aa == [], f"under AA at {WCAG_AA_NORMAL_TEXT}:1: {under_aa}"


def test_no_variable_paints_type_without_a_ground_to_clear():
    painted = set(_PAINTS_TYPE_RE.findall(APP_CSS.read_text()))
    measured = {type_variable for _, type_variable, _ in TYPE_ON_GROUND}

    assert painted, "the app paints no type through a variable at all"
    assert painted <= measured | {"--body-stack"}, (
        f"{sorted(painted - measured - {'--body-stack'})} colour type in the "
        f"app and no row of TYPE_ON_GROUND says what they sit on, so nothing "
        f"measures them"
    )


EDGE_INKS = {
    "ready": ("--yellow-text", "--yellow"),
    "failed": ("--red",),
    "reopened": ("--text",),
    "working": ("--mark",),
    "waiting-on-others": ("--mark",),
    "draft": ("--mark",),
    "rework": ("--blue",),
    "parked": (),
}

ROW_GROUNDS = ("--page", "--selected", "--grey-fill")

_EDGE_RULE_RE = re.compile(r'^\.edge\[data-square="([a-z-]+)"\]\s*\{([^}]*)\}', re.M)


def test_every_row_edge_stands_off_every_ground_its_row_takes():
    bound = css_variables(client_for().get(f"{THE_ROOT}/palette.css").text)

    faint = [
        f"a {square} edge is {ratio:.2f}:1 on {ground} in {theme}"
        for theme in THEMES
        for square, inks in EDGE_INKS.items()
        if inks
        for ground in ROW_GROUNDS
        if (ratio := max(contrast_ratio(bound[theme][ink], bound[theme][ground])
                         for ink in inks)) < WCAG_NON_TEXT
    ]

    assert faint == [], f"under {WCAG_NON_TEXT}:1 for a mark: {faint}"


def test_every_edge_rule_paints_only_the_inks_measured_for_it():
    drawn = {
        square: set(re.findall(r"var\((--[a-z0-9-]+)\)", body))
        for square, body in _EDGE_RULE_RE.findall(APP_CSS.read_text())
    }
    mixed = [
        square for square, body in _EDGE_RULE_RE.findall(APP_CSS.read_text())
        if "color-mix" in body
    ]

    assert drawn == {square: set(inks) for square, inks in EDGE_INKS.items()}
    assert mixed == [], f"{mixed} mix an ink the palette never measures"
