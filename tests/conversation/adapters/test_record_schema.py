import json
from dataclasses import replace

import pytest

from github_orchestrator.agent_runs.fake import Outcome
from github_orchestrator.conversation import Denied, ErrorCode, OperationKind
from github_orchestrator.domain import Side
from github_orchestrator.settings.fake import fake_settings
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    World,
    drain,
    hear,
    on_github,
    repo_at,
    said,
    start_run,
    without_runs,
    world,
)
from tests.disk_layout import thread_dir, thread_file
from tests.thread_records.support import disk_thread_records, ticking_clock

KEY = "PRRT_kwDO"
BEFORE_THE_CLOCK = "2026-02-01T00:00:00Z"


def _here(tmp_path, *, runs: bool = True) -> World:
    settings = fake_settings(tmp_path / "data")
    built = world(settings if runs else without_runs(settings),
                  thread_records=disk_thread_records(tmp_path), clock=ticking_clock())
    repo_at(built.working_copies, WORKTREE)
    return built


@pytest.fixture
def here(tmp_path) -> World:
    return _here(tmp_path)


def _heard(here: World, *keys: str):
    threads = here.threads()
    for number, key in enumerate(keys or (KEY,), start=101):
        on_github(here.github, key, said(number, "rename it", created_at=BEFORE_THE_CLOCK))
        hear(threads)
    return threads


def _on_disk(tmp_path, key=KEY):
    return json.loads(thread_file(tmp_path, THE_PR, key).read_text())


def _write_document(tmp_path, text, key=KEY):
    path = thread_file(tmp_path, THE_PR, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _write_legacy(tmp_path, **fields):
    return _write_document(tmp_path, json.dumps({"thread_key": KEY, **fields}))


WRONG_SHAPES = {
    "top-level-list": "[]",
    "not-json": "{not json",
    "version-is-a-word": '{"version": "two", "thread_key": "PRRT_kwDO"}',
    "attempts-is-a-word": '{"version": 1, "thread_key": "PRRT_kwDO", '
                          '"attempts": "many"}',
    "comments-is-a-mapping": '{"version": 1, "thread_key": "PRRT_kwDO", '
                             '"comments": {"id": 1}}',
    "fix-steps-is-a-number": '{"version": 1, "thread_key": "PRRT_kwDO", '
                             '"fix_steps": 3}',
    "panel-reply-ids-is-a-number": '{"version": 1, "thread_key": "PRRT_kwDO", '
                                   '"panel_reply_ids": 3}',
    "v2-conversation-state-is-a-retired-word":
        '{"version": 2, "thread_key": "PRRT_kwDO", '
        '"conversation_state": "dismissed"}',
    "v2-conversation-state-is-a-display-word":
        '{"version": 2, "thread_key": "PRRT_kwDO", '
        '"conversation_state": "unreadable"}',
    "v2-fix-state-is-a-display-word":
        '{"version": 2, "thread_key": "PRRT_kwDO", "fix_state": "ready"}',
    "v2-fix-steps-is-a-word":
        '{"version": 2, "thread_key": "PRRT_kwDO", "fix_steps": "pick"}',
    "v2-run-kind-is-no-kind-of-ours":
        '{"version": 2, "thread_key": "PRRT_kwDO", "run_kind": "cherry-pick"}',
    "v2-rework-brief-is-a-word":
        '{"version": 2, "thread_key": "PRRT_kwDO", '
        '"rework_brief": "do it again"}',
    "v2-rework-brief-points-at-a-word":
        '{"version": 2, "thread_key": "PRRT_kwDO", '
        '"rework_brief": {"note": "again", "pointed": ["line 4"]}}',
    "v2-a-pointed-line-names-no-file":
        '{"version": 2, "thread_key": "PRRT_kwDO", '
        '"rework_brief": {"pointed": [{"file": 4, "line": 4, "text": "x"}]}}',
    "v2-base-sha-is-no-commit-hash":
        '{"version": 2, "thread_key": "PRRT_kwDO", "base_sha": "base1"}',
    "v2-thread-sha-is-a-branch-name":
        '{"version": 2, "thread_key": "PRRT_kwDO", "thread_sha": "HEAD"}',
    "v2-landed-sha-is-a-number":
        '{"version": 2, "thread_key": "PRRT_kwDO", "landed_sha": 1234567}',
    "v2-an-anchor-over-lines-on-no-side":
        '{"version": 2, "thread_key": "PRRT_kwDO", "operations": [{"id": "a.1", '
        '"kind": "create-draft", "state": "applied", '
        '"anchor": {"path": "f", "line": 4, "start_line": 2}}]}',
    "v2-a-pointed-line-is-on-no-number":
        '{"version": 2, "thread_key": "PRRT_kwDO", '
        '"rework_brief": {"pointed": [{"file": "a.py", "line": "four", '
        '"text": "x"}]}}',
}


@pytest.mark.parametrize("name", sorted(WRONG_SHAPES))
def test_a_record_of_the_wrong_shape_reads_as_unreadable(tmp_path, here, name):
    _write_document(tmp_path, WRONG_SHAPES[name])

    assert here.threads().get(KEY).is_unreadable


def _listed(threads) -> dict[str, bool]:
    return {conversation.key: conversation.is_unreadable
            for conversation in threads.all()}


@pytest.mark.parametrize("name", ["not-json", "v2-run-kind-is-no-kind-of-ours"])
def test_a_record_of_the_wrong_shape_never_hides_the_rest_of_the_board(tmp_path, here, name):
    threads = _heard(here, "PRRT_readable")
    _write_document(tmp_path, WRONG_SHAPES[name], key="broken")

    assert _listed(threads) == {"PRRT_readable": False, "broken": True}


def test_a_record_that_will_not_read_at_all_stands_in_on_the_board(tmp_path, here):
    _write_document(tmp_path, "{not json", key="MDI0OlB1bGx/UmV2aWV3=")

    assert _listed(here.threads()) == {"MDI0OlB1bGx/UmV2aWV3=": True}


def test_a_thread_the_board_has_never_seen_is_stamped_once(tmp_path, here):
    threads = _heard(here)
    created = threads.get(KEY).created_at

    with threads.editing(KEY) as editable:
        editable.mark_seen()

    assert threads.get(KEY).created_at == created


def test_a_verb_on_a_record_that_will_not_read_writes_nothing(tmp_path, here):
    path = _write_document(tmp_path, "[]")

    with here.threads().editing(KEY) as editable:
        denied = editable.retry()

    assert isinstance(denied, Denied)
    assert denied.code is ErrorCode.INTERNAL_REFUSAL
    assert path.read_text() == "[]"


def test_a_record_written_before_the_port_reads_back(tmp_path, here):
    _write_legacy(tmp_path, status="ready")

    assert here.threads().get(KEY).fix.is_proposed


def _unchanged_by_a_save(here):
    threads = here.threads()
    before = threads.get(KEY)

    with threads.editing(KEY) as editable:
        editable.mark_seen()

    after = threads.get(KEY)
    assert (replace(after, seen_at=None, created_at=None)
            == replace(before, seen_at=None, created_at=None))
    return after


def test_a_record_written_before_the_port_reads_back_the_same_once_saved(tmp_path, here):
    _write_legacy(tmp_path, status="ready", summary="rename the thing",
                  created_at="2026-01-01T00:00:00.000000Z")

    saved = _unchanged_by_a_save(here)

    assert saved.fix.is_proposed
    assert saved.gist == "rename the thing"
    assert saved.created_at == "2026-01-01T00:00:00.000000Z"


def test_a_draft_written_before_start_side_starts_its_range_on_its_side(tmp_path, here):
    anchor = {"path": "f", "line": 40, "start_line": 38, "side": "before"}
    _write_document(tmp_path, json.dumps({
        "version": 2, "thread_key": KEY, "conversation_state": "draft", "fix_state": "absent",
        **anchor,
        "operations": [{"id": f"{KEY}.1", "kind": "create-draft", "state": "applied",
                        "anchor": anchor}]}))

    saved = _unchanged_by_a_save(here)

    assert saved.start_side is Side.BEFORE
    assert saved.operations[0].anchor.start_side is Side.BEFORE
    on_disk = _on_disk(tmp_path)
    assert (on_disk["start_side"], on_disk["operations"][0]["anchor"]["start_side"]) == (
        "before", "before")


def test_a_single_line_draft_written_before_start_side_has_none(tmp_path, here):
    _write_document(tmp_path, json.dumps({
        "version": 2, "thread_key": KEY, "conversation_state": "draft", "fix_state": "absent",
        "path": "f", "line": 40, "side": "before"}))

    assert here.threads().get(KEY).start_side is None


def test_a_record_the_port_wrote_reads_back_the_same_once_saved(tmp_path, here):
    _write_document(tmp_path, json.dumps({
        "version": 1, "thread_key": KEY, "status": "ready",
        "conversation_state": "open", "fix_state": "proposed", "fix_steps": [],
        "summary": "rename the thing"}))

    saved = _unchanged_by_a_save(here)

    assert saved.fix.is_proposed
    assert saved.gist == "rename the thing"
    assert saved.created_at is not None


def test_threads_list_in_the_order_they_were_first_seen_and_undated_last(tmp_path, here):
    threads = _heard(here, "PRRT_c", "PRRT_b", "PRRT_a")
    _write_document(tmp_path, json.dumps({"thread_key": "undated", "status": "ready"}),
                    key="undated")
    _write_document(tmp_path, "{", key="PRRT_0")

    assert [conversation.key for conversation in threads.all()] == [
        "PRRT_c", "PRRT_b", "PRRT_a", "undated", "PRRT_0"]


def test_the_agents_last_action_reads_back_clipped_to_a_card(here):
    threads = _heard(here)
    here.agent_runs.script(Outcome(events=({"type": "result", "is_error": True,
                                            "result": "x" * 500},), finishes=False))
    drain(threads)
    drain(threads)

    clipped = threads.activity(threads.get(KEY)).last_action

    assert len(clipped) == 200
    assert clipped.endswith("…")


def _review(review_id, requested_at, state="pending"):
    return {"id": review_id, "verdict": "APPROVE", "state": state,
            "requested_at": requested_at}


def test_reviews_come_back_in_the_order_they_were_asked_for(tmp_path, here):
    thread_dir(tmp_path, THE_PR).mkdir(parents=True)
    for review in (_review("op_b", "2026-01-02T00:00:00Z"),
                   _review("op_a", "2026-01-01T00:00:00Z", "applied")):
        thread_dir(tmp_path, THE_PR).joinpath(f"{review['id']}.review").write_text(
            json.dumps(review))

    reviews = here.threads().reviews()

    assert [review.id for review in reviews] == ["op_a", "op_b"]


def test_a_review_in_no_state_work_can_be_in_is_passed_over(tmp_path, here):
    thread_dir(tmp_path, THE_PR).mkdir(parents=True)
    thread_dir(tmp_path, THE_PR).joinpath("op_good.review").write_text(
        json.dumps(_review("op_good", None)))
    thread_dir(tmp_path, THE_PR).joinpath("op_bad.review").write_text(
        json.dumps(_review("op_bad", None, "lost")))

    assert [review.id for review in here.threads().reviews()] == ["op_good"]


def test_a_retry_reads_back_as_the_work_holding_the_run(here):
    threads = _heard(here)
    for _ in range(threads.get(KEY).run_holder.attempts_allowed):
        start_run(here, threads)
        with threads.editing(KEY) as editable:
            editable.fail("the tests would not run")

    with threads.editing(KEY) as editable:
        editable.retry()
    drain(threads)

    holder = threads.get(KEY).run_holder
    assert holder.kind is OperationKind.RETRY
    assert holder.in_flight
