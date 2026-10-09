import itertools
import json
import logging
import os
import shutil
import time
from collections.abc import Callable, Iterator, Set
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from github_orchestrator.change_detection import PrClosed, PrEvent
from github_orchestrator.conversation import ThreadActivity
from github_orchestrator.domain import Pr, Repo
from github_orchestrator.pr_event_queue._responses import (
    found_again,
    recovered,
    respond,
    settling_of,
    touches_the_run,
    waiting_of,
)
from github_orchestrator.pr_event_queue._stored import Unreadable, document, item_of
from github_orchestrator.pr_event_queue.interface import (
    Entry,
    Queue,
    Queued,
    Response,
    State,
    Waiting,
)

_enqueue_counter = itertools.count()

logger = logging.getLogger(__name__)

_PENDING = ".json"
_IN_FLIGHT = ".processing"
_FAILED = ".failed-"
_TORN_DOWN = "pr-closed.done"


def _queue_dir_for_pr(queues_dir: Path, pr: Pr) -> Path:
    return Path(queues_dir) / pr.repo.owner / pr.repo.name / str(pr.number)


def _parse_queue_path(queues_dir: Path, path: Path) -> Pr | None:
    try:
        rel = Path(path).relative_to(queues_dir)
    except ValueError:
        return None
    if len(rel.parts) < 3:
        return None
    owner, name, pr_str = rel.parts[:3]
    try:
        return Pr(Repo(owner, name), int(pr_str))
    except ValueError:
        return None


def _iter_queue_dirs(queues_dir: Path) -> Iterator[Path]:
    base = Path(queues_dir)
    if not base.exists():
        return iter(())
    return (p for p in base.glob("*/*/*") if p.is_dir())


def _load(file: Path) -> Queued:
    try:
        return item_of(json.loads(file.read_text()))
    except (json.JSONDecodeError, OSError) as exc:
        raise Unreadable(str(exc)) from exc


def enqueue(
    queues_dir: Path,
    pr: Pr,
    item: Queued,
) -> None:
    event_type = item.kind
    queue_dir = _queue_dir_for_pr(queues_dir, pr)
    queue_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.time_ns()
    discriminator = f"{os.getpid()}-{next(_enqueue_counter)}"
    event_data = document(pr, item)

    tmp_file = queue_dir / f".{timestamp}-{discriminator}.tmp"
    final_file = queue_dir / f"{timestamp}-{discriminator}-{event_type}{_PENDING}"

    try:
        tmp_file.write_text(json.dumps(event_data))
        tmp_file.rename(final_file)
        logger.debug("Enqueued %s for %s -> %s", event_type, pr, final_file.name)
    except Exception:
        logger.error("Failed to enqueue %s for %s", event_type, pr, exc_info=True)
        tmp_file.unlink(missing_ok=True)
        raise


def list_pending(
    queues_dir: Path,
    pr: Pr,
) -> list[Queued]:
    queue_dir = _queue_dir_for_pr(queues_dir, pr)

    if not queue_dir.exists():
        return []

    event_files = sorted(queue_dir.glob(f"*{_PENDING}"))
    events = []

    for file in event_files:
        try:
            events.append(_load(file))
        except Unreadable as exc:
            logger.warning("Skipping unreadable queue file %s: %s", file, exc)

    logger.debug("list_pending %s: %d events", pr, len(events))
    return events


def list_in_flight(queues_dir: Path, pr: Pr) -> list[Queued]:
    events = []
    for file in sorted(_queue_dir_for_pr(queues_dir, pr).glob(f"*{_IN_FLIGHT}")):
        try:
            events.append(_load(file))
        except Unreadable as exc:
            logger.warning("Skipping unreadable queue file %s: %s", file, exc)
    return events


def pop(
    queues_dir: Path,
    pr: Pr,
    eligible: Optional[Callable[[Queued], bool]] = None,
) -> Optional[tuple[Queued, Path]]:
    queue_dir = _queue_dir_for_pr(queues_dir, pr)
    event_files = sorted(queue_dir.glob(f"*{_PENDING}"))

    event_file = None
    event_data = None
    for thread in event_files:
        try:
            data = _load(thread)
        except Unreadable as exc:
            logger.warning("Corrupt queue file %s, deleting: %s", thread, exc)
            try:
                thread.unlink()
            except OSError:
                pass
            continue
        if eligible is not None and not eligible(data):
            continue
        event_data = data
        event_file = thread
        break

    if event_file is None or event_data is None:
        return None

    processing_path = event_file.with_suffix(_IN_FLIGHT)
    event_file.rename(processing_path)

    logger.info("Popped %s for %s from %s", event_data.kind, pr, event_file.name)
    return event_data, processing_path


def complete(processing_path: Path) -> None:
    try:
        processing_path.unlink()
        logger.debug("Completed event: %s", processing_path.name)
    except FileNotFoundError:
        logger.warning("Processing file already gone when completing: %s", processing_path)


def mark_failed(processing_path: Path) -> Path:
    failed_path = processing_path.with_suffix(f"{_FAILED}{time.time_ns()}")
    try:
        processing_path.rename(failed_path)
    except FileNotFoundError:
        logger.warning("Processing file vanished before mark_failed: %s", processing_path)
        return failed_path
    logger.warning("Marked failed: %s -> %s", processing_path.name, failed_path.name)
    return failed_path


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _moment(ns: int) -> datetime:
    return _EPOCH + timedelta(microseconds=ns // 1000)


def _ns(when: datetime) -> int:
    return (when - _EPOCH) // timedelta(microseconds=1) * 1000


def _queued_at(file: Path) -> datetime:
    stamp = file.name.split("-", 1)[0]
    if stamp.isdigit():
        return _moment(int(stamp))
    return _moment(file.stat().st_mtime_ns)


def _entries(pr: Pr, files: list[Path], state: State) -> list[Entry]:
    entries = []
    for file in files:
        try:
            entries.append(Entry(pr, _load(file), _queued_at(file), state))
        except Unreadable as exc:
            entries.append(Entry(pr, None, _queued_at(file), state, str(exc)))
    return entries


def contents(queue_dir: Path, pr: Pr) -> Queue:
    return Queue(pr, (
        *_entries(pr, sorted(queue_dir.glob(f"*{_IN_FLIGHT}")), State.IN_FLIGHT),
        *_entries(pr, sorted(queue_dir.glob(f"*{_PENDING}")), State.PENDING),
    ))


def _recover(pr: Pr, orphan: Path, target: Path) -> None:
    try:
        event = _load(orphan)
    except Unreadable:
        orphan.rename(target)
        return
    back = recovered(event)
    if back == event:
        orphan.rename(target)
        return
    tmp_file = orphan.with_name(f".{orphan.name}.tmp")
    tmp_file.write_text(json.dumps(document(pr, back)))
    tmp_file.rename(target)
    orphan.unlink()


def recover_orphans(queues_dir: Path, pr: Pr) -> None:
    for orphan in _queue_dir_for_pr(queues_dir, pr).glob(f"*{_IN_FLIGHT}"):
        target = orphan.with_suffix(_PENDING)
        try:
            _recover(pr, orphan, target)
            logger.warning("Recovered orphan processing file %s -> %s", orphan.name, target.name)
        except OSError as exc:
            logger.warning("Could not recover orphan %s: %s", orphan, exc)


def drop_in_flight(queues_dir: Path, pr: Pr) -> None:
    for processing_file in _queue_dir_for_pr(queues_dir, pr).glob(f"*{_IN_FLIGHT}"):
        try:
            processing_file.unlink()
        except OSError:
            logger.warning("Failed to remove %s", processing_file, exc_info=True)


def mark_torn_down(queues_dir: Path, pr: Pr) -> None:
    queue_dir = _queue_dir_for_pr(queues_dir, pr)
    queue_dir.mkdir(parents=True, exist_ok=True)
    (queue_dir / _TORN_DOWN).write_text("")


def is_torn_down(queues_dir: Path, pr: Pr) -> bool:
    return (_queue_dir_for_pr(queues_dir, pr) / _TORN_DOWN).exists()


def failed_since(queues_dir: Path, when: datetime) -> list[Entry]:
    since_ns = _ns(when)
    failures = []
    for directory in sorted(_iter_queue_dirs(queues_dir)):
        parsed = _parse_queue_path(queues_dir, directory)
        if parsed is None:
            continue
        failed = [path for path in sorted(directory.glob(f"*{_FAILED}*"))
                  if int(path.suffix.removeprefix(_FAILED)) >= since_ns]
        failures.extend(_entries(parsed, failed, State.FAILED))
    return failures


class _TakenFile:
    def __init__(self, queues_dir: Path, pr: Pr, event: Queued,
                 processing_path: Path, response: Response) -> None:
        self._queues_dir = queues_dir
        self._pr = pr
        self._event = event
        self._processing_path = processing_path
        self._response = response

    @property
    def response(self) -> Response:
        return self._response

    def done(self) -> None:
        if isinstance(self._event, PrClosed):
            mark_torn_down(self._queues_dir, self._pr)
            logger.info("Consumed pr-closed for %s; wrote teardown tombstone",
                        self._pr)
        complete(self._processing_path)

    def failed(self) -> None:
        mark_failed(self._processing_path)


def _queue_order(queue: tuple[Path, Pr]) -> tuple[str, ...]:
    return queue[0].parts


class DiskPrEventQueue:
    def __init__(self, queues_dir: Path) -> None:
        self._queues_dir = queues_dir

    def add(self, pr: Pr, event: PrEvent) -> None:
        enqueue(self._queues_dir, pr, event)

    def add_thread_activity(self, pr: Pr, activity: ThreadActivity) -> None:
        held = (list_pending(self._queues_dir, pr)
                + list_in_flight(self._queues_dir, pr))
        if found_again(activity, held):
            logger.info("%s: the %s found again is already waiting; not adding it twice",
                        pr, activity.kind)
            return
        enqueue(self._queues_dir, pr, activity)

    def next(
        self, pr: Pr, *, is_author: bool, agents_enabled: bool,
        busy: bool = False,
    ) -> _TakenFile | None:
        def eligible(event: Queued) -> bool:
            return not touches_the_run(event, is_author, agents_enabled)

        taken = pop(self._queues_dir, pr, eligible=eligible if busy else None)
        if taken is None:
            return None
        event, processing_path = taken
        try:
            response = respond(
                pr, event, is_author=is_author, agents_enabled=agents_enabled,
                pending=lambda: list_pending(self._queues_dir, pr),
            )
        except Exception:
            mark_failed(processing_path)
            raise
        return _TakenFile(self._queues_dir, pr, event, processing_path, response)

    def waiting(self, pr: Pr) -> Waiting:
        pending = list_pending(self._queues_dir, pr)
        return waiting_of(pending, pending + list_in_flight(self._queues_dir, pr))

    def settling(self, pr: Pr) -> bool:
        return settling_of(list_pending(self._queues_dir, pr)
                           + list_in_flight(self._queues_dir, pr))

    def queues(self) -> list[Queue]:
        found = []
        for directory in _iter_queue_dirs(self._queues_dir):
            parsed = _parse_queue_path(self._queues_dir, directory)
            if parsed is None:
                if any(directory.glob(f"*{_IN_FLIGHT}")) or any(directory.glob(f"*{_PENDING}")):
                    logger.warning("Skipping unparseable queue dir: %s", directory)
                continue
            found.append((directory, parsed))
        return [contents(directory, pr)
                for directory, pr in sorted(found, key=_queue_order)]

    def failed_since(self, when: datetime) -> list[Entry]:
        return failed_since(self._queues_dir, when)

    def recover(self, pr: Pr) -> None:
        recover_orphans(self._queues_dir, pr)

    def drop_in_flight(self, pr: Pr) -> None:
        drop_in_flight(self._queues_dir, pr)

    def forget(self, pr: Pr) -> bool:
        queue_dir = _queue_dir_for_pr(self._queues_dir, pr)
        if not queue_dir.exists():
            return True
        try:
            shutil.rmtree(queue_dir)
        except OSError:
            logger.exception("Failed to remove the queue of %s at %s", pr, queue_dir)
            return False
        return True

    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]:
        archived: list[Path] = []
        if not self._queues_dir.exists():
            return archived
        for owner_dir in self._queues_dir.iterdir():
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

    def is_torn_down(self, pr: Pr) -> bool:
        return is_torn_down(self._queues_dir, pr)
