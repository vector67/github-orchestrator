import logging
import subprocess

import pytest

from github_orchestrator.domain import Sha
from tests.builders import a_pr
from tests.working_copies.support import copies_for, found_checkout

SHA = "a" * 40


@pytest.fixture
def copies(settings, tmp_path):
    return copies_for(settings, a_pr(1, "o/n"), tmp_path)


@pytest.fixture
def pr_checkout(settings, tmp_path):
    return found_checkout(settings, a_pr(1, "o/n"), tmp_path)
OTHER = "b" * 40


def _hangs(*args, **kwargs):
    raise subprocess.TimeoutExpired(cmd=args[0], timeout=60)


def _refuses(*args, **kwargs):
    refused = subprocess.CompletedProcess(args[0], 128, "", "fatal: not a git repository")
    if kwargs.get("check"):
        refused.check_returncode()
    return refused


def _asks(copies, worktree, pr=None):
    pr = pr or copies.checkout(a_pr(1, "o/n"))
    workspace = pr.workspace("PRRT_1", "a" * 40)
    return {
        "report_branch": lambda: copies.report_branch(a_pr(1, "o/n"), str(worktree),
                                                      "main", now=1.0, run_output_at=None),
        "commits_since": lambda: copies.commits_since(worktree, SHA),
        "head_sha": lambda: workspace.head_sha(),
        "descends": lambda: workspace.descends(SHA, OTHER),
        "commit_message": lambda: pr.commit_message(Sha(SHA)),
    }


@pytest.mark.parametrize("ask", ("report_branch", "head_sha"))
def test_a_git_that_hangs_is_logged_with_the_worktree(ask, copies, pr_checkout, tmp_path,
                                                      monkeypatch, caplog):
    monkeypatch.setattr(subprocess, "run", _hangs)

    with caplog.at_level(logging.WARNING):
        _asks(copies, tmp_path, pr_checkout)[ask]()

    assert str(tmp_path) in caplog.text
    assert "timed out" in caplog.text


@pytest.mark.parametrize("ask", ("report_branch", "head_sha", "descends"))
def test_a_git_that_errors_is_logged_with_what_it_said(ask, copies, tmp_path,
                                                       monkeypatch, caplog):
    monkeypatch.setattr(subprocess, "run", _refuses)

    with caplog.at_level(logging.WARNING):
        _asks(copies, tmp_path)[ask]()

    assert str(tmp_path) in caplog.text
    assert "fatal: not a git repository" in caplog.text
