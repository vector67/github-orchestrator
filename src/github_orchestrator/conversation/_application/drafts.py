import secrets
from collections.abc import Sequence

from github_orchestrator.conversation._application.ports import Ports
from github_orchestrator.conversation._domain.apply import create_draft
from github_orchestrator.conversation._domain.conversation import (
    Conversation,
)
from github_orchestrator.domain import Location, Side
from github_orchestrator.working_copies import FileDiff

DRAFT_PREFIX = "draft_"


def draft_key() -> str:
    """A key GitHub never hands out.

    The three thread kinds are keyed by the node ids of a
    `PullRequestReviewThread`, an `IssueComment` and a `PullRequestReview`,
    which begin `PRRT_`, `IC_` and `PRR_`, or are base64 with no underscore
    in ids minted before those prefixes. A lower-case prefix of the board's
    own can be neither.
    """
    return f"{DRAFT_PREFIX}{secrets.token_hex(8)}"


def open_draft(ports: Ports, body: str, anchor: Location, role: str,
               operation: str | None = None) -> Conversation:
    """A new draft on disk, under a key no record already holds."""
    while True:
        key = draft_key()
        with ports.records.update(key) as update:
            if update.conversation is not None:
                continue
            drafted = create_draft(
                key=key, body=body, anchor=anchor,
                author=ports.config.gh_account, role=role,
                at=ports.clock.now(), operation=operation or f"{key}.1")
            update.conversation = drafted
            return drafted


_SIDE_NAMES = {Side.BEFORE: "old", Side.AFTER: "new"}


def _named(path: str, number: int, side: Side) -> str:
    return f"{path}:{number} on the {_SIDE_NAMES[side]} side"


def _found(files: Sequence[FileDiff], path: str, number: int,
           side: Side) -> tuple[int, int] | None:
    for file in files:
        if file.path != path:
            continue
        for hunk, lines in enumerate(one.lines for one in file.hunks):
            for position, line in enumerate(lines):
                if (line.old_line if side is Side.BEFORE else line.new_line) == number:
                    return hunk, position
    return None


def off_the_diff(files: Sequence[FileDiff], anchor: Location) -> str | None:
    """Why GitHub would refuse a comment here, or None where it would take
    it: the line on its side and the first line on its own are lines of one
    hunk, the first no later in it than the line."""
    last = _named(anchor.path, anchor.line, anchor.side)
    end = _found(files, anchor.path, anchor.line, anchor.side)
    if end is None:
        return f"{last} is not a line of the pull request's diff"
    if anchor.start_line is None or anchor.start_side is None:
        return None
    first = _named(anchor.path, anchor.start_line, anchor.start_side)
    start = _found(files, anchor.path, anchor.start_line, anchor.start_side)
    if start is None:
        return f"{first} is not a line of the pull request's diff"
    if start[0] != end[0]:
        return (f"{first} is in another hunk than {last}; GitHub takes a range "
                f"only inside one hunk")
    if start[1] > end[1]:
        return f"{first} comes after {last} in the diff; a range starts before it ends"
    return None
