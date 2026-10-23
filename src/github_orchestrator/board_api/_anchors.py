from bisect import bisect_right
from collections.abc import Callable, Iterable, Iterator, Sequence
from itertools import accumulate

from github_orchestrator.board_api._contract import (
    DiffSide,
    FileAnchors,
    LineAnchor,
    PullRequestLine,
)
from github_orchestrator.working_copies import FileDiff

ADDED = "added"
REMOVED = "removed"

type _Carrier = Callable[[int], int | None]


def _firsts[K, V](pairs: Iterable[tuple[K, V]]) -> dict[K, V]:
    found: dict[K, V] = {}
    for key, value in pairs:
        found.setdefault(key, value)
    return found


def _unmoved(line: int) -> int | None:
    return line


def _gone(line: int) -> int | None:
    return None


def _carrier(change: FileDiff) -> _Carrier:
    if change.status == REMOVED or change.path != (change.old_path or change.path):
        return _gone
    reach = list(accumulate((hunk.old_start + (0 if hunk.old_lines else 1)
                             for hunk in change.hunks), max))
    shifts = [0, *accumulate(hunk.new_lines - hunk.old_lines for hunk in change.hunks)]
    landing = _firsts((one.old_line, (index, one.new_line))
                      for index, hunk in enumerate(change.hunks) for one in hunk.lines)

    def carried(line: int) -> int | None:
        passed = bisect_right(reach, line)
        index, new_line = landing.get(line, (passed, None))
        return new_line if index < passed else line + shifts[passed]
    return carried


def _carriers(changes: Sequence[FileDiff]) -> dict[str, _Carrier]:
    return {path: _carrier(change) for path, change
            in _firsts((one.old_path or one.path, one) for one in changes).items()}


def _visible(file: FileDiff | None, base_path: str) -> dict[DiffSide, set[int | None]]:
    if file is None:
        return {DiffSide.RIGHT: set(), DiffSide.LEFT: set()}
    lines = [one for hunk in file.hunks for one in hunk.lines]
    same_base = (file.old_path or file.path) == base_path
    return {DiffSide.RIGHT: {one.new_line for one in lines if one.kind != REMOVED},
            DiffSide.LEFT: {one.old_line for one in lines
                            if one.kind != ADDED and same_base}}


def _sides(file: FileDiff) -> Iterator[tuple[DiffSide, int]]:
    for hunk in file.hunks:
        for one in hunk.lines:
            if one.kind != REMOVED and one.new_line is not None:
                yield DiffSide.RIGHT, one.new_line
            if one.kind != ADDED and one.old_line is not None:
                yield DiffSide.LEFT, one.old_line


def _anchored(file: FileDiff, forward: dict[str, _Carrier], backward: dict[str, _Carrier],
              pull_request: dict[str, FileDiff]) -> Iterator[LineAnchor]:
    base_path = file.old_path or file.path
    carry = {DiffSide.RIGHT: forward.get(file.path, _unmoved),
             DiffSide.LEFT: backward.get(base_path, _unmoved)}
    visible = _visible(pull_request.get(file.path), base_path)
    for side, line in _sides(file):
        moved = carry[side](line)
        if moved is not None and moved in visible[side]:
            yield LineAnchor(side=side, line=line,
                             onto=PullRequestLine(side=side, line=moved))


def anchors_of(shown: Sequence[FileDiff], forward: Sequence[FileDiff],
               backward: Sequence[FileDiff],
               pull_request: Sequence[FileDiff]) -> list[FileAnchors]:
    carried_forward, carried_backward = _carriers(forward), _carriers(backward)
    by_path = _firsts((one.path, one) for one in pull_request)
    return [FileAnchors(path=file.path,
                        lines=list(_anchored(file, carried_forward, carried_backward, by_path)))
            for file in shown]
