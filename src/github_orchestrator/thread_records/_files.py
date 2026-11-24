from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from github_orchestrator.atomic_write import locked, write_atomically
from github_orchestrator.domain import Pr, Repo, ThreadName
from github_orchestrator.thread_records.interface import PrRecords, UnreadableThread

log = logging.getLogger(__name__)

_KIND = re.compile(r"[a-z]+")
_TIMESTAMP_TICK_NS = 10_000_000


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
class _Stamp:
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int

    @classmethod
    def of(cls, status: os.stat_result) -> _Stamp:
        return cls(status.st_ino, status.st_size, status.st_mtime_ns, status.st_ctime_ns)


@dataclass(frozen=True)
class _Seen:
    stamp: _Stamp
    key: str
    document: bytes


_Listing = tuple[Path, str]


@dataclass(frozen=True)
class DiskPrRecords:
    threads_dir: Path
    pr: Pr
    seen: dict[_Listing, dict[str, _Seen]]

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
        listing = (self._dir, suffix)
        if not self._dir.exists():
            self.seen.pop(listing, None)
            return {}
        before = self.seen.get(listing, {})
        now = time.time_ns()
        found = []
        for path in self._dir.glob(f"*{suffix}"):
            try:
                found.append((path.lstat(), path.name, path))
            except OSError as exc:
                log.warning("Passing over %s: %s", path, exc)
        listed: dict[str, bytes | None] = {}
        settled: dict[str, _Seen] = {}
        for status, name, path in sorted(found, key=lambda each: (each[0].st_mtime, each[1])):
            stamp = _Stamp.of(status)
            seen = before.get(name)
            if seen is not None and seen.stamp == stamp:
                settled[name] = seen
                listed[seen.key] = seen.document
                continue
            named = ThreadName.parse(path.stem)
            if named is None:
                log.warning("Passing over %s: it is not named by a thread key", path)
                continue
            key = named.key
            try:
                document = _read(path)
            except UnreadableThread as exc:
                log.warning("Standing in for the unreadable %s: %s", path, exc)
                listed[key] = None
                continue
            listed[key] = document
            if stamp.ctime_ns + _TIMESTAMP_TICK_NS <= now:
                settled[name] = _Seen(stamp, key, document)
        self.seen[listing] = settled
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
        self._seen: dict[_Listing, dict[str, _Seen]] = {}

    def of(self, pr: Pr) -> PrRecords:
        return DiskPrRecords(self._threads_dir, pr, self._seen)

    def forget(self, pr: Pr) -> bool:
        records = thread_dir(self._threads_dir, pr)
        for listing in list(self._seen):
            if listing[0] == records:
                self._seen.pop(listing, None)
        if not records.exists():
            return True
        try:
            shutil.rmtree(records)
        except OSError:
            log.exception("failed to remove the thread records of %s at %s",
                          pr, records)
            return False
        return True
