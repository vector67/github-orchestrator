from __future__ import annotations

from dataclasses import dataclass

BLACK = "#000000"
WHITE = "#ffffff"
YELLOW = "#ffd70c"
BLUE = "#3f59dc"
GREEN = "#3acb81"
RED = "#dc3f4b"
GREY_TINT = "#f4f4f4"
FLAG_GROUND = "#3a3a3a"

TTY_GROUND = "#0d0d0d"
TTY_TEXT = "#e6e6e6"


def channels(colour: str) -> tuple[int, int, int]:
    raw = colour.lstrip("#")
    red, green, blue = (int(raw[i:i + 2], 16) for i in (0, 2, 4))
    return red, green, blue


def _hex(values: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % values


def _mix(primary: int, alpha: float, ground: int) -> int:
    return int(alpha * primary + (1 - alpha) * ground + 0.5)


def over(primary: str, alpha: float, ground: str) -> str:
    p, g = channels(primary), channels(ground)
    return _hex((_mix(p[0], alpha, g[0]), _mix(p[1], alpha, g[1]),
                 _mix(p[2], alpha, g[2])))


def over_white(primary: str, alpha: float) -> str:
    return over(primary, alpha, WHITE)


def translucent(colour: str, alpha: float) -> str:
    red, green, blue = channels(colour)
    return f"rgba({red}, {green}, {blue}, {alpha})"


@dataclass(frozen=True)
class Palette:
    page: str
    card: str
    text: str
    muted: str
    hairline: str
    border_strong: str
    scrim: str
    yellow: str
    yellow_text: str
    yellow_muted: str
    blue: str
    blue_fill: str
    link: str
    green: str
    green_fill: str
    grey: str
    grey_fill: str
    red: str
    red_fill: str
    flag: str
    ready_ground: str
    ready_text: str
    ready_muted: str
    ready_edge: str
    selected: str
    range_highlight: str
    diff_text: str
    diff_ground: str
    diff_added: str
    diff_added_emph: str
    diff_added_gutter: str
    diff_removed: str
    diff_removed_emph: str
    diff_removed_gutter: str
    diff_hunk_text: str
    diff_file: str
    diff_expander: str
    diff_expander_num: str
    diff_line_number: str
    diff_note: str
    diff_note_text: str
    diff_error: str
    syntax_keyword: str
    syntax_string: str
    syntax_comment: str
    syntax_constant: str
    syntax_title: str
    syntax_type: str
    syntax_name: str
    tty_ground: str
    tty_text: str


LIGHT = Palette(
    page=WHITE,
    card=WHITE,
    text=BLACK,
    muted="#666666",
    hairline=over_white(BLACK, 0.12),
    border_strong=BLACK,
    scrim=translucent(BLACK, 0.45),
    yellow=YELLOW,
    yellow_text=BLACK,
    yellow_muted=over(BLACK, 0.6, YELLOW),
    blue=BLUE,
    blue_fill=over_white(BLUE, 0.2),
    link=BLUE,
    green=GREEN,
    green_fill=over_white(GREEN, 0.2),
    grey=over_white(BLACK, 0.3),
    grey_fill=GREY_TINT,
    red=RED,
    red_fill=over_white(RED, 0.12),
    flag=FLAG_GROUND,
    ready_ground=YELLOW,
    ready_text=BLACK,
    ready_muted=over(BLACK, 0.6, YELLOW),
    ready_edge=BLACK,
    selected=over_white(BLACK, 0.07),
    range_highlight=over_white(BLACK, 0.07),
    diff_text=BLACK,
    diff_ground=WHITE,
    diff_added=over_white(GREEN, 0.2),
    diff_added_emph=over_white(GREEN, 0.5),
    diff_added_gutter=over_white(GREEN, 0.4),
    diff_removed=over_white(RED, 0.2),
    diff_removed_emph=over_white(RED, 0.5),
    diff_removed_gutter=over_white(RED, 0.4),
    diff_hunk_text="#666666",
    diff_file=GREY_TINT,
    diff_expander=GREY_TINT,
    diff_expander_num=GREY_TINT,
    diff_line_number="#666666",
    diff_note=BLACK,
    diff_note_text=WHITE,
    diff_error=BLACK,
    syntax_keyword="#b31d28",
    syntax_string="#0a3069",
    syntax_comment="#57606a",
    syntax_constant="#0550ae",
    syntax_title="#6639ba",
    syntax_type="#953800",
    syntax_name="#116329",
    tty_ground=TTY_GROUND,
    tty_text=TTY_TEXT,
)

DARK_PAGE = over(WHITE, 0.06, BLACK)
DARK_TEXT = over(BLACK, 0.06, WHITE)
DARK_MUTED = over(DARK_TEXT, 0.6, DARK_PAGE)
DARK_SUBTLE = over(DARK_TEXT, 0.05, DARK_PAGE)
DARK_READY = over(YELLOW, 0.18, DARK_PAGE)

DARK = Palette(
    page=DARK_PAGE,
    card=over(WHITE, 0.15, BLACK),
    text=DARK_TEXT,
    muted=DARK_MUTED,
    hairline=over(DARK_TEXT, 0.16, DARK_PAGE),
    border_strong=over(DARK_TEXT, 0.45, DARK_PAGE),
    scrim=translucent(BLACK, 0.6),
    yellow=YELLOW,
    yellow_text=BLACK,
    yellow_muted=over(BLACK, 0.6, YELLOW),
    blue=over(BLUE, 0.7, WHITE),
    blue_fill=over(BLUE, 0.2, DARK_PAGE),
    link=over(BLUE, 0.7, WHITE),
    green=GREEN,
    green_fill=over(GREEN, 0.2, DARK_PAGE),
    grey=over(DARK_TEXT, 0.3, DARK_PAGE),
    grey_fill=DARK_SUBTLE,
    red=RED,
    red_fill=over(RED, 0.16, DARK_PAGE),
    flag=FLAG_GROUND,
    ready_ground=DARK_READY,
    ready_text=DARK_TEXT,
    ready_muted=over(DARK_TEXT, 0.72, DARK_READY),
    ready_edge=YELLOW,
    selected=over(DARK_TEXT, 0.1, DARK_PAGE),
    range_highlight=over(DARK_TEXT, 0.1, DARK_PAGE),
    diff_text=DARK_TEXT,
    diff_ground=DARK_PAGE,
    diff_added=over(GREEN, 0.2, DARK_PAGE),
    diff_added_emph=over(GREEN, 0.5, DARK_PAGE),
    diff_added_gutter=over(GREEN, 0.4, DARK_PAGE),
    diff_removed=over(RED, 0.2, DARK_PAGE),
    diff_removed_emph=over(RED, 0.5, DARK_PAGE),
    diff_removed_gutter=over(RED, 0.4, DARK_PAGE),
    diff_hunk_text=DARK_MUTED,
    diff_file=DARK_SUBTLE,
    diff_expander=DARK_SUBTLE,
    diff_expander_num=DARK_SUBTLE,
    diff_line_number=DARK_MUTED,
    diff_note=DARK_TEXT,
    diff_note_text=DARK_PAGE,
    diff_error=DARK_TEXT,
    syntax_keyword="#ff7b72",
    syntax_string="#a5d6ff",
    syntax_comment="#9ea7b3",
    syntax_constant="#79c0ff",
    syntax_title="#d2a8ff",
    syntax_type="#ffa657",
    syntax_name="#7ee787",
    tty_ground=TTY_GROUND,
    tty_text=TTY_TEXT,
)
