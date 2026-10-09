import mimetypes
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent / "static" / "app"
APP_PREFIX = "/"
INDEX = "index.html"
HTML = "text/html; charset=utf-8"


def _within(root: Path, candidate: Path) -> bool:
    return root == candidate or root in candidate.parents


def _served_path(root: Path, path: str) -> Path | None:
    relative = path[len(APP_PREFIX):]
    if not relative:
        return None
    candidate = (root / relative).resolve()
    if not _within(root, candidate) or not candidate.is_file():
        return None
    return candidate


def _type_of(served: Path) -> str:
    guessed, _ = mimetypes.guess_type(served.name)
    if guessed is None:
        return "application/octet-stream"
    if guessed.startswith("text/") or guessed == "application/javascript":
        return f"{guessed}; charset=utf-8"
    return guessed


SERVER_OWNED = ("/api/", "/fonts/")


def app_response(path: str, root: Path) -> tuple[int, str, bytes] | None:
    if not path.startswith(APP_PREFIX):
        return None
    if any(path.startswith(owned) for owned in SERVER_OWNED):
        return None
    root = root.resolve()
    served = _served_path(root, path)
    if served is not None:
        return 200, _type_of(served), served.read_bytes()
    index = root / INDEX
    if not index.is_file():
        return None
    return 200, HTML, index.read_bytes()
