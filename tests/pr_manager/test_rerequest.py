from dataclasses import dataclass
from typing import Any

import pytest

from github_orchestrator.board_api.interface import NoticeCode
from github_orchestrator.github import PullRequestState
from github_orchestrator.github.fake import Check, FakeGitHub
from tests.change_detection.support import failing, passing
from tests.change_detection.support import seen as seen_by
from tests.pr_manager.support import THE_PR, ServerPanel, polled, run_manager
from tests.settings.support import disk_rerequests
from tests.thread_records.support import disk_thread_records, keep, thread

ASKED_AT = "2026-06-10T09:00:00Z"
POLLED_AT = "2026-06-10T11:00:00Z"
BEFORE_THE_POLL = "2026-06-10T10:59:59.500000Z"
AFTER_THE_POLL = "2026-06-10T11:00:00.250000Z"
RUNNING = Check("tests", "in_progress", None, "https://ci/tests", "tests running")


@dataclass(frozen=True)
class Poll:
    checks: tuple[Check, ...] = (passing(),)
    pending: tuple[str, ...] = ()
    at: str = POLLED_AT
    head: str = "sha1"


@dataclass(frozen=True)
class Case:
    polls: tuple[Poll, ...] = (Poll(),)
    threads: tuple[dict[str, Any], ...] = ()
    queued: tuple[str, ...] = ("carol",)


def _thread(key, *, by="carol", state="resolved", opened_at="2026-06-10T10:00:00Z",
            accept=None, settled_at=None):
    operations = [] if accept is None else [
        {"id": f"{key}.1", "kind": "approve", "state": accept,
         "requested_at": "2026-06-10T10:30:00Z", "settled_at": settled_at}]
    return thread(key, kind="review", conversation_state=state, author=by,
                  comment_created_at=opened_at,
                  operations=operations)


SETTLED = _thread("t1", accept="applied", settled_at=BEFORE_THE_POLL)
CHECKS_THEN_NONE = (Poll(head="sha0"), Poll(checks=()))


def _seeded(settings, case):
    polled(settings, *(seen_by(settings.config.gh_account, polled_at=each.at,
                               head_sha=each.head, checks=each.checks,
                               pending_reviewers=each.pending)
                       for each in case.polls))
    records = disk_thread_records(settings.threads_dir).of(THE_PR)
    for each in case.threads:
        keep(records, each)
    rerequests = disk_rerequests(settings.data_dir)
    for login in case.queued:
        rerequests.queue(THE_PR, login)
    return rerequests


def _after_a_tick(settings, tmp_path, case):
    rerequests = _seeded(settings, case)
    github = FakeGitHub()
    github.add_pr(THE_PR, PullRequestState())
    run_manager(settings, worktree=tmp_path, is_author=True, github=github)
    return github.pr_state(THE_PR).pending_reviewers, rerequests.queued(THE_PR)


ASKED = (("carol",), ())
WAITING = ((), ("carol",))


@pytest.mark.parametrize(("case", "answer"), [
    pytest.param(Case(threads=(SETTLED,)), ASKED, id="ci passing and nothing in flight asks"),
    pytest.param(Case(polls=(Poll(checks=(RUNNING,)),), threads=(SETTLED,)), WAITING,
                 id="ci pending waits"),
    pytest.param(Case(polls=(Poll(checks=(failing(),)),), threads=(SETTLED,)), WAITING,
                 id="ci failing waits"),
    pytest.param(Case(threads=(_thread("t1", accept="pending"),)), WAITING,
                 id="an accept pending waits"),
    pytest.param(Case(threads=(_thread("t1", accept="running"),)), WAITING,
                 id="an accept running waits"),
    pytest.param(Case(threads=(_thread("t1", accept="requeued"),)), WAITING,
                 id="an accept requeued waits"),
    pytest.param(Case(threads=(SETTLED, _thread("t2", by="dave", accept="running"))), WAITING,
                 id="an accept landing on someone else's thread waits"),
    pytest.param(Case(threads=(_thread("t1", accept="applied", settled_at=AFTER_THE_POLL),)),
                 WAITING, id="facts polled before the last accept settled wait"),
    pytest.param(Case(threads=(SETTLED, _thread("t2", state="open"))), WAITING,
                 id="an open thread from the reviewer waits"),
    pytest.param(Case(threads=(SETTLED, _thread("t2", by="dave", state="open"))), ASKED,
                 id="an open thread from someone else does not hold the reviewer"),
    pytest.param(Case(polls=(Poll(pending=("carol",), at=ASKED_AT), Poll()),
                      threads=(SETTLED, _thread("t2", state="open",
                                                opened_at="2026-06-10T08:00:00Z"))),
                 ASKED, id="an open thread from before they were last asked is not in the round"),
    pytest.param(Case(threads=(SETTLED, _thread("t2", state="removed"))), ASKED,
                 id="a removed thread is not in the round"),
    pytest.param(Case(threads=(SETTLED, thread("t2", author="carol", operations="first"))),
                 ASKED, id="an unreadable record holds nothing"),
    pytest.param(Case(polls=CHECKS_THEN_NONE, threads=(SETTLED,)), WAITING,
                 id="with checks before, none waits however long"),
    pytest.param(Case(polls=(Poll(checks=()),), threads=(SETTLED,)), ASKED,
                 id="never had checks, none asks once the accepts settled and were polled"),
    pytest.param(Case(polls=(Poll(checks=()),),
                      threads=(_thread("t1", accept="applied", settled_at=AFTER_THE_POLL),)),
                 WAITING, id="never had checks, an accept not yet polled waits"),
    pytest.param(Case(polls=(Poll(checks=()),)), ASKED,
                 id="never had checks and no accept at all asks"),
    pytest.param(Case(polls=(Poll(pending=("carol",)),), threads=(SETTLED,)), ((), ()),
                 id="a pending login is dropped, not asked"),
    pytest.param(Case(polls=(Poll(pending=("@acme/reviewers",)),), threads=(SETTLED,)), ASKED,
                 id="a pending team does not hold the person"),
    pytest.param(Case(threads=(SETTLED, _thread("t2", by="dave", state="open")),
                      queued=("carol", "dave")), (("carol",), ("dave",)),
                 id="each queued login is judged on its own threads"),
])
def test_a_queued_reviewer_is_asked_once_the_fixes_are_pushed_and_ci_is_green(
        settings, tmp_path, case, answer):
    assert _after_a_tick(settings, tmp_path, case) == answer


def test_a_re_request_github_refuses_says_why_in_the_notice_and_leaves_the_queue(settings,
                                                                                 tmp_path):
    rerequests = _seeded(settings, Case(threads=(SETTLED,)))
    board = ServerPanel()
    seen = []
    run_manager(settings, lambda: seen.append(board.panel.dashboard().notice),
                worktree=tmp_path, is_author=True, board=board)
    [notice] = seen
    assert notice is not None and notice.code is NoticeCode.ASSIGN_REVIEWERS_REFUSED
    assert "Not Found" in (notice.detail or "")
    assert rerequests.queued(THE_PR) == ()
