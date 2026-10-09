from github_orchestrator.board_api import _palette as palette

CSS = "text/css; charset=utf-8"

FAMILY = "Board Face"

BODY_STACK = f'"{FAMILY}", "Helvetica Neue", Arial, sans-serif'

FONT_WEIGHTS = {
    "Extralight": 200, "Light": 300, "Book": 350, "Regular": 400,
    "Medium": 500, "SemiBold": 600, "Bold": 700, "ExtraBold": 800,
}

DIFF_VARIABLES = (
    "diff_text", "diff_ground", "diff_added", "diff_added_emph",
    "diff_added_gutter", "diff_removed", "diff_removed_emph",
    "diff_removed_gutter", "diff_hunk_text",
    "diff_file", "diff_expander", "diff_expander_num",
    "diff_line_number", "diff_note", "diff_note_text",
    "diff_error",
)

SYNTAX_VARIABLES = (
    "syntax_keyword", "syntax_string", "syntax_comment", "syntax_constant",
    "syntax_title", "syntax_type", "syntax_name",
)

PAGE_VARIABLES = (
    "page", "card", "text", "muted", "hairline", "border_strong", "scrim",
    "yellow", "yellow_text", "yellow_muted", "blue", "blue_fill",
    "link", "green",
    "green_fill", "grey", "grey_fill", "red", "red_fill", "flag",
    "ready_ground", "ready_text", "ready_muted", "ready_edge", "selected", "range_highlight",
    "tty_ground", "tty_text",
)


def _variables(colours: palette.Palette) -> str:
    return " ".join(
        f"--{field.replace('_', '-')}: {getattr(colours, field)};"
        for field in PAGE_VARIABLES + DIFF_VARIABLES + SYNTAX_VARIABLES)


def _face(file_name: str) -> str | None:
    stem = file_name.removesuffix(".otf").rpartition("-")[2]
    italic = stem.endswith("Italic")
    weight = FONT_WEIGHTS.get(stem.removesuffix("Italic") if italic else stem)
    if weight is None:
        return None
    return (f'  @font-face {{ font-family: "{FAMILY}"; '
            f'src: url("/fonts/{file_name}") format("opentype"); '
            f"font-weight: {weight}; "
            f"font-style: {'italic' if italic else 'normal'}; "
            "font-display: swap; }\n")


def font_faces(font_files: tuple[str, ...]) -> str:
    return "".join(face for face in map(_face, font_files) if face is not None)


def palette_css() -> bytes:
    light = _variables(palette.LIGHT)
    dark = _variables(palette.DARK)
    return (
        f":root {{ {light} }}\n"
        "@media (prefers-color-scheme: dark) {\n"
        f'  :root:not([data-theme="light"]) {{ {dark} }}\n'
        "}\n"
        f':root[data-theme="dark"] {{ {dark} }}\n'
    ).encode()


def fonts_css(files: tuple[str, ...]) -> bytes:
    return (f"{font_faces(files)}"
            f":root {{ --body-stack: {BODY_STACK}; }}\n").encode()
