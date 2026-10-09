from github_orchestrator.conversation import ConversationState
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    Moment,
    World,
    drain,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    world,
)

KEY = "PRRT_1"
BEFORE = "2026-09-24T15:40:00Z"
READY_AT = "2026-09-24T15:46:32Z"
AFTER = "2026-09-24T15:47:00Z"


def _commented(settings, clock: Moment) -> tuple[World, object]:
    here = world(settings, clock=clock)
    repo_at(here.working_copies, WORKTREE, {"f": "old\n"})
    threads = here.threads()
    on_github(here.github, KEY, said(101, "bind as one array"))
    hear(threads)
    return here, threads


def _ready(settings) -> tuple[World, object, Moment]:
    clock = Moment(READY_AT)
    here, threads = _commented(settings, clock)
    propose(here, threads, KEY)
    return here, threads, clock


def _still_news(here: World) -> bool:
    return here.standing.fix_still_news(THE_PR, KEY)


def test_marking_a_conversation_seen_stamps_it(settings):
    here, threads = _commented(settings, Moment(AFTER))

    with threads.editing(KEY) as editable:
        editable.mark_seen()

    assert threads.get(KEY).seen_at is not None


def test_marking_a_conversation_nobody_has_leaves_no_record(settings):
    here = world(settings)
    threads = here.threads()

    with threads.editing("PRRT_gone") as editable:
        editable.mark_seen()

    assert threads.get("PRRT_gone") is None


def test_a_ready_fix_nobody_has_looked_at_is_not_handled(settings):
    here, _, _ = _ready(settings)

    assert _still_news(here)


def test_a_fix_clicked_after_it_was_ready_is_handled(settings):
    here, threads, clock = _ready(settings)
    clock.iso = AFTER

    with threads.editing(KEY) as editable:
        editable.mark_seen()

    assert not _still_news(here)


def test_a_fix_clicked_only_before_it_was_ready_is_not_handled(settings):
    clock = Moment(BEFORE)
    here, threads = _commented(settings, clock)
    with threads.editing(KEY) as editable:
        editable.mark_seen()
    clock.iso = READY_AT

    propose(here, threads, KEY)

    assert _still_news(here)


def test_a_board_verb_asked_after_the_fix_was_ready_handles_it(settings):
    here, threads, clock = _ready(settings)
    clock.iso = AFTER

    with threads.editing(KEY) as editable:
        editable.place(ConversationState.DEFERRED)

    assert not _still_news(here)


def test_work_asked_before_the_fix_was_ready_does_not_handle_it(settings):
    clock = Moment(BEFORE)
    here, threads = _commented(settings, clock)
    with threads.editing(KEY) as editable:
        editable.reply("looking at it")
    drain(threads)
    clock.iso = READY_AT

    propose(here, threads, KEY)

    assert _still_news(here)


def test_a_fix_no_longer_proposed_is_handled(settings):
    here, threads, _ = _ready(settings)
    with threads.editing(KEY) as editable:
        editable.approve()
    drain(threads)

    assert not _still_news(here)


def test_a_conversation_that_is_gone_is_handled(settings):
    assert not _still_news(world(settings))
