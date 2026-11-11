from dataclasses import dataclass, field

from github_orchestrator.domain import Sha
from github_orchestrator.working_copies import _diff, _hunks, _revisions
from github_orchestrator.working_copies.interface import PrDiff


@dataclass(frozen=True)
class _Held:
    tips: tuple[str, str]
    diff: PrDiff
    line_counts: dict[str, int | None] = field(default_factory=dict)


class PrReads:
    def __init__(self) -> None:
        self._merge_bases: dict[str, tuple[tuple[str, str], str]] = {}
        self._diffs: dict[str, _Held] = {}

    def merge_base(self, worktree: str, base_branch: str | None, head: str) -> str | None:
        tips = _diff.tips(worktree, head, base_branch)
        if tips is None:
            return None
        known = self._merge_bases.get(worktree)
        if known is not None and known[0] == tips:
            return known[1]
        found = _diff.merge_base(worktree, tips[1], tips[0])
        if found is not None:
            self._merge_bases[worktree] = (tips, found)
        return found

    def diff(self, worktree: str, base_branch: str | None, head: str) -> PrDiff | None:
        tips = _diff.tips(worktree, head, base_branch)
        if tips is None:
            return None
        held = self._diffs.get(worktree)
        if held is not None and held.tips == tips:
            return held.diff
        base = _diff.merge_base(worktree, tips[1], tips[0])
        files = None if base is None else _hunks.diff_files(worktree, base, tips[0])
        if base is None or files is None:
            return None
        diff = PrDiff(Sha(base), Sha(tips[0]), files)
        self._diffs[worktree] = _Held(tips, diff)
        return diff

    def line_count(self, worktree: str, sha: str, path: str) -> int | None:
        held = self._diffs.get(worktree)
        if held is None or held.tips[0] != sha:
            return _revisions.line_count(_revisions.blob(worktree, sha, path))
        if path not in held.line_counts:
            held.line_counts[path] = _revisions.line_count(_revisions.blob(worktree, sha, path))
        return held.line_counts[path]
