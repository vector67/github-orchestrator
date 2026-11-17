import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Protocol

from github_orchestrator.atomic_write import write_atomically
from github_orchestrator.domain import AGENT_CHANGES_FILE, Pr, Repo
from github_orchestrator.working_copies._layout import repo_dir
from github_orchestrator.working_copies.interface import CleanUp

log = logging.getLogger(__name__)

AGENTS_OWN = frozenset({AGENT_CHANGES_FILE})


@dataclass(frozen=True)
class Asked:
    clean_up: CleanUp
    allowed: bool


class Shelf(Protocol):
    def read(self, pr: Pr) -> Asked | None: ...

    def write(self, pr: Pr, asked: Asked) -> None: ...

    def drop(self, pr: Pr) -> None: ...

    def prs(self) -> tuple[Pr, ...]: ...


def not_the_agents(paths: list[str]) -> tuple[str, ...]:
    return tuple(sorted({path for path in paths if path not in AGENTS_OWN}))


def changed_paths(porcelain: str) -> list[str]:
    entries = iter(porcelain.split("\0"))
    paths: list[str] = []
    for entry in entries:
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            next(entries, None)
    return paths


class CleanUps:
    def __init__(self, shelf: Shelf) -> None:
        self._shelf = shelf

    def asks(self, pr: Pr, worktree: str | None, leftovers: tuple[str, ...] | None) -> bool:
        if worktree is None or leftovers == ():
            self._shelf.drop(pr)
            return False
        asked = self._shelf.read(pr)
        if asked is not None and asked.allowed:
            return False
        until = None if asked is None else asked.clean_up.dismissed_until
        self._shelf.write(pr, Asked(CleanUp(worktree, leftovers or (), until), allowed=False))
        return True

    def clean_up(self, pr: Pr) -> CleanUp | None:
        asked = self._shelf.read(pr)
        return None if asked is None or asked.allowed else asked.clean_up

    def asked(self) -> tuple[Pr, ...]:
        return tuple(pr for pr in self._shelf.prs() if self.clean_up(pr) is not None)

    def allow(self, pr: Pr) -> bool:
        asked = self._shelf.read(pr)
        if asked is None:
            return False
        self._shelf.write(pr, replace(asked, allowed=True))
        return True

    def dismiss(self, pr: Pr, until: datetime) -> bool:
        asked = self._shelf.read(pr)
        if asked is None:
            return False
        self._shelf.write(pr, replace(asked, clean_up=replace(asked.clean_up,
                                                              dismissed_until=until)))
        return True

    def forget(self, pr: Pr) -> None:
        self._shelf.drop(pr)


class MemoryShelf:
    def __init__(self) -> None:
        self._asked: dict[Pr, Asked] = {}

    def read(self, pr: Pr) -> Asked | None:
        return self._asked.get(pr)

    def write(self, pr: Pr, asked: Asked) -> None:
        self._asked[pr] = asked

    def drop(self, pr: Pr) -> None:
        self._asked.pop(pr, None)

    def prs(self) -> tuple[Pr, ...]:
        return tuple(self._asked)


class DiskShelf:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def read(self, pr: Pr) -> Asked | None:
        try:
            stored = json.loads(self._path(pr).read_text())
            until = stored["dismissed_until"]
            return Asked(CleanUp(worktree=str(stored["worktree"]),
                                 files=tuple(str(path) for path in stored["files"]),
                                 dismissed_until=None if until is None
                                 else datetime.fromisoformat(until)),
                         allowed=bool(stored["allowed"]))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("could not read the clean-up asked of %s: %s", pr, exc)
            return None

    def write(self, pr: Pr, asked: Asked) -> None:
        until = asked.clean_up.dismissed_until
        write_atomically(self._path(pr), json.dumps({
            "worktree": asked.clean_up.worktree,
            "files": list(asked.clean_up.files),
            "dismissed_until": None if until is None else until.isoformat(),
            "allowed": asked.allowed,
        }).encode())

    def drop(self, pr: Pr) -> None:
        self._path(pr).unlink(missing_ok=True)

    def prs(self) -> tuple[Pr, ...]:
        found: list[Pr] = []
        for path in sorted(self._directory.glob("*/*/*.json")):
            try:
                found.append(Pr(Repo(path.parent.parent.name, path.parent.name), int(path.stem)))
            except ValueError:
                continue
        return tuple(found)

    def _path(self, pr: Pr) -> Path:
        return repo_dir(self._directory, pr.repo) / f"{pr.number}.json"
