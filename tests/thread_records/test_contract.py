import threading
import time

import pytest

from github_orchestrator.thread_records.fake import FakeThreadRecords
from tests.builders import a_pr
from tests.thread_records.support import (
    KEY,
    PR,
    REPO,
    disk_thread_records,
)

THE_PR = a_pr(PR, REPO)


@pytest.fixture(params=["fake", "disk"])
def store(request, tmp_path):
    if request.param == "fake":
        return FakeThreadRecords()
    return disk_thread_records(tmp_path / "threads")


@pytest.fixture
def records(store):
    return store.of(THE_PR)


def test_a_document_saved_again_is_replaced_whole(records):
    records.save("json", KEY, b"first")
    records.save("json", KEY, b"second")

    assert records.load("json", KEY) == b"second"


def test_a_document_nothing_saved_loads_as_nothing(records):
    assert records.load("json", KEY) is None


def test_each_kind_keeps_its_own_documents_under_the_same_key(records):
    records.save("json", KEY, b"a thread")
    records.save("action", KEY, b"Edit a.py")

    assert (records.load("json", KEY), records.load("action", KEY),
            records.load("intent", KEY)) == (b"a thread", b"Edit a.py", None)
    assert records.list("action") == {KEY: b"Edit a.py"}


def test_every_document_of_a_kind_is_listed_under_its_key(records):
    records.save("review", "op_b", b"b")
    records.save("review", "op_a", b"a")

    assert records.list("review") == {"op_b": b"b", "op_a": b"a"}


def test_a_listing_comes_in_the_order_the_documents_were_last_written(records):
    records.save("intent", "PRRT_zzz", b"first")
    time.sleep(0.01)
    records.save("intent", "PRRT_aaa", b"second")
    time.sleep(0.01)
    records.save("intent", "PRRT_zzz", b"third")

    assert list(records.list("intent")) == ["PRRT_aaa", "PRRT_zzz"]


def test_a_deleted_document_is_gone_and_its_neighbours_stay(records):
    records.save("intent", KEY, b"approve")
    records.save("reply", KEY, b"thanks")

    records.delete("intent", KEY)

    assert records.load("intent", KEY) is None
    assert records.list("reply") == {KEY: b"thanks"}


def test_deleting_what_is_not_there_is_fine(records):
    records.delete("intent", KEY)

    assert records.list("intent") == {}


def test_a_second_holder_of_a_lock_waits_for_the_first(records):
    records.save("json", KEY, b"0")
    inside = threading.Event()
    order = []

    def spend_an_attempt(name):
        with records.lock(KEY):
            inside.set()
            attempts = int(records.load("json", KEY))
            time.sleep(0.05 if name == "first" else 0)
            records.save("json", KEY, str(attempts + 1).encode())
            order.append(name)

    worker = threading.Thread(target=spend_an_attempt, args=("first",))
    worker.start()
    inside.wait()
    spend_an_attempt("second")
    worker.join()

    assert order == ["first", "second"]
    assert records.load("json", KEY) == b"2"


def test_locks_of_different_names_do_not_wait_for_each_other(records):
    with records.lock(KEY), records.lock("reviews"):
        pass


def test_each_pr_keeps_its_own_documents(store):
    store.of(THE_PR).save("json", KEY, b"{}")

    assert store.of(a_pr(PR + 1, REPO)).load("json", KEY) is None
    assert store.of(a_pr(PR, "other/repo")).list("json") == {}


def test_a_forgotten_pr_has_no_documents_left(store):
    records = store.of(THE_PR)
    for kind in ("json", "intent", "reply", "cursor"):
        records.save(kind, KEY, b"x")

    assert store.forget(THE_PR) is True

    again = store.of(THE_PR)
    assert [again.list(kind) for kind in ("json", "intent", "reply", "cursor")] == [
        {}, {}, {}, {}]


def test_forgetting_a_pr_that_had_no_documents_is_fine(store):
    assert store.forget(THE_PR) is True
