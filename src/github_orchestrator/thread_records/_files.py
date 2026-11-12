import logging
import re
import shutil
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from github_orchestrator.atomic_write import write_atomically
from github_orchestrator.domain import Pr, Repo, ThreadName
from github_orchestrator.thread_records._lock import locked
from github_orchestrator.thread_records.interface import PrRecords, UnreadableThread

log = logging.getLogger(__name__)

_KIND = re.compile(r"[a-z]+")


def _repo_dir(base: Path, repo: Repo) -> Path:
    return Path(base) / repo.owner / repo.name


def _suffix(kind: str) -> str:
    if _KIND.fullmatch(kind) is None:
        raise ValueError(f"invalid document kind {kind!r}")
    return f".{kind}"


def thread_dir(threads_dir: Path, pr: Pr) -> Path:
    return _repo_dir(threads_dir, pr.repo) / str(pr.number)


def _read(path: Path) -> bytes:
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise UnreadableThread(f"{path} is not a regular file")
        return path.read_bytes()
    except OSError as exc:
        raise UnreadableThread(f"{path} will not read: {exc}") from exc


@dataclass(frozen=True)
class DiskPrRecords:
    threads_dir: Path
    pr: Pr

    @property
    def _dir(self) -> Path:
        return thread_dir(self.threads_dir, self.pr)

    def _named(self, kind: str, key: str) -> Path:
        return self._dir / f"{ThreadName(key)}{_suffix(kind)}"

    def save(self, kind: str, key: str, document: bytes) -> None:
        write_atomically(self._named(kind, key), document)

    def load(self, kind: str, key: str) -> bytes | None:
        named = self._named(kind, key)
        try:
            named.lstat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise UnreadableThread(f"{named} will not read: {exc}") from exc
        return _read(named)

    def list(self, kind: str) -> dict[str, bytes | None]:
        suffix = _suffix(kind)
        if not self._dir.exists():
            return {}
        found = []
        for path in self._dir.glob(f"*{suffix}"):
            try:
                found.append((path.lstat().st_mtime, path.name, path))
            except OSError as exc:
                log.warning("Passing over %s: %s", path, exc)
        listed: dict[str, bytes | None] = {}
        for _, _, path in sorted(found):
            named = ThreadName.parse(path.stem)
            if named is None:
                log.warning("Passing over %s: it is not named by a thread key", path)
                continue
            key = named.key
            try:
                listed[key] = _read(path)
            except UnreadableThread as exc:
                log.warning("Standing in for the unreadable %s: %s", path, exc)
                listed[key] = None
        return listed

    @contextmanager
    def lock(self, name: str) -> Iterator[None]:
        with locked(self._dir / f"{ThreadName(name)}.lock"):
            yield

    def delete(self, kind: str, key: str) -> None:
        named = self._named(kind, key)
        try:
            if stat.S_ISDIR(named.lstat().st_mode):
                log.warning("Leaving %s, which reads as nothing kept: it is a directory", named)
                return
        except FileNotFoundError:
            return
        named.unlink(missing_ok=True)


class DiskThreadRecords:
    def __init__(self, threads_dir: Path):
        self._threads_dir = threads_dir

    def of(self, pr: Pr) -> PrRecords:
        return DiskPrRecords(self._threads_dir, pr)

    def forget(self, pr: Pr) -> bool:
        records = thread_dir(self._threads_dir, pr)
        if not records.exists():
            return True
        try:
            shutil.rmtree(records)
        except OSError:
            log.exception("failed to remove the thread records of %s at %s",
                          pr, records)
            return False
        return True
