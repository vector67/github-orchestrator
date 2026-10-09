import builtins
import logging
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

from github_orchestrator.domain import Pr, Repo
from github_orchestrator.thread_records._lock import locked
from github_orchestrator.thread_records.interface import PrRecords, UnreadableThread

log = logging.getLogger(__name__)

_KIND = re.compile(r"[a-z]+")


def _repo_dir(base: Path, repo: Repo) -> Path:
    return Path(base) / repo.owner / repo.name


def _slug(key: str) -> str:
    if not key or key.strip(".") == "":
        raise ValueError(f"invalid thread key {key!r}")
    return quote(key, safe="")


def _suffix(kind: str) -> str:
    if _KIND.fullmatch(kind) is None:
        raise ValueError(f"invalid document kind {kind!r}")
    return f".{kind}"


def thread_dir(threads_dir: Path, pr: Pr) -> Path:
    return _repo_dir(threads_dir, pr.repo) / str(pr.number)


def _write_atomically(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="wb", dir=path.parent, suffix=".tmp", delete=False
    )
    tmp_path = Path(tmp.name)
    try:
        try:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        tmp_path.replace(path)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


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

    def _named(self, kind: str, key: str) -> builtins.list[Path]:
        suffix = _suffix(kind)
        direct = self._dir / f"{_slug(key)}{suffix}"
        try:
            direct.lstat()
            return [direct]
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise UnreadableThread(f"{direct} will not read: {exc}") from exc
        if not self._dir.exists():
            return []
        return sorted(path for path in self._dir.glob(f"*{suffix}")
                      if unquote(path.stem) == key)

    def save(self, kind: str, key: str, document: bytes) -> None:
        _write_atomically(self._dir / f"{_slug(key)}{_suffix(kind)}", document)

    def load(self, kind: str, key: str) -> bytes | None:
        named = self._named(kind, key)
        if not named:
            return None
        return _read(named[0])

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
            try:
                listed[unquote(path.stem)] = _read(path)
            except UnreadableThread as exc:
                log.warning("Standing in for the unreadable %s: %s", path, exc)
                listed[unquote(path.stem)] = None
        return listed

    @contextmanager
    def lock(self, name: str) -> Iterator[None]:
        with locked(self._dir / f"{_slug(name)}.lock"):
            yield

    def delete(self, kind: str, key: str) -> None:
        suffix = _suffix(kind)
        if not self._dir.exists():
            return
        for path in self._dir.glob(f"*{suffix}"):
            if unquote(path.stem) == key:
                path.unlink(missing_ok=True)


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
