import subprocess

import pytest

from github_orchestrator.domain import Sha
from tests.builders import a_pr
from tests.working_copies.support import found_checkout


def _git(repo, *argv):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *argv],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def checkout(settings, tmp_path):
    return found_checkout(settings, a_pr(1, "o/n"), tmp_path / "repo")


def _refusing_git(monkeypatch):
    seen = []

    def capture(argv, *args, **kwargs):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 1, "", "")

    monkeypatch.setattr(subprocess, "run", capture)
    return seen


@pytest.mark.parametrize("base_branch",
                         ["--output=/tmp/pwned", "-x", "a b", "a^b", "..",
                          "feature/x.lock"])
def test_a_base_branch_that_is_no_branch_name_never_reaches_git(checkout, monkeypatch,
                                                                base_branch):
    seen = _refusing_git(monkeypatch)

    assert checkout.pr_diff(base_branch, Sha("a" * 40)) is None

    assert seen, "the fallback refs were never tried"
    assert not [argv for argv in seen if base_branch in " ".join(argv)]


def test_the_base_branch_a_pr_really_has_ends_option_parsing(checkout, monkeypatch):
    seen = _refusing_git(monkeypatch)

    checkout.pr_diff("release/2.0", Sha("a" * 40))

    assert "origin/release/2.0^{commit}" in seen[0]
    assert seen[0].index("--end-of-options") < seen[0].index(
        "origin/release/2.0^{commit}")
