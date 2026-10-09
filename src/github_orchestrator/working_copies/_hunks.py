import logging
import re

from github_orchestrator.working_copies._diff import DiffSource, raw_diff
from github_orchestrator.working_copies.interface import DiffHunk, DiffLine, FileDiff

log = logging.getLogger(__name__)

UNIFIED = 3

_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")

CONTEXT = "context"
ADDED = "added"
REMOVED = "removed"
MODIFIED = "modified"
RENAMED = "renamed"
COPIED = "copied"


class _File:
    def __init__(self, path: str) -> None:
        self.path = path
        self.old_path: str | None = None
        self.status = MODIFIED
        self.is_binary = False
        self.hunks: list[DiffHunk] = []
        self.lines: list[DiffLine] = []
        self.header: tuple[int, int, int, int, str | None] | None = None
        self.old_no = 0
        self.new_no = 0

    def close_hunk(self) -> None:
        if self.header is None:
            return
        old_start, old_lines, new_start, new_lines, section = self.header
        self.hunks.append(DiffHunk(old_start=old_start, old_lines=old_lines,
                                   new_start=new_start, new_lines=new_lines,
                                   section=section, lines=tuple(self.lines)))
        self.header = None
        self.lines = []

    def done(self) -> FileDiff:
        self.close_hunk()
        lines = [line for hunk in self.hunks for line in hunk.lines]
        return FileDiff(
            path=self.path,
            old_path=self.old_path,
            status=self.status,
            added=sum(1 for line in lines if line.kind == ADDED),
            removed=sum(1 for line in lines if line.kind == REMOVED),
            is_binary=self.is_binary,
            hunks=tuple(self.hunks),
        )


def _named(line: str) -> str:
    return line.split(" b/", 1)[-1].strip()


def _start(header: str) -> _File:
    return _File(_named(header))


def _hunk_header(current: _File, line: str) -> bool:
    match = _HEADER_RE.match(line)
    if match is None:
        return False
    current.close_hunk()
    old_start, old_lines, new_start, new_lines, section = match.groups()
    current.header = (int(old_start), int(old_lines or 1), int(new_start),
                      int(new_lines or 1), section.strip() or None)
    current.old_no = int(old_start)
    current.new_no = int(new_start)
    return True


def _body(current: _File, line: str) -> None:
    if line.startswith("+"):
        current.lines.append(DiffLine(kind=ADDED, old_line=None,
                                      new_line=current.new_no,
                                      text=line[1:]))
        current.new_no += 1
    elif line.startswith("-"):
        current.lines.append(DiffLine(kind=REMOVED, old_line=current.old_no,
                                      new_line=None, text=line[1:]))
        current.old_no += 1
    elif line.startswith(" "):
        current.lines.append(DiffLine(kind=CONTEXT, old_line=current.old_no,
                                      new_line=current.new_no,
                                      text=line[1:]))
        current.old_no += 1
        current.new_no += 1


def _preamble(current: _File, line: str) -> None:
    if line.startswith("new file mode"):
        current.status = ADDED
    elif line.startswith("deleted file mode"):
        current.status = REMOVED
    elif line.startswith("rename from "):
        current.old_path = line.removeprefix("rename from ").strip()
        current.status = RENAMED
    elif line.startswith("copy from "):
        current.old_path = line.removeprefix("copy from ").strip()
        current.status = COPIED
    elif line.startswith("rename to ") or line.startswith("copy to "):
        current.path = line.split(" to ", 1)[1].strip()
    elif line.startswith("Binary files") or line.startswith("GIT binary patch"):
        current.is_binary = True


def parse_diff(printed: str) -> tuple[FileDiff, ...]:
    """git's unified diff as files, hunks and lines.

    It keeps the numbers, because the contract says a diff is data and
    whatever draws it does the highlighting.
    """
    files: list[FileDiff] = []
    current: _File | None = None
    for line in printed.split("\n"):
        if line.startswith("diff --git "):
            if current is not None:
                files.append(current.done())
            current = _start(line)
        elif current is None:
            continue
        elif _hunk_header(current, line):
            continue
        elif current.header is not None:
            _body(current, line)
        else:
            _preamble(current, line)
    if current is not None:
        files.append(current.done())
    return tuple(files)


def diff_files(worktree: str, base: str,
               head: str) -> tuple[FileDiff, ...] | None:
    printed, complaint = raw_diff(
        DiffSource(worktree=worktree, left=base, right=head), UNIFIED)
    if printed is None:
        log.warning("diff %s..%s in %s: %s", base, head, worktree, complaint)
        return None
    return parse_diff(printed)
