import json
import logging
import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from github_orchestrator.board_api.interface import (
    CloneProgress,
    CloneState,
    RepoChoice,
    SetupProgress,
    WriteState,
)
from github_orchestrator.domain import Repo

log = logging.getLogger(__name__)

WriteWhole = Callable[[Path, bytes], None]

OPERATION = re.compile(r"setup_[0-9a-f]+")
LOGIN = re.compile(r"[A-Za-z0-9-]+")


class SetupFiles:
    def __init__(self, data_dir: Path, write_whole: WriteWhole) -> None:
        self._dir = data_dir / "setup"
        self._write_whole = write_whole

    def listed(self, login: str) -> tuple[datetime, list[RepoChoice]] | None:
        document = self._read(self._listing(login)) if LOGIN.fullmatch(login) else None
        if document is None:
            return None
        try:
            return datetime.fromisoformat(document["listed_at"]), [
                RepoChoice(Repo.parse(one["repo"]), bool(one["can_push"]),
                           bool(one["has_my_prs"]), str(one["default_branch"]))
                for one in document["repos"]]
        except (ValueError, KeyError, TypeError) as error:
            log.warning("could not read the listing of %s: %s", login, error)
            return None

    def keep_listing(self, login: str, at: datetime, choices: list[RepoChoice]) -> None:
        self._write_whole(self._listing(login), json.dumps({
            "listed_at": at.isoformat(),
            "repos": [{**asdict(one), "repo": str(one.repo)} for one in choices],
        }).encode())

    def progress(self, operation: str) -> SetupProgress | None:
        document = self._read(self._progress(operation)) if OPERATION.fullmatch(operation) else None
        if document is None:
            return None
        try:
            return SetupProgress(
                id=str(document["id"]), state=WriteState(document["state"]),
                clones=tuple(CloneProgress(Repo.parse(one["repo"]), str(one["path"]),
                                           CloneState(one["state"]), one["error"])
                             for one in document["clones"]),
                error=document["error"], archived=tuple(document["archived"]),
                kept_worktrees=tuple(document["kept_worktrees"]))
        except (ValueError, KeyError, TypeError) as error:
            log.warning("could not read the setup write %s: %s", operation, error)
            return None

    def record(self, progress: SetupProgress) -> None:
        self._write_whole(self._progress(progress.id), json.dumps({
            **asdict(progress),
            "clones": [{**asdict(one), "repo": str(one.repo)} for one in progress.clones],
        }).encode())

    def leave(self) -> None:
        self._write_whole(self._leave(), b"")

    def taken_leave(self) -> bool:
        try:
            self._leave().unlink()
        except FileNotFoundError:
            return False
        return True

    def _read(self, path: Path) -> Any:
        try:
            return json.loads(path.read_bytes())
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            log.warning("could not read %s: %s", path, error)
            return None

    def _listing(self, login: str) -> Path:
        return self._dir / "listed" / f"{login}.json"

    def _progress(self, operation: str) -> Path:
        return self._dir / "progress" / f"{operation}.json"

    def _leave(self) -> Path:
        return self._dir / "leave"
