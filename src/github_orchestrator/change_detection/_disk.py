import json
import logging
import os
import tempfile
from collections.abc import Iterator, Set
from pathlib import Path
from typing import Any

from github_orchestrator.change_detection._facts import facts_of
from github_orchestrator.change_detection._rules import (
    advance,
    closing,
    ended,
    is_closing,
)
from github_orchestrator.change_detection._stored import current_form
from github_orchestrator.change_detection.interface import (
    Facts,
    Poll,
    PrClosed,
    PrEvent,
    Stored,
)
from github_orchestrator.domain import Pr, Repo, UtcClock

log = logging.getLogger(__name__)


def _repo_dir(base: Path, repo: Repo) -> Path:
    return Path(base) / repo.owner / repo.name


class CorruptSnapshot(Exception):
    pass


def _read(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise CorruptSnapshot(str(exc)) from exc
    if not isinstance(loaded, dict):
        raise CorruptSnapshot(f"expected an object, found {type(loaded).__name__}")
    return current_form(loaded)


def _write(target: Path, snapshot: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", dir=target.parent, suffix=".tmp", delete=False
    )
    tmp_path = Path(tmp.name)
    try:
        try:
            json.dump(snapshot, tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        tmp_path.replace(target)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


class DiskChangeDetection:
    def __init__(self, state_dir: Path, account: str, poll_interval: int,
                 clock: UtcClock) -> None:
        self._state_dir = state_dir
        self._account = account
        self._poll_interval = poll_interval
        self._clock = clock

    def _file(self, pr: Pr) -> Path:
        return _repo_dir(self._state_dir, pr.repo) / f"{pr.number}.json"

    def _files(self) -> Iterator[Path]:
        if not self._state_dir.exists():
            return iter(())
        return self._state_dir.glob("*/*/*.json")

    def _pr_of(self, path: Path) -> Pr | None:
        try:
            return Pr(Repo(path.parent.parent.name, path.parent.name), int(path.stem))
        except ValueError:
            return None

    def advance(self, pr: Pr, poll: Poll, pending_ci_checks: set[str]) -> list[PrEvent]:
        step = advance(pr, self._last(pr), poll, pending_ci_checks,
                       self._clock().isoformat(), account=self._account,
                       poll_interval=self._poll_interval)
        self._save(pr, step.snapshot)
        return step.events

    def _save(self, pr: Pr, snapshot: dict[str, Any]) -> None:
        _write(self._file(pr), snapshot)

    def ended(self, *, still_open: bool, merged: bool) -> PrClosed:
        return ended(still_open=still_open, merged=merged)

    def facts(self, pr: Pr) -> Facts | None:
        snapshot = self._last(pr)
        return None if snapshot is None else facts_of(snapshot, self._account)

    def _last(self, pr: Pr) -> dict[str, Any] | None:
        path = self._file(pr)
        if not path.exists():
            return None
        try:
            return _read(path)
        except CorruptSnapshot:
            log.warning("Corrupt or unreadable state for %s at %s; treating as missing",
                        pr, path)
            return None

    def tracked(self) -> list[Pr]:
        found = []
        for path in self._files():
            parsed = self._pr_of(path)
            if parsed is not None:
                found.append(parsed)
        return found

    def stored(self) -> list[Stored]:
        listed = []
        for pr in sorted(self.tracked()):
            try:
                snapshot = _read(self._file(pr))
            except CorruptSnapshot as exc:
                listed.append(Stored(pr, None, str(exc)))
                continue
            listed.append(Stored(pr, facts_of(snapshot, self._account), None))
        return listed

    def closing(self, pr: Pr) -> bool:
        return is_closing(self._last(pr))

    def close(self, pr: Pr) -> None:
        self._save(pr, closing(self._last(pr)))

    def forget(self, pr: Pr) -> bool:
        path = self._file(pr)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.exception("failed to remove the snapshot of %s at %s", pr, path)
            return False
        return True

    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]:
        archived: list[Path] = []
        if not self._state_dir.exists():
            return archived
        for owner_dir in self._state_dir.iterdir():
            if not owner_dir.is_dir():
                continue
            for repo_dir in list(owner_dir.iterdir()):
                if not repo_dir.is_dir():
                    continue
                if (owner_dir.name, repo_dir.name) in {(repo.owner, repo.name) for repo in keep}:
                    continue
                dest_parent = into / owner_dir.name
                dest_parent.mkdir(parents=True, exist_ok=True)
                dest = dest_parent / repo_dir.name
                repo_dir.rename(dest)
                archived.append(dest)
        return archived
