from collections.abc import Mapping
from typing import Any

from github_orchestrator.domain import Side

_WRITTEN_BEFORE_THE_KERNEL = {"LEFT": Side.BEFORE, "RIGHT": Side.AFTER}


def side_word(side: Side | None) -> str | None:
    return None if side is None else side.value


def start_side_word(written: Mapping[str, Any]) -> Any:
    if "start_side" in written:
        return written["start_side"]
    return written.get("side") if written.get("start_line") is not None else None


def side_of(word: object) -> Side | None:
    if not isinstance(word, str):
        return None
    if word in _WRITTEN_BEFORE_THE_KERNEL:
        return _WRITTEN_BEFORE_THE_KERNEL[word]
    try:
        return Side(word)
    except ValueError:
        return None
