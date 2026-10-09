
import pytest

from github_orchestrator.conversation import OperationKind
from github_orchestrator.domain import Location, Side
from github_orchestrator.settings.fake import fake_settings
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    World,
    at,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    world,
)
from tests.disk_layout import thread_intent_file
from tests.thread_records.support import disk_thread_records

NOW = "2026-09-24T12:00:00Z"
KEY = "PRRT_kwDO"


@pytest.fixture
def here(tmp_path) -> World:
    settings = fake_settings(tmp_path / "data")
    built = world(settings, thread_records=disk_thread_records(settings.threads_dir),
                  clock=at(NOW))
    repo_at(built.working_copies, WORKTREE)
    return built


def _heard(here: World):
    threads = here.threads()
    on_github(here.github, KEY, said(101, "rename it"))
    hear(threads)
    return threads, KEY


def _proposed(here: World):
    threads, key = _heard(here)
    propose(here, threads, key)
    return threads, key


def _left(here: World, key: str, text: str) -> None:
    path = thread_intent_file(here.settings.threads_dir, THE_PR, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _drawn(here: World, text: str):
    threads, key = _proposed(here)
    known = threads.get(key).operations
    _left(here, key, text)
    operations = threads.get(key).operations
    return known, operations


READ_FROM_THE_OLD_BOARD = {
    "approve-said-and-resolved": (
        'approve\n{"reply": "renamed it", "resolve": true, "message": "Rename the flag"}',
        dict(kind=OperationKind.APPROVE, text="renamed it")),
    "approve": ('approve\n{"reply": null, "resolve": false, "message": ""}',
                dict(kind=OperationKind.APPROVE)),
    "approve-delete": ('approve delete\n{"reply": null, "resolve": false, "message": ""}',
                       dict(kind=OperationKind.APPROVE, delete_comment=True)),
    "defer-ci": ("defer ci\nafter ci", dict(kind=OperationKind.DEFER, text="after ci",
                                            until="ci")),
    "unpark": ("unpark", dict(kind=OperationKind.UNPARK)),
    "enrol": ("enrol", dict(kind=OperationKind.ENROL)),
    "withdraw": ("withdraw-from-review", dict(kind=OperationKind.WITHDRAW_FROM_REVIEW)),
    "discard": ("discard", dict(kind=OperationKind.DISCARD)),
    "post-now": ("post-now", dict(kind=OperationKind.POST_NOW)),
    "approve-asked": ('@operation op_0123456789ab 2026-09-24T11:59:00Z\napprove\n'
                      '{"reply": "ok", "resolve": false, "message": ""}',
                      dict(kind=OperationKind.APPROVE, text="ok", id="op_0123456789ab",
                           requested_at="2026-09-24T11:59:00Z")),
}


@pytest.mark.parametrize("case", sorted(READ_FROM_THE_OLD_BOARD))
def test_every_decision_the_old_board_wrote_is_drawn_as_it_was_asked(here, case):
    text, expected = READ_FROM_THE_OLD_BOARD[case]

    known, operations = _drawn(here, text)

    drawn = operations[-1]
    assert operations[:-1] == known
    fields = {"text": "", "delete_comment": False, "until": None, **expected}
    assert {field: getattr(drawn, field) for field in fields} == fields


@pytest.mark.parametrize(("word", "side"), [("LEFT", Side.BEFORE), ("RIGHT", Side.AFTER),
                                            ("before", Side.BEFORE), ("after", Side.AFTER)])
def test_a_draft_edit_reads_its_side_in_the_old_words_and_the_new(here, word, side):
    text = ('edit-draft\n{"body": "rename this", "path": "src/x.py", "line": 12, '
            f'"start_line": 10, "side": "{word}"}}')

    _, operations = _drawn(here, text)

    drawn = operations[-1]
    assert (drawn.kind, drawn.text, drawn.anchor) == (
        OperationKind.EDIT_DRAFT, "rename this",
        Location(path="src/x.py", line=12, start_line=10, start_side=side, side=side))


def test_a_draft_edit_keeps_the_side_its_range_starts_on(here):
    text = ('edit-draft\n{"body": "rename this", "path": "src/x.py", "line": 12, '
            '"start_line": 10, "start_side": "before", "side": "after"}')

    _, operations = _drawn(here, text)

    assert operations[-1].anchor == Location(path="src/x.py", line=12, start_line=10,
                                             start_side=Side.BEFORE, side=Side.AFTER)


GARBAGE = {
    "edit-whose-anchor-will-not-parse": 'edit-draft\n{"body": "x", "path": "f"}',
    "edit-whose-range-starts-on-no-side": ('edit-draft\n{"body": "x", "path": "f", "line": 4, '
                                           '"start_line": 2, "start_side": "up"}'),
    "approve-not-json": "approve\n{not json",
    "approve-a-list": 'approve\n["a list"]',
    "approve-reply-a-number": 'approve\n{"reply": 4}',
    "reply-with-a-modifier": "reply delete\nhave another look",
    "defer-pr-with-no-number": "defer pr:",
    "rework-not-json": "rework\n{not json",
    "rework-a-list": 'rework\n["a list"]',
    "rework-pointed-a-word": 'rework\n{"pointed": "line 4"}',
    "rework-pointed-line-names-no-file": 'rework\n{"pointed": [{"line": 4}]}',
    "resolve-with-a-wake-condition": "resolve pr:87",
    "no-verb-of-ours": "obliterate",
}


@pytest.mark.parametrize("case", sorted(GARBAGE))
def test_a_decision_that_does_not_parse_asks_nothing(here, case):
    known, operations = _drawn(here, GARBAGE[case])

    assert operations == known
