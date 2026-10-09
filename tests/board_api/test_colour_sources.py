import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
BOARD_API = REPO_ROOT / "src" / "github_orchestrator" / "board_api"


_CSS_NAMES = (
    "aliceblue antiquewhite aqua aquamarine azure beige bisque black "
    "blanchedalmond blue blueviolet brown burlywood cadetblue chartreuse "
    "chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan "
    "darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta "
    "darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen "
    "darkslateblue darkslategray darkslategrey darkturquoise darkviolet "
    "deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite "
    "forestgreen fuchsia gainsboro ghostwhite gold goldenrod gray green "
    "greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender "
    "lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan "
    "lightgoldenrodyellow lightgray lightgreen lightgrey lightpink "
    "lightsalmon lightseagreen lightskyblue lightslategray lightslategrey "
    "lightsteelblue lightyellow lime limegreen linen magenta maroon "
    "mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen "
    "mediumslateblue mediumspringgreen mediumturquoise mediumvioletred "
    "midnightblue mintcream mistyrose moccasin navajowhite navy oldlace olive "
    "olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise "
    "palevioletred papayawhip peachpuff peru pink plum powderblue purple "
    "rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown "
    "seagreen seashell sienna silver skyblue slateblue slategray slategrey "
    "snow springgreen steelblue tan teal thistle tomato turquoise violet "
    "wheat white whitesmoke yellow yellowgreen"
).split()

_LITERAL_RE = re.compile(r"#[0-9a-fA-F]{3,8}(?![0-9a-zA-Z])"
                         r"|(?:rgb|hsl)a?\([^)]*\)")
_NAME_RE = re.compile(r"(?<![-\w])(?:" + "|".join(_CSS_NAMES) + r")(?![-\w])")


def colours_in(text: str) -> list[str]:
    found = _LITERAL_RE.findall(text)
    for line in text.splitlines():
        value = line.partition(":")[2]
        if value and '"' not in value and "'" not in value:
            found += _NAME_RE.findall(value)
    return found
_USED_RE = re.compile(r"var\((--[a-z0-9-]+)\)")


NOT_A_COLOUR = {"--body-stack"}


def test_no_module_but_the_palette_writes_a_colour():
    guilty = {
        str(path.relative_to(BOARD_API)): sorted(set(colours_in(path.read_text())))
        for path in sorted(BOARD_API.rglob("*.py"))
        if path.name != "_palette.py" and colours_in(path.read_text())
    }

    assert not guilty, (
        f"{guilty} name colours of their own; every one belongs to the "
        f"palette, which is the single place the page CSS is drawn from"
    )
