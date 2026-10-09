import dataclasses
import gzip
import logging
import re
import urllib.parse
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from github_orchestrator.board_api._app_files import (
    app_response,
)
from github_orchestrator.board_api._palette_css import (
    CSS,
    font_faces,
    fonts_css,
    palette_css,
)

log = logging.getLogger(__name__)

HTML = "text/html; charset=utf-8"
PLAIN = "text/plain; charset=utf-8"


FONT = "font/otf"
FONT_CACHE_CONTROL = "public, max-age=86400"
FONT_NAME_RE = re.compile(r"^[A-Za-z0-9]+-[A-Za-z]+\.otf$")

Response = tuple[int, str, bytes, Mapping[str, str]]


NO_HEADERS: Mapping[str, str] = MappingProxyType({})

GZIP_MIN_BYTES = 256

PALETTE_CSS = "/palette.css"
FONTS_CSS = "/fonts.css"

_FONT_RE = re.compile(r"^/fonts/([^/]+)$")


@dataclasses.dataclass(frozen=True)
class Fonts:
    directory: Path | None = None
    files: tuple[str, ...] = ()
    problem: str | None = None


NO_FONTS = Fonts()

FALLBACK = ", so the board is set in Helvetica Neue instead of its own face"


def _servable(directory: Path, name: str) -> bool:
    if not FONT_NAME_RE.match(name):
        return False
    path = directory / name
    try:
        if not path.is_file():
            return False
        if path.resolve().parent != directory.resolve():
            log.warning("refusing %s: it leaves %s", name, directory)
            return False
    except OSError:
        return False
    return True


def fonts_in(directory: str | None) -> Fonts:
    if not directory:
        return NO_FONTS
    root = Path(directory).expanduser()
    try:
        entries = sorted(entry.name for entry in root.iterdir())
    except OSError:
        return Fonts(problem=f"board_font_dir {root} cannot be listed{FALLBACK}")
    files = tuple(name for name in entries if _servable(root, name))
    if not font_faces(files):
        return Fonts(root, files, f"board_font_dir {root} holds no <Family>-<Style>.otf face{FALLBACK}")
    return Fonts(root, files)


def served_fonts(directory: str | None) -> Fonts:
    fonts = fonts_in(directory)
    if fonts.problem is not None:
        log.warning("%s", fonts.problem)
    return fonts


def font_bytes(fonts: Fonts, name: str) -> bytes | None:
    if fonts.directory is None or not _servable(fonts.directory, name):
        return None
    try:
        return (fonts.directory / name).read_bytes()
    except OSError:
        return None


def accepts_gzip(accept_encoding: str | None) -> bool:
    for coding in (accept_encoding or "").split(","):
        token, _, params = coding.strip().partition(";")
        if token.strip().lower() != "gzip":
            continue
        for param in params.split(";"):
            key, _, value = param.partition("=")
            if key.strip().lower() == "q":
                try:
                    return float(value.strip()) > 0
                except ValueError:
                    return False
        return True
    return False


def encode_body(body: bytes,
                accept_encoding: str | None) -> tuple[bytes, str | None]:
    if accepts_gzip(accept_encoding) and len(body) >= GZIP_MIN_BYTES:
        return gzip.compress(body, 6), "gzip"
    return body, None


def not_found() -> tuple[int, str, bytes]:
    return 404, PLAIN, b"not found"


def get_not_found() -> Response:
    return *not_found(), NO_HEADERS


def handle_get(fonts: Fonts, app_root: Path, raw_path: str) -> Response:
    path = urllib.parse.urlsplit(raw_path).path
    match = _FONT_RE.match(path)
    if match:
        served = font_bytes(fonts, match.group(1))
        if served is None:
            return get_not_found()
        return 200, FONT, served, {"Cache-Control": FONT_CACHE_CONTROL}
    if path == FONTS_CSS:
        return 200, CSS, fonts_css(fonts.files), NO_HEADERS
    if path == PALETTE_CSS:
        return 200, CSS, palette_css(), NO_HEADERS
    served_app = app_response(path, app_root)
    if served_app is not None:
        app_status, app_type, app_body = served_app
        return app_status, app_type, app_body, NO_HEADERS
    return get_not_found()
