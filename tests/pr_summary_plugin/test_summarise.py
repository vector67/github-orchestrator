import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest
import summarise
from pr_summary.github import Gh, GhFailed


def failing_target(gh: Gh, given: str) -> tuple[str, str, int]:
    raise GhFailed("no such pull request")


def test_without_a_work_dir_a_failed_lookup_leaves_no_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(summarise, "target", failing_target)
    monkeypatch.setattr("sys.argv", ["summarise.py", "7"])

    with pytest.raises(GhFailed):
        summarise.main()

    assert list(tmp_path.iterdir()) == []


def test_a_work_dir_that_holds_anything_is_refused_before_the_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "leftover").write_text("")
    monkeypatch.setattr(summarise, "target", failing_target)
    monkeypatch.setattr("sys.argv", ["summarise.py", "7", "--work-dir", str(tmp_path)])

    with pytest.raises(summarise.WorkDirNotEmpty):
        summarise.main()


class FakeGh:
    def __init__(self, tokens: dict[str, str]) -> None:
        self.tokens = tokens
        self.calls: list[tuple[list[str], dict[str, str] | None]] = []

    def run(self, command: list[str], **options: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((command, options.get("env")))
        if command[1:4] == ["auth", "token", "--user"]:
            account = command[4]
            if account not in self.tokens:
                return subprocess.CompletedProcess(command, 1, b"", f"no oauth token found for {account}".encode())
            return subprocess.CompletedProcess(command, 0, f"{self.tokens[account]}\n".encode(), b"")
        return subprocess.CompletedProcess(command, 0, b"{}", b"")

    def tokens_of(self, args: list[str]) -> list[str | None]:
        return [None if env is None else env.get("GH_TOKEN") for command, env in self.calls if command[1:] == args]


def looking_up_the_user_then_failing(gh: Gh, given: str) -> tuple[str, str, int]:
    gh(["api", "user"])
    raise GhFailed("no such pull request")


def run_with(gh: FakeGh, argv: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(subprocess, "run", gh.run)
    monkeypatch.setattr(summarise, "target", looking_up_the_user_then_failing)
    monkeypatch.setattr("sys.argv", ["summarise.py", "7", *argv])
    summarise.main()


def test_with_a_gh_account_every_gh_call_carries_that_accounts_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gh = FakeGh({"octocat": "fake-token-of-octocat"})

    with pytest.raises(GhFailed):
        run_with(gh, ["--gh-account", "octocat"], monkeypatch, tmp_path)

    assert gh.tokens_of(["api", "user"]) == ["fake-token-of-octocat"]


def test_without_a_gh_account_gh_runs_as_the_shell_has_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gh = FakeGh({"octocat": "fake-token-of-octocat"})

    with pytest.raises(GhFailed):
        run_with(gh, [], monkeypatch, tmp_path)

    assert [command for command, _ in gh.calls] == [["gh", "api", "user"]]
    assert gh.tokens_of(["api", "user"]) == [None]


def test_a_gh_account_without_a_token_fails_naming_the_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gh = FakeGh({})

    with pytest.raises(GhFailed, match="gh auth token --user octocat failed: no oauth token found for octocat"):
        run_with(gh, ["--gh-account", "octocat"], monkeypatch, tmp_path)

    assert gh.tokens_of(["api", "user"]) == []
