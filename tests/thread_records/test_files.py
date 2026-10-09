import errno
import fcntl
import os
import threading
from pathlib import Path

import pytest

from github_orchestrator.thread_records import UnreadableThread
from tests.builders import a_pr
from tests.disk_layout import (
    review_lock_file,
    thread_action_file,
    thread_dir,
    thread_file,
    thread_intent_file,
    thread_lock_file,
    thread_reply_file,
)
from tests.thread_records.support import (
    KEY,
    PR,
    REPO,
    disk_thread_records,
)

THE_PR = a_pr(PR, REPO)


def _records(tmp_path):
    return disk_thread_records(tmp_path).of(THE_PR)


def _write(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_each_kind_of_document_is_the_file_the_board_has_always_kept(tmp_path):
    records = _records(tmp_path)
    for kind in ("json", "intent", "reply", "action", "review"):
        records.save(kind, KEY, kind.encode())
    records.save("cursor", "poll", b"{}")

    assert thread_file(tmp_path, THE_PR, KEY).read_bytes() == b"json"
    assert thread_intent_file(tmp_path, THE_PR, KEY).read_bytes() == b"intent"
    assert thread_reply_file(tmp_path, THE_PR, KEY).read_bytes() == b"reply"
    assert thread_action_file(tmp_path, THE_PR, KEY).read_bytes() == b"action"
    assert (thread_dir(tmp_path, THE_PR) / f"{KEY}.review").read_bytes() == b"review"
    assert (thread_dir(tmp_path, THE_PR) / "poll.cursor").read_bytes() == b"{}"


def test_the_files_already_on_disk_load_by_their_kind_and_key(tmp_path):
    _write(thread_file(tmp_path, THE_PR, KEY), b'{"version": 2}')
    _write(thread_dir(tmp_path, THE_PR) / "poll.cursor", b"{}")

    records = _records(tmp_path)

    assert records.load("json", KEY) == b'{"version": 2}'
    assert records.load("cursor", "poll") == b"{}"


PRESENT_BUT_UNREADABLE = ("dangling-symlink", "symlink-loop", "a-fifo")


def _present_but_unreadable(tmp_path, how, key=KEY):
    path = thread_file(tmp_path, THE_PR, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    if how == "symlink-loop":
        path.symlink_to(path)
    elif how == "dangling-symlink":
        path.symlink_to(path.parent / "nothing-is-here.json")
    else:
        os.mkfifo(path)
    return path


def _answered(work, path, seconds=2.0):
    outcome = []

    def run():
        try:
            outcome.append((True, work()))
        except BaseException as exc:
            outcome.append((False, exc))

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        try:
            os.close(os.open(path, os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass
        worker.join(seconds)
        return None
    return outcome[0]


@pytest.mark.parametrize("how", PRESENT_BUT_UNREADABLE)
def test_a_document_that_is_there_and_will_not_read_is_never_taken_for_absent(
    tmp_path, how,
):
    path = _present_but_unreadable(tmp_path, how)
    records = _records(tmp_path)

    answer = _answered(lambda: records.load("json", KEY), path)

    assert answer is not None, "load never came back"
    returned, value = answer
    assert not returned, f"load called a file that is there {value!r}"
    assert isinstance(value, UnreadableThread), value


@pytest.mark.parametrize("how", PRESENT_BUT_UNREADABLE)
def test_a_document_that_is_there_and_will_not_read_is_listed_as_unreadable(
    tmp_path, how,
):
    path = _present_but_unreadable(tmp_path, how)
    records = _records(tmp_path)
    records.save("json", "readable", b"{}")

    answer = _answered(lambda: records.list("json"), path)

    assert answer is not None, "the listing never came back"
    returned, listed = answer
    assert returned, listed
    assert listed == {"readable": b"{}", KEY: None}


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads anything")
def test_a_document_whose_file_will_not_open_is_unreadable(tmp_path):
    records = _records(tmp_path)
    records.save("intent", KEY, b"approve")
    thread_intent_file(tmp_path, THE_PR, KEY).chmod(0)

    with pytest.raises(UnreadableThread):
        records.load("intent", KEY)
    assert records.list("intent") == {KEY: None}


def test_a_document_is_listed_under_the_key_its_file_name_spells(tmp_path):
    _write(thread_file(tmp_path, THE_PR, "MDI0OlB1bGx/UmV2aWV3="))

    assert list(_records(tmp_path).list("json")) == ["MDI0OlB1bGx/UmV2aWV3="]


def test_a_document_is_saved_under_its_pr_and_named_by_its_encoded_key(tmp_path):
    _records(tmp_path).save("json", "MDI0OlB1bGx/UmV2aWV3=", b"{}")

    assert [p.name for p in (tmp_path / "owner" / "name" / "5").iterdir()] == [
        "MDI0OlB1bGx%2FUmV2aWV3%3D.json"]


def test_two_keys_that_differ_only_by_an_encoded_slash_are_two_documents(tmp_path):
    _records(tmp_path).save("json", "a/b", b"slash")
    _records(tmp_path).save("json", "a%2Fb", b"percent")

    assert _records(tmp_path).list("json") == {"a/b": b"slash", "a%2Fb": b"percent"}


def test_a_key_that_merely_starts_with_dots_is_a_document_of_its_own(tmp_path):
    _records(tmp_path).save("json", "..PRRT_kwDO", b"mine")

    assert _records(tmp_path).load("json", "..PRRT_kwDO") == b"mine"
    assert _records(tmp_path).load("json", "PRRT_kwDO") is None


@pytest.mark.parametrize("key", ["", ".."])
def test_a_key_that_names_no_file_of_its_own_is_refused(tmp_path, key):
    with pytest.raises(ValueError):
        _records(tmp_path).save("json", key, b"{}")


@pytest.mark.parametrize("kind", ["../json", "JSON"])
def test_a_kind_that_names_no_file_suffix_is_refused(tmp_path, kind):
    with pytest.raises(ValueError):
        _records(tmp_path).save(kind, KEY, b"{}")


STRAY_NAMES = ("PRRT%zz",)


@pytest.mark.parametrize("stem", STRAY_NAMES)
def test_a_file_no_writer_of_ours_named_is_read_where_it_lies(tmp_path, stem):
    _write(thread_dir(tmp_path, THE_PR) / f"{stem}.intent", b"approve")
    records = _records(tmp_path)

    key, = records.list("intent")

    assert records.load("intent", key) == b"approve"


@pytest.mark.parametrize("stem", STRAY_NAMES)
def test_a_file_no_writer_of_ours_named_is_deleted_where_it_lies(tmp_path, stem):
    stray = _write(thread_dir(tmp_path, THE_PR) / f"{stem}.intent", b"approve")
    records = _records(tmp_path)

    key, = records.list("intent")
    records.delete("intent", key)

    assert not stray.exists()
    assert records.list("intent") == {}


def test_a_save_that_dies_mid_write_keeps_the_document_that_was_there(
    tmp_path, monkeypatch,
):
    records = _records(tmp_path)
    records.save("json", KEY, b"the first gist")

    def boom(self, target):
        raise OSError("no space left on device")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError):
        records.save("json", KEY, b"the second gist")

    monkeypatch.undo()
    assert records.load("json", KEY) == b"the first gist"
    record = thread_file(tmp_path, THE_PR, KEY)
    assert list(record.parent.iterdir()) == [record]


def test_a_reader_in_the_middle_of_a_rewrite_still_sees_the_document_that_stands(
    tmp_path, monkeypatch,
):
    records = _records(tmp_path)
    records.save("intent", KEY, b"approve")
    midway = []
    real_replace = Path.replace

    def replacing(self, target):
        midway.append(records.load("intent", KEY))
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", replacing)
    records.save("intent", KEY, b"session")

    assert midway == [b"approve"]
    assert records.load("intent", KEY) == b"session"


@pytest.mark.parametrize("name,lock_file", [
    (KEY, lambda tmp_path: thread_lock_file(tmp_path, THE_PR, KEY)),
    ("reviews", lambda tmp_path: review_lock_file(tmp_path, THE_PR)),
])
def test_a_lock_is_held_across_processes_for_as_long_as_the_block_runs(
    tmp_path, name, lock_file,
):
    records = _records(tmp_path)

    with records.lock(name):
        contender = os.open(lock_file(tmp_path), os.O_RDWR | os.O_CREAT)
        try:
            with pytest.raises(OSError) as refused:
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(contender)

    assert refused.value.errno in (errno.EWOULDBLOCK, errno.EAGAIN)


def test_the_lock_is_let_go_when_the_block_raises(tmp_path):
    records = _records(tmp_path)

    with pytest.raises(ZeroDivisionError), records.lock(KEY):
        1 / 0

    contender = os.open(thread_lock_file(tmp_path, THE_PR, KEY), os.O_RDWR)
    try:
        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(contender)


def test_the_lock_files_and_other_kinds_are_never_documents_of_a_kind(tmp_path):
    records = _records(tmp_path)
    records.save("json", KEY, b"{}")
    for kind in ("intent", "reply", "action", "review"):
        records.save(kind, KEY, b"x")
    records.save("cursor", "poll", b"{}")
    with records.lock(KEY), records.lock("reviews"):
        pass

    assert list(records.list("json")) == [KEY]


def test_a_forgotten_pr_leaves_no_directory_behind(tmp_path):
    store = disk_thread_records(tmp_path)
    store.of(THE_PR).save("json", KEY, b"{}")

    assert store.forget(THE_PR) is True
    assert not thread_dir(tmp_path, THE_PR).exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root removes anything")
def test_a_pr_whose_records_will_not_go_says_so(tmp_path):
    store = disk_thread_records(tmp_path)
    store.of(THE_PR).save("json", KEY, b"{}")
    records = thread_dir(tmp_path, THE_PR)
    records.chmod(0o500)
    try:
        assert store.forget(THE_PR) is False
    finally:
        records.chmod(0o700)
