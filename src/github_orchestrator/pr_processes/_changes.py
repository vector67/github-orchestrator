import re
from datetime import datetime
from pathlib import Path

from github_orchestrator.domain import Pr

CHANGES_FILE = "agent-changes.md"


def title(pr: Pr) -> str:
    return f"# Agent Changes -- {pr}\n\n"


_ESCAPE_SEQUENCE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b[ -/]*[0-~]"
)
_CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _inert(text: str) -> str:
    return _CONTROL_CHARACTER.sub("", _ESCAPE_SEQUENCE.sub("", text))


def entry(text: str, at: datetime) -> str:
    return f"## [{at.strftime('%Y-%m-%d %H:%M')}]\n\n{_inert(text)}\n"


def start(worktree: Path, pr: Pr) -> None:
    changes = worktree / CHANGES_FILE
    if not changes.exists():
        changes.write_text(title(pr))


class DiskAgentChanges:
    def file_name(self) -> str:
        return CHANGES_FILE

    def note(self, worktree: Path, text: str, at: datetime) -> None:
        with (worktree / CHANGES_FILE).open("a") as changes:
            changes.write(entry(text, at))

    def read(self, worktree: Path) -> str | None:
        try:
            return (worktree / CHANGES_FILE).read_text()
        except OSError:
            return None
