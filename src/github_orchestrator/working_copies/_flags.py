import json
from pathlib import Path

from github_orchestrator.domain import Pr
from github_orchestrator.working_copies._layout import repo_dir
from github_orchestrator.working_copies._trouble import Conflict, Mismatch


def _flag_path(directory: Path, pr: Pr) -> Path:
    return repo_dir(directory, pr.repo) / f"{pr.number}.flag"


def _write(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))


class DiskFlags:
    def __init__(self, mismatched_dir: Path, worktree_conflicts_dir: Path) -> None:
        self._mismatched_dir = mismatched_dir
        self._worktree_conflicts_dir = worktree_conflicts_dir

    def mismatch(self, pr: Pr) -> Mismatch | None:
        path = _flag_path(self._mismatched_dir, pr)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return Mismatch(
                worktree=data["worktree"],
                actual_branch=data["actual_branch"],
                expected_branch=data["expected_branch"],
                since=float(data["since"]),
                run_alive=bool(data.get("run_alive", False)),
                last_output_at=(
                    None if data.get("last_output_at") is None
                    else float(data["last_output_at"])
                ),
                release_requested=bool(data.get("release_requested", False)),
            )
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            return None

    def save_mismatch(self, pr: Pr, mismatch: Mismatch) -> None:
        _write(_flag_path(self._mismatched_dir, pr), {
            "worktree": mismatch.worktree,
            "actual_branch": mismatch.actual_branch,
            "expected_branch": mismatch.expected_branch,
            "since": mismatch.since,
            "run_alive": mismatch.run_alive,
            "last_output_at": mismatch.last_output_at,
            "release_requested": mismatch.release_requested,
        })

    def clear_mismatch(self, pr: Pr) -> None:
        _flag_path(self._mismatched_dir, pr).unlink(missing_ok=True)

    def conflict(self, pr: Pr) -> Conflict | None:
        path = _flag_path(self._worktree_conflicts_dir, pr)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return Conflict(
                worktree=data["worktree"],
                other_pr=int(data["other_pr"]),
                since=float(data["since"]),
                checks=int(data["checks"]),
            )
        except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
            return None

    def save_conflict(self, pr: Pr, conflict: Conflict) -> None:
        _write(_flag_path(self._worktree_conflicts_dir, pr), {
            "worktree": conflict.worktree,
            "other_pr": conflict.other_pr,
            "since": conflict.since,
            "checks": conflict.checks,
        })

    def clear_conflict(self, pr: Pr) -> None:
        _flag_path(self._worktree_conflicts_dir, pr).unlink(missing_ok=True)
