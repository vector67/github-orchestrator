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

TTY_LIGHT_GROUND = WHITE
TTY_LIGHT_TEXT = "#1a1a1a"
TTY_DARK_GROUND = "#0d0d0d"
TTY_DARK_TEXT = "#e6e6e6"


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
    green_text: str
    grey: str
    mark: str
    grey_fill: str
    red: str
    red_fill: str
    red_text: str
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
    tty_light_ground: str
    tty_light_text: str
    tty_dark_ground: str
    tty_dark_text: str


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
    green_text=over(GREEN, 0.6, BLACK),
    grey=over_white(BLACK, 0.3),
    mark=over_white(BLACK, 0.5),
    grey_fill=GREY_TINT,
    red=RED,
    red_fill=over_white(RED, 0.12),
    red_text=over(RED, 0.85, BLACK),
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
    tty_light_ground=TTY_LIGHT_GROUND,
    tty_light_text=TTY_LIGHT_TEXT,
    tty_dark_ground=TTY_DARK_GROUND,
    tty_dark_text=TTY_DARK_TEXT,
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
    green_text=GREEN,
    grey=over(DARK_TEXT, 0.3, DARK_PAGE),
    mark=over(DARK_TEXT, 0.45, DARK_PAGE),
    grey_fill=DARK_SUBTLE,
    red=RED,
    red_fill=over(RED, 0.16, DARK_PAGE),
    red_text=over(RED, 0.8, WHITE),
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
    tty_light_ground=TTY_LIGHT_GROUND,
    tty_light_text=TTY_LIGHT_TEXT,
    tty_dark_ground=TTY_DARK_GROUND,
    tty_dark_text=TTY_DARK_TEXT,
)


SOLARIZED_ANSI = (
    "#073642", "#dc322f", "#859900", "#b58900", "#268bd2", "#d33682", "#2aa198", "#eee8d5",
    "#002b36", "#cb4b16", "#586e75", "#657b83", "#839496", "#6c71c4", "#93a1a1", "#fdf6e3",
)


@dataclass(frozen=True)
class TerminalTheme:
    key: str
    ground: str
    text: str
    cursor: str
    selection: str
    ansi: tuple[str, ...] = ()

    def variables(self) -> dict[str, str]:
        slots = {"ground": self.ground, "text": self.text,
                 "cursor": self.cursor, "selection": self.selection}
        slots.update({f"ansi-{index}": colour for index, colour in enumerate(self.ansi)})
        return {f"--tty-{self.key}-{slot}": colour for slot, colour in slots.items()}


THEMES = (
    TerminalTheme("default-light", TTY_LIGHT_GROUND, TTY_LIGHT_TEXT,
                  TTY_LIGHT_TEXT, "#cfdcf5"),
    TerminalTheme("default-dark", TTY_DARK_GROUND, TTY_DARK_TEXT,
                  TTY_DARK_TEXT, "#3a3d41"),
    TerminalTheme("solarized-light", "#fdf6e3", "#657b83", "#586e75", "#eee8d5",
                  SOLARIZED_ANSI),
    TerminalTheme("solarized-dark", "#002b36", "#839496", "#93a1a1", "#073642",
                  SOLARIZED_ANSI),
    TerminalTheme("tokyo-night-day", "#e1e2e7", "#3760bf", "#3760bf", "#b6bfe2", (
        "#e9e9ed", "#f52a65", "#587539", "#8c6c3e", "#2e7de9", "#9854f1", "#007197", "#6172b0",
        "#a1a6c5", "#f52a65", "#587539", "#8c6c3e", "#2e7de9", "#9854f1", "#007197", "#3760bf",
    )),
    TerminalTheme("tokyo-night", "#1a1b26", "#c0caf5", "#c0caf5", "#283457", (
        "#15161e", "#f7768e", "#9ece6a", "#e0af68", "#7aa2f7", "#bb9af7", "#7dcfff", "#a9b1d6",
        "#414868", "#f7768e", "#9ece6a", "#e0af68", "#7aa2f7", "#bb9af7", "#7dcfff", "#c0caf5",
    )),
    TerminalTheme("monokai", "#272822", "#f8f8f2", "#f8f8f0", "#49483e", (
        "#272822", "#f92672", "#a6e22e", "#f4bf75", "#66d9ef", "#ae81ff", "#a1efe4", "#f8f8f2",
        "#75715e", "#f92672", "#a6e22e", "#f4bf75", "#66d9ef", "#ae81ff", "#a1efe4", "#f9f8f5",
    )),
    TerminalTheme("one-light", "#fafafa", "#383a42", "#526fff", "#e5e5e6", (
        "#383a42", "#e45649", "#50a14f", "#c18401", "#4078f2", "#a626a4", "#0184bc", "#fafafa",
        "#a0a1a7", "#e45649", "#50a14f", "#c18401", "#4078f2", "#a626a4", "#0184bc", "#ffffff",
    )),
    TerminalTheme("one-dark", "#282c34", "#abb2bf", "#528bff", "#3e4451", (
        "#282c34", "#e06c75", "#98c379", "#e5c07b", "#61afef", "#c678dd", "#56b6c2", "#abb2bf",
        "#5c6370", "#e06c75", "#98c379", "#e5c07b", "#61afef", "#c678dd", "#56b6c2", "#ffffff",
    )),
    TerminalTheme("gruvbox-light", "#fbf1c7", "#3c3836", "#3c3836", "#d5c4a1", (
        "#fbf1c7", "#cc241d", "#98971a", "#d79921", "#458588", "#b16286", "#689d6a", "#7c6f64",
        "#928374", "#9d0006", "#79740e", "#b57614", "#076678", "#8f3f71", "#427b58", "#3c3836",
    )),
    TerminalTheme("gruvbox-dark", "#282828", "#ebdbb2", "#ebdbb2", "#504945", (
        "#282828", "#cc241d", "#98971a", "#d79921", "#458588", "#b16286", "#689d6a", "#a89984",
        "#928374", "#fb4934", "#b8bb26", "#fabd2f", "#83a598", "#d3869b", "#8ec07c", "#ebdbb2",
    )),
    TerminalTheme("catppuccin-latte", "#eff1f5", "#4c4f69", "#dc8a78", "#acb0be", (
        "#5c5f77", "#d20f39", "#40a02b", "#df8e1d", "#1e66f5", "#ea76cb", "#179299", "#acb0be",
        "#6c6f85", "#d20f39", "#40a02b", "#df8e1d", "#1e66f5", "#ea76cb", "#179299", "#bcc0cc",
    )),
    TerminalTheme("catppuccin-mocha", "#1e1e2e", "#cdd6f4", "#f5e0dc", "#585b70", (
        "#45475a", "#f38ba8", "#a6e3a1", "#f9e2af", "#89b4fa", "#f5c2e7", "#94e2d5", "#bac2de",
        "#585b70", "#f38ba8", "#a6e3a1", "#f9e2af", "#89b4fa", "#f5c2e7", "#94e2d5", "#a6adc8",
    )),
    TerminalTheme("dracula", "#282a36", "#f8f8f2", "#f8f8f2", "#44475a", (
        "#21222c", "#ff5555", "#50fa7b", "#f1fa8c", "#bd93f9", "#ff79c6", "#8be9fd", "#f8f8f2",
        "#6272a4", "#ff6e6e", "#69ff94", "#ffffa5", "#d6acff", "#ff92df", "#a4ffff", "#ffffff",
    )),
    TerminalTheme("nord", "#2e3440", "#d8dee9", "#d8dee9", "#434c5e", (
        "#3b4252", "#bf616a", "#a3be8c", "#ebcb8b", "#81a1c1", "#b48ead", "#88c0d0", "#e5e9f0",
        "#4c566a", "#bf616a", "#a3be8c", "#ebcb8b", "#81a1c1", "#b48ead", "#8fbcbb", "#eceff4",
    )),
)


def theme_variables() -> str:
    return " ".join(
        f"{name}: {colour};"
        for theme in THEMES
        for name, colour in theme.variables().items())
