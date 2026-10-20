import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest
import summarise
from pr_summary.github import Gh, GhFailed
from pr_summary.inputs import Contents

from tests.pr_summary_plugin.test_inputs import PR


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


def nothing_at(sha: str, path: str) -> bytes | None:
    return None


def contents_of(gh: Gh, owner: str, repo: str) -> Contents:
    return nothing_at


def summarising_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(summarise, "target", lambda gh, given: ("acme", "shop", 7))
    monkeypatch.setattr(summarise, "pull_request", lambda gh, owner, repo, number: PR)
    monkeypatch.setattr(summarise.Clone, "find", lambda cwd, owner, repo: None)
    monkeypatch.setattr(summarise, "merge_base", lambda gh, owner, repo, base, head: PR.base_sha)
    monkeypatch.setattr(summarise, "changed_files", lambda gh, owner, repo, number: [])
    monkeypatch.setattr(summarise, "contents", contents_of)
    monkeypatch.setattr(summarise, "history", lambda gh, owner, repo, sha: lambda path: [])
    monkeypatch.setattr(summarise, "earlier_prs", lambda *args: [])
    monkeypatch.setattr(summarise, "report", lambda manifest: "## Requested")


def test_an_mcp_config_reaches_the_witness_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summarising_offline(monkeypatch)
    launched_with: list[Path | None] = []
    monkeypatch.setattr(summarise, "launcher", lambda plugin_root, mcp_config: launched_with.append(mcp_config))
    monkeypatch.setattr(summarise, "run_witnesses", lambda manifest, launch, wait: {})
    monkeypatch.setattr("sys.argv", ["summarise.py", "7", "--use-github-api", "--work-dir", str(tmp_path / "work"), "--mcp-config", str(tmp_path / "mcp.json")])

    summarise.main()

    assert launched_with == [tmp_path / "mcp.json"]


def test_an_earlier_primer_is_handed_to_the_primer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summarising_offline(monkeypatch)
    earlier = tmp_path / "earlier.json"
    earlier.write_text('{"witness": "primer", "concepts": []}')
    monkeypatch.setattr("sys.argv", ["summarise.py", "7", "--use-github-api", "--work-dir", str(tmp_path / "work"), "--earlier-primer", str(earlier), "--prepare-only"])

    summarise.main()

    assert (tmp_path / "work" / "primer" / "earlier_primer.json").read_text() == earlier.read_text()


def test_a_witness_that_failed_prints_the_report_then_exits_naming_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    summarising_offline(monkeypatch)
    monkeypatch.setattr(summarise, "run_witnesses", lambda manifest, launch, wait: {"requested": "its tools stayed unavailable: the Atlassian tools never connected"})
    monkeypatch.setattr("sys.argv", ["summarise.py", "7", "--use-github-api", "--work-dir", str(tmp_path / "work")])

    with pytest.raises(SystemExit) as exited:
        summarise.main()

    assert "## Requested" in capsys.readouterr().out
    assert exited.value.code == "Witnesses failed: requested: its tools stayed unavailable: the Atlassian tools never connected"
