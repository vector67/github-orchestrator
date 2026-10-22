import fcntl
import json
import os
import tempfile
from collections.abc import Iterator, Set
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from github_orchestrator.domain import Pr, Repo, UtcClock
from github_orchestrator.pr_summaries._due import due
from github_orchestrator.pr_summaries.interface import Summary


def _moment(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)


def _text(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat()


def _decoded(document: bytes) -> Summary:
    fields = json.loads(document)
    return Summary(wanted=_moment(fields.get("wanted")),
                   answered=_moment(fields.get("answered")),
                   head_sha=fields.get("head_sha"),
                   started=_moment(fields.get("started")),
                   finished=_moment(fields.get("finished")),
                   exit_status=fields.get("exit_status"),
                   stderr=fields.get("stderr"),
                   markdown=fields.get("markdown"),
                   mismatches=fields.get("mismatches"))


def _encoded(summary: Summary) -> bytes:
    return json.dumps({"wanted": _text(summary.wanted),
                       "answered": _text(summary.answered),
                       "head_sha": summary.head_sha,
                       "started": _text(summary.started),
                       "finished": _text(summary.finished),
                       "exit_status": summary.exit_status,
                       "stderr": summary.stderr,
                       "markdown": summary.markdown,
                       "mismatches": summary.mismatches}, indent=2).encode()


def _read(path: Path) -> Summary | None:
    try:
        return _decoded(path.read_bytes())
    except ValueError:
        return None


def working_folder(summaries_dir: Path, pr: Pr) -> Path:
    return summaries_dir / pr.repo.owner / pr.repo.name / str(pr.number)


def _replaced(path: Path, content: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as written:
        written.write(content)
        written.flush()
        os.fsync(written.fileno())
    Path(written.name).replace(path)


class DiskPrSummaries:
    def __init__(self, summaries_dir: Path, clock: UtcClock) -> None:
        self._dir = summaries_dir
        self._clock = clock

    def want(self, pr: Pr) -> None:
        with self._locked(pr):
            stored = self.load(pr) or Summary()
            _replaced(self._file(pr), _encoded(replace(stored, wanted=self._clock())))

    def load(self, pr: Pr) -> Summary | None:
        path = self._file(pr)
        if not path.exists():
            return None
        return _read(path)

    def save(self, pr: Pr, summary: Summary) -> None:
        with self._locked(pr):
            stored = self.load(pr) or Summary()
            _replaced(self._file(pr), _encoded(replace(summary, wanted=stored.wanted)))

    def due(self, in_flight: Set[Pr]) -> list[Pr]:
        stored = {}
        for path in self._dir.glob("*/*/*.json"):
            if not path.stem.isdigit():
                continue
            summary = _read(path)
            if summary is None:
                continue
            stored[Pr(Repo(path.parent.parent.name, path.parent.name), int(path.stem))] = summary
        return due(stored, in_flight)

    @contextmanager
    def _locked(self, pr: Pr) -> Iterator[None]:
        lock = self._file(pr).with_suffix(".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def _file(self, pr: Pr) -> Path:
        return working_folder(self._dir, pr).with_suffix(".json")
