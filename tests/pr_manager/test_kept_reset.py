import json

import pytest

from github_orchestrator.board_api.interface import (
    RESET_STATE,
    RESET_TO_ORIGIN,
    Dashboards,
    ResetRefusal,
    ResetRefusalCode,
    ResetToOrigin,
    Shelves,
)
from tests.pr_manager.support import THE_PR, ServerPanel, manager_over


def read_back(settings, tmp_path, document):
    manager = manager_over(settings, None, worktree=tmp_path, board=ServerPanel())
    manager.container.get(Shelves).of(THE_PR).save(RESET_TO_ORIGIN, RESET_STATE, document)
    return manager.container.get(Dashboards).dashboard(THE_PR).reset_to_origin


@pytest.mark.parametrize("fields", [
    {"queued_at": 5}, {"queued_at": False}, {"queued_at": 0}, {"queued_at": []},
    {"queued_at": {}}, {"queued_at": None, "ran_at": 1}, {"queued_at": None, "refused": True},
    {"queued_at": ""}, {"ran_at": ""}, {"ran_at": "2026-01-01T00:00:00Z", "refused": ""},
    {"ran_at": "2026-01-01T00:00:00Z", "refused": "a sentence kept before refusals had codes"},
    {"ran_at": "2026-01-01T00:00:00Z", "refused": {"code": "no-such-code", "detail": None}},
    {"ran_at": "2026-01-01T00:00:00Z", "refused": {"code": "reset-refused", "detail": 5}},
    {"ran_at": "2026-01-01T00:00:00Z", "refused": {"code": "reset-refused", "detail": ""}},
])
def test_a_kept_reset_with_a_field_that_is_not_text_or_is_empty_reads_as_none_kept(
        settings, tmp_path, fields):
    assert read_back(settings, tmp_path, json.dumps(fields).encode()) is None


def test_a_kept_refusal_reads_back_as_its_code_and_detail(settings, tmp_path):
    document = {"queued_at": None, "ran_at": "2026-01-01T00:00:00Z",
                "refused": {"code": "fetch-failed",
                            "detail": "fatal: could not read from remote"}}

    kept = read_back(settings, tmp_path, json.dumps(document).encode())

    assert kept == ResetToOrigin(ran_at="2026-01-01T00:00:00Z", refused=ResetRefusal(
        ResetRefusalCode.FETCH_FAILED, "fatal: could not read from remote"))


def test_a_kept_reset_nested_too_deep_to_parse_reads_as_none_kept(settings, tmp_path):
    assert read_back(settings, tmp_path, b"[" * 100_000 + b"]" * 100_000) is None
