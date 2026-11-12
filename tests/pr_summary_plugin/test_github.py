import subprocess
from collections.abc import Callable
from typing import Any

import pytest
from pr_summary.github import (
    Gh,
    GhFailed,
    changed_files,
    contents,
    gh_cli,
    pull_request,
    target,
)

CUT_OFF = subprocess.CompletedProcess(["gh"], 1, b"", b"unexpected end of JSON input\n")
NOT_FOUND = subprocess.CompletedProcess(["gh"], 1, b"", b"gh: Not Found (HTTP 404)\n")
ANSWERED = subprocess.CompletedProcess(["gh"], 0, b'{"login": "octocat"}', b"")


def replying(monkeypatch: pytest.MonkeyPatch, *replies: subprocess.CompletedProcess[bytes]) -> list[list[str]]:
    calls: list[list[str]] = []
    queued = list(replies)

    def run(command: list[str], **options: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        return queued.pop(0)

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_a_cut_off_response_is_asked_for_again(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = replying(monkeypatch, CUT_OFF, ANSWERED)

    assert gh_cli(["api", "user"]) == b'{"login": "octocat"}'
    assert calls == [["gh", "api", "user"], ["gh", "api", "user"]]


def test_a_response_cut_off_twice_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    replying(monkeypatch, CUT_OFF, CUT_OFF)

    with pytest.raises(GhFailed, match="unexpected end of JSON input"):
        gh_cli(["api", "user"])


def test_any_other_failure_is_not_asked_for_again(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = replying(monkeypatch, NOT_FOUND, ANSWERED)

    with pytest.raises(GhFailed, match="HTTP 404"):
        gh_cli(["api", "user"])
    assert len(calls) == 1


@pytest.mark.parametrize("body", [b"", b'{"data": {"repos'])
def test_a_cut_off_body_from_a_gh_that_exited_cleanly_fails(body: bytes) -> None:
    with pytest.raises(GhFailed, match="not JSON"):
        pull_request(lambda args: body, "acme", "widgets", 1)


CUT_OFF_BODY = b'{"data": {"repos'


def answering_first(first: bytes) -> Gh:
    calls: list[list[str]] = []

    def gh(args: list[str]) -> bytes:
        calls.append(args)
        return first if len(calls) == 1 else CUT_OFF_BODY

    return gh


@pytest.mark.parametrize(
    "read",
    [
        pytest.param(lambda: target(lambda args: CUT_OFF_BODY, "7"), id="repository"),
        pytest.param(lambda: pull_request(answering_first(b'{"data": {"repository": {"pullRequest": {}}}}'), "acme", "widgets", 1), id="paged"),
        pytest.param(lambda: changed_files(lambda args: CUT_OFF_BODY, "acme", "widgets", 1), id="changed files"),
        pytest.param(lambda: contents(lambda args: CUT_OFF_BODY, "acme", "widgets")("abc", "a.py"), id="contents"),
        pytest.param(lambda: contents(answering_first(b'{"type": "file", "sha": "def"}'), "acme", "widgets")("abc", "a.py"), id="blob"),
    ],
)
def test_every_read_of_a_cut_off_body_fails_cleanly(read: Callable[[], object]) -> None:
    with pytest.raises(GhFailed, match="not JSON"):
        read()
