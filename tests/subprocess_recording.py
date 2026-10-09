import base64
import errno
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

RECORDING = Path(__file__).with_name("recorded_subprocesses.json")
TMP = "<TMP>"
BASETEMP = "<BASETEMP>"
PYTHON = "<PYTHON>"

Rewrite = Callable[[str], str]
Stat = tuple[object, ...]
Delta = dict[str, dict[str, Any] | None]
RealRun = Callable[..., Any]


class RecordingMismatch(AssertionError):
    pass


def covers_whole_suite(args: Sequence[str], invocation_dir: str | Path, selected: int,
                       collected: int) -> bool:
    if selected != collected:
        return False
    whole = {RECORDING.parent.resolve(), RECORDING.parent.parent.resolve()}
    return all("::" not in a and (Path(invocation_dir) / a).resolve() in whole for a in args)


class _Scope:
    def __init__(self, name: str, bucket: dict[str, list[dict[str, Any]]], root: str | Path,
                 placeholder: str, replaying: bool) -> None:
        self.name = name
        self.bucket = bucket
        self.root = Path(root)
        self.replaying = replaying
        self.cursors: dict[str, int] = {}
        self._pairs = [
            (str(self.root), placeholder),
            (str(self.root.parent), BASETEMP),
            (sys.executable, PYTHON),
        ]

    def norm(self, text: str) -> str:
        for real, placeholder in self._pairs:
            text = text.replace(real, placeholder)
        return text

    def denorm(self, text: str) -> str:
        for real, placeholder in self._pairs:
            text = text.replace(placeholder, real)
        return text


def _encode(value: str | bytes | None, norm: Rewrite) -> str | dict[str, str] | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return {"b64": base64.b64encode(value).decode()}
    return norm(value)


def _decode(value: str | dict[str, str] | None, denorm: Rewrite) -> str | bytes | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return base64.b64decode(value["b64"])
    return denorm(value)


def _digest(value: str | bytes | None, norm: Rewrite) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = norm(value).encode()
    return hashlib.sha1(value).hexdigest()


HEAD_FILES = ("HEAD", "commondir", "packed-refs", "refs/heads/**/*", "worktrees/*/HEAD",
              "worktrees/*/commondir")


def _stat(path: str) -> Stat:
    stat = os.stat(path, follow_symlinks=False)
    return ("f", stat.st_mtime_ns, stat.st_size)


def _head_files(git_dir: str, root: Path, seen: dict[str, Stat]) -> None:
    for pattern in HEAD_FILES:
        for path in Path(git_dir).glob(pattern):
            try:
                if path.is_file():
                    seen[os.path.relpath(path, root)] = _stat(str(path))
            except FileNotFoundError:
                pass


def _snapshot(root: Path) -> dict[str, Stat]:
    seen: dict[str, Stat] = {}
    stack = [str(root)]
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except FileNotFoundError:
            continue
        for entry in entries:
            rel = os.path.relpath(entry.path, root)
            try:
                if entry.is_dir(follow_symlinks=False):
                    seen[rel] = ("d",)
                    if entry.name == ".git":
                        _head_files(entry.path, root, seen)
                    elif not entry.name.endswith(".git"):
                        stack.append(entry.path)
                else:
                    seen[rel] = _stat(entry.path)
            except FileNotFoundError:
                pass
    return seen


def _diff(before: dict[str, Stat], after: dict[str, Stat], root: Path, norm: Rewrite) -> Delta:
    delta: Delta = {}
    for rel, stat in after.items():
        if before.get(rel) == stat:
            continue
        if stat[0] == "d":
            delta[rel] = {"dir": True}
            continue
        try:
            raw = (root / rel).read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            continue
        try:
            delta[rel] = {"text": norm(raw.decode())}
        except UnicodeDecodeError:
            delta[rel] = {"b64": base64.b64encode(raw).decode()}
    for rel in before.keys() - after.keys():
        delta[rel] = None
    return delta


def _apply(delta: Delta, root: Path, denorm: Rewrite) -> None:
    for rel, value in sorted(delta.items()):
        path = root / rel
        if value is None:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        elif "dir" in value:
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if "b64" in value:
                path.write_bytes(base64.b64decode(value["b64"]))
            else:
                path.write_text(denorm(value["text"]))


class Recorder:
    def __init__(self, mode: str, real_run: RealRun) -> None:
        self.mode = mode
        self._real = real_run
        self._lock = threading.RLock()
        self._data: dict[str, Any] = json.loads(RECORDING.read_text()) if RECORDING.exists() else {}
        self._data.setdefault("templates", {})
        self._data.setdefault("tests", {})
        self._recorded: dict[str, dict[str, Any]] = {"templates": {}, "tests": {}}
        self._scope: _Scope | None = None
        self._test_scope: _Scope | None = None
        self.live_tests: set[str] = set()

    def begin_test(self, nodeid: str, tmp_path: Path) -> None:
        self._test_scope = self._scope = self._open("tests", nodeid, tmp_path, TMP)

    def end_test(self) -> None:
        self._scope = self._test_scope = None

    @contextmanager
    def template_scope(self, name: str, root: str | Path) -> Iterator[None]:
        outer = self._scope
        self._scope = self._open("templates", name, root, f"<TPL:{name}>")
        try:
            yield
        finally:
            self._scope = outer

    def _open(self, kind: str, name: str, root: str | Path, placeholder: str) -> _Scope:
        if self.mode == "record":
            bucket: dict[str, list[dict[str, Any]]] = {}
            self._recorded[kind][name] = bucket
            return _Scope(name, bucket, root, placeholder, False)
        found = self._data[kind].get(name)
        replaying = self.mode == "replay" and found is not None
        return _Scope(name, found or {}, root, placeholder, replaying)

    def run(self, argv: Any, *args: Any, **kwargs: Any) -> Any:
        scope = self._scope
        if scope is None or self.mode == "live":
            return self._real(argv, *args, **kwargs)
        if self.mode == "replay" and not scope.replaying:
            if self._test_scope is not None:
                self.live_tests.add(self._test_scope.name)
            return self._real(argv, *args, **kwargs)
        argv_list = list(argv) if isinstance(argv, (list, tuple)) else [argv]
        cwd = kwargs.get("cwd")
        key = json.dumps([
            [scope.norm(str(a)) for a in argv_list],
            scope.norm(str(cwd)) if cwd is not None else None,
            _digest(kwargs.get("input"), scope.norm),
        ])
        if self.mode == "record":
            return self._record(scope, key, argv, args, kwargs)
        return self._replay(scope, key, argv, kwargs)

    def _record(self, scope: _Scope, key: str, argv: Any, args: tuple[Any, ...],
                kwargs: dict[str, Any]) -> Any:
        with self._lock:
            before = _snapshot(scope.root)
            entry: dict[str, Any] = {"argv": json.loads(key)[0]}
            try:
                result = self._real(argv, *args, **kwargs)
            except subprocess.CalledProcessError as exc:
                entry.update(returncode=exc.returncode,
                             stdout=_encode(exc.stdout, scope.norm),
                             stderr=_encode(exc.stderr, scope.norm))
                raise
            except subprocess.TimeoutExpired:
                entry["error"] = "TimeoutExpired"
                raise
            except FileNotFoundError as exc:
                entry["error"] = "FileNotFoundError"
                entry["filename"] = scope.norm(str(exc.filename or ""))
                raise
            else:
                entry.update(returncode=result.returncode,
                             stdout=_encode(result.stdout, scope.norm),
                             stderr=_encode(result.stderr, scope.norm))
                return result
            finally:
                entry["fs"] = _diff(before, _snapshot(scope.root), scope.root, scope.norm)
                scope.bucket.setdefault(key, []).append(entry)

    def _replay(self, scope: _Scope, key: str, argv: Any,
                kwargs: dict[str, Any]) -> subprocess.CompletedProcess[Any]:
        with self._lock:
            entries = scope.bucket.get(key, [])
            index = scope.cursors.get(key, 0)
            if index >= len(entries):
                raise RecordingMismatch(
                    f"{scope.name} ran {json.loads(key)[0]} (call {index + 1}) but "
                    f"{RECORDING.name} has no result for it. The code under test runs "
                    f"a subprocess the recording does not know; re-record with "
                    f"`make record`, or run this test live with `--no-replay`."
                )
            scope.cursors[key] = index + 1
            entry = entries[index]
            _apply(entry.get("fs", {}), scope.root, scope.denorm)
        if entry.get("error") == "TimeoutExpired":
            timeout: Any = kwargs.get("timeout")
            raise subprocess.TimeoutExpired(argv, timeout)
        if entry.get("error") == "FileNotFoundError":
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
                                    scope.denorm(entry.get("filename", "")))
        stdout = _decode(entry["stdout"], scope.denorm)
        stderr = _decode(entry["stderr"], scope.denorm)
        if kwargs.get("check") and entry["returncode"]:
            raise subprocess.CalledProcessError(entry["returncode"], argv, stdout, stderr)
        return subprocess.CompletedProcess(argv, entry["returncode"], stdout, stderr)

    def save(self, collected: Iterable[str], full_run: bool) -> int:
        wanted = set(collected)
        tests = {n: b for n, b in self._data["tests"].items() if n in wanted or not full_run}
        tests.update(self._recorded["tests"])
        tests = {n: b for n, b in tests.items() if b}
        templates = dict(self._recorded["templates"])
        if not full_run:
            templates = {**self._data["templates"], **templates}
        RECORDING.write_text(json.dumps(
            {"templates": templates, "tests": tests},
            indent=1, sort_keys=True, ensure_ascii=False,
        ) + "\n")
        return len(tests)
