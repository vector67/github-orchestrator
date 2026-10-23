import subprocess
from typing import Any

import pytest
from pr_summary.github import GhFailed, gh_cli

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
