import json

import pytest

from github_orchestrator.conversation import (
    Denied,
    ErrorCode,
)
from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.thread_records.fake import FakeThreadRecords
from tests.builders import a_pr
from tests.conversation.support import (
    WORKTREE,
    hear,
    on_github,
    repo_at,
    said,
    world,
)


def test_a_handle_reads_this_prs_records_and_no_other(tmp_path):
    here = world(fake_settings(tmp_path))
    repo_at(here.working_copies, WORKTREE, pr=a_pr(1, "o/n"))
    on_github(here.github, "PRRT_1", said(1, "fix this"), pr=a_pr(1, "o/n"))
    hear(here.threads(repo="o/n", pr=1))

    assert [c.key for c in here.conversation_managers.of(a_pr(1, "o/n")).all()] == ["PRRT_1"]
    assert here.conversation_managers.of(a_pr(2, "o/n")).all() == []


def test_a_handle_answers_for_the_configured_account_in_the_role_change_detection_saved(
        tmp_path):
    here = world(fake_settings(tmp_path, gh_account="vector67"))
    here.polled(repo="o/n", pr=1, is_author=False)

    facts = here.conversation_managers.of(a_pr(1, "o/n")).facts()

    assert (facts.account, facts.is_author) == ("vector67", False)


CORRUPT = {
    "will not parse": b"{not json",
    "a fix in no state": json.dumps({"version": 1, "thread_key": "PRRT_1",
                                     "fix_state": "pondering"}).encode(),
}


@pytest.mark.parametrize("written", CORRUPT.values(), ids=CORRUPT.keys())
def test_a_record_that_will_not_read_reads_as_an_unreadable_conversation(tmp_path, written):
    thread_records = FakeThreadRecords()
    here = world(fake_settings(tmp_path), thread_records=thread_records)
    thread_records.pr(a_pr(1, "o/n")).save("json", "PRRT_1", written)
    threads = here.conversation_managers.of(a_pr(1, "o/n"))

    assert threads.get("PRRT_1").is_unreadable
    assert [c.is_unreadable for c in threads.all()] == [True]


def test_a_verb_on_a_record_that_will_not_read_is_refused(tmp_path):
    thread_records = FakeThreadRecords()
    here = world(fake_settings(tmp_path), thread_records=thread_records)
    thread_records.pr(a_pr(1, "o/n")).save("json", "PRRT_1", b"{not json")

    with here.conversation_managers.of(a_pr(1, "o/n")).editing("PRRT_1") as editable:
        refused = editable.retry()

    assert isinstance(refused, Denied)
    assert refused.code is ErrorCode.INTERNAL_REFUSAL
