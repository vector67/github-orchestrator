from collections.abc import Iterator, Sequence

from github_orchestrator.board_api._contract import (
    DiffSide,
    FileAnchors,
    LineAnchor,
    PullRequestLine,
)
from github_orchestrator.working_copies import FileDiff

ADDED = "added"
REMOVED = "removed"


def _carried(changes: Sequence[FileDiff], path: str, line: int) -> int | None:
    change = next((one for one in changes if (one.old_path or one.path) == path), None)
    if change is None:
        return line
    if change.status == REMOVED or change.path != path:
        return None
    shift = 0
    for hunk in change.hunks:
        if line < hunk.old_start + (0 if hunk.old_lines else 1):
            break
        for one in hunk.lines:
            if one.old_line == line:
                return one.new_line
        shift += hunk.new_lines - hunk.old_lines
    return line + shift


def _shown(pull_request: Sequence[FileDiff], path: str, base_path: str,
           side: DiffSide, line: int) -> bool:
    file = next((one for one in pull_request if one.path == path), None)
    if file is None:
        return False
    if side is DiffSide.LEFT:
        return (file.old_path or file.path) == base_path and any(
            one.kind != ADDED and one.old_line == line
            for hunk in file.hunks for one in hunk.lines)
    return any(one.kind != REMOVED and one.new_line == line
               for hunk in file.hunks for one in hunk.lines)


def _sides(file: FileDiff) -> Iterator[tuple[DiffSide, int]]:
    for hunk in file.hunks:
        for one in hunk.lines:
            if one.kind != REMOVED and one.new_line is not None:
                yield DiffSide.RIGHT, one.new_line
            if one.kind != ADDED and one.old_line is not None:
                yield DiffSide.LEFT, one.old_line


def _anchored(file: FileDiff, forward: Sequence[FileDiff], backward: Sequence[FileDiff],
              pull_request: Sequence[FileDiff]) -> Iterator[LineAnchor]:
    base_path = file.old_path or file.path
    for side, line in _sides(file):
        moved = (_carried(forward, file.path, line) if side is DiffSide.RIGHT
                 else _carried(backward, base_path, line))
        if moved is not None and _shown(pull_request, file.path, base_path, side, moved):
            yield LineAnchor(side=side, line=line,
                             onto=PullRequestLine(side=side, line=moved))


def anchors_of(shown: Sequence[FileDiff], forward: Sequence[FileDiff],
               backward: Sequence[FileDiff],
               pull_request: Sequence[FileDiff]) -> list[FileAnchors]:
    return [FileAnchors(path=file.path,
                        lines=list(_anchored(file, forward, backward, pull_request)))
            for file in shown]
