
import pytest

from github_orchestrator.conversation import (
    ConversationState,
    OperationKind,
    Verdict,
)
from github_orchestrator.domain import Location, Side
from tests.builders import a_pr
from tests.conversation.support import (
    PR,
    REPO,
    WORKTREE,
    World,
    at,
    drain,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    world,
)
from tests.disk_layout import (
    thread_action_file,
    thread_dir,
    thread_intent_file,
    thread_reply_file,
)
from tests.thread_records.support import disk_thread_records

THE_PR = a_pr(PR, REPO)

NOW = "2026-09-24T12:00:00Z"

KEY = "PRRT_old"

OLD_INTENTS = {
    "rework": (
        "rework\n"
        '{"note": "use the enum", "pointed": [{"file": "a.py", "line": 3, "text": "x = 1"},'
        ' {"file": "b.py", "line": null, "text": ""}], "include": ["PRRT_other"]}'
    ),
    "session": "session\nlook at the tests first",
    "resolve": "resolve delete\ndone elsewhere",
    "retry": "retry",
    "stop": "stop",
    "reject": "reject\nNot taking this.",
    "not_fixed": "not_fixed\nstill broken",
    "reply": "reply\nthanks, will do\nsecond line",
    "defer_pr": "defer pr:87\nblocked on that",
    "defer_push": "defer push",
    "edit": (
        "edit-draft\n"
        '{"body": "rename this", "path": "src/x.py", "line": 12, "start_line": 10, "side": "LEFT"}'
    ),
    "asked": (
        "@operation op_ba9876543210 2026-09-24T11:58:00Z\n"
        "rework\n"
        '{"note": "again", "pointed": [], "include": []}'
    ),
    "asked_no_time": "@operation op_000000000000\nstop",
}

DRAWN = {
    "rework": dict(kind=OperationKind.REWORK, text="use the enum",
                   note="use the enum",
                   pointed=(("a.py", 3, "x = 1"), ("b.py", None, "")),
                   include=("PRRT_other",)),
    "session": dict(kind=OperationKind.START_SESSION, text="look at the tests first"),
    "resolve": dict(kind=OperationKind.RESOLVE, text="done elsewhere", delete_comment=True),
    "retry": dict(kind=OperationKind.RETRY),
    "stop": dict(kind=OperationKind.STOP),
    "reject": dict(kind=OperationKind.REJECT, text="Not taking this."),
    "not_fixed": dict(kind=OperationKind.REPLY, text="still broken"),
    "reply": dict(kind=OperationKind.REPLY, text="thanks, will do\nsecond line"),
    "defer_pr": dict(kind=OperationKind.DEFER, text="blocked on that", until="pr:87"),
    "defer_push": dict(kind=OperationKind.DEFER, until="push"),
    "edit": dict(kind=OperationKind.EDIT_DRAFT, text="rename this",
                 anchor=Location(path="src/x.py", line=12, start_line=10,
                                 start_side=Side.BEFORE, side=Side.BEFORE)),
    "asked": dict(kind=OperationKind.REWORK, text="again", note="again",
                  id="op_ba9876543210", requested_at="2026-09-24T11:58:00Z"),
    "asked_no_time": dict(kind=OperationKind.STOP, id="op_000000000000"),
}

OLD_REVIEW = (
    '{"id": "op_review1", "verdict": "APPROVE", "body": "ship it", "state": "pending", '
    '"requested_at": "2026-09-24T11:00:00Z", "settled_at": null, "reason": null, '
    '"reason_code": null, "drafts": ["PRRT_edit"], "posted_review": null}'
)


def _on_disk(settings) -> World:
    here = world(settings, clock=at(NOW),
                 thread_records=disk_thread_records(settings.threads_dir))
    repo_at(here.working_copies, WORKTREE)
    on_github(here.github, KEY, said(101, "rename it"))
    return here


def _left(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def here(settings):
    return _on_disk(settings)


@pytest.fixture
def threads(here):
    proposed = here.threads()
    hear(proposed)
    propose(here, proposed, KEY)
    return proposed


def _intent_path(here: World, key: str = KEY):
    return thread_intent_file(here.settings.threads_dir, THE_PR, key)


def _drawn_fields(drawn) -> dict:
    brief = drawn.brief
    return {"id": drawn.id, "requested_at": drawn.requested_at, "kind": drawn.kind,
            "text": drawn.text, "delete_comment": drawn.delete_comment,
            "until": drawn.until, "anchor": drawn.anchor,
            "note": None if brief is None else brief.note,
            "pointed": None if brief is None else tuple(
                (line.file, line.line, line.text) for line in brief.pointed),
            "include": None if brief is None else brief.include}


@pytest.mark.parametrize("case", sorted(OLD_INTENTS))
def test_an_intent_the_old_board_wrote_is_drawn_as_the_work_it_asked_for(here, threads, case):
    known = len(threads.get(KEY).operations)
    _left(_intent_path(here), OLD_INTENTS[case])

    drawn = threads.get(KEY).operations[-1]

    expected = {"id": f"{KEY}.{known + 1}", "requested_at": None, "text": "",
                "delete_comment": False, "until": None, "anchor": None}
    expected.update(DRAWN[case])
    if "note" in expected:
        expected.setdefault("pointed", ())
        expected.setdefault("include", ())
    else:
        expected.update(note=None, pointed=None, include=None)
    assert _drawn_fields(drawn) == expected


def test_a_reply_the_old_board_wrote_is_drawn_and_then_posted(here, threads):
    reply = thread_reply_file(here.settings.threads_dir, THE_PR, KEY)
    _left(reply, "a reply the old board wrote\n")

    drawn = threads.get(KEY).operations[-1]
    drain(threads)

    assert (drawn.kind, drawn.text) == (OperationKind.REPLY, "a reply the old board wrote\n")
    assert [c.body for c in here.github.thread(KEY).comments[1:]] == [
        "a reply the old board wrote\n"]
    assert not reply.exists()


def test_an_intent_the_old_board_wrote_is_taken_by_the_drain(here, threads):
    _left(_intent_path(here), "resolve\ndone elsewhere")

    drain(threads)

    assert threads.get(KEY).standing is ConversationState.DONE
    assert [c.body for c in here.github.thread(KEY).comments[1:]] == ["done elsewhere"]
    assert not _intent_path(here).exists()


def test_an_action_the_old_manager_wrote_is_the_cards_last_action(here, threads):
    _left(thread_action_file(here.settings.threads_dir, THE_PR, KEY), "Read tests/test_x.py")

    activity = threads.activity(threads.get(KEY))

    assert activity.last_action == "Read tests/test_x.py"


def test_a_review_the_old_board_wrote_reads_back(here):
    _left(thread_dir(here.settings.threads_dir, THE_PR) / "op_review1.review", OLD_REVIEW)

    [review] = here.threads().reviews()

    assert (review.id, review.verdict, review.body, review.state, review.requested_at,
            review.drafts) == ("op_review1", Verdict.APPROVE, "ship it", "pending",
                               "2026-09-24T11:00:00Z", ("PRRT_edit",))


