import os
import signal

import pytest

from github_orchestrator.pr_manager import Front
from tests.builders import a_pr
from tests.pr_manager.support import (
    PR,
    REPO,
    manager_over,
)

THE_PR = a_pr(PR, REPO)


def test_sigterm_inside_the_browser_fronts_session_raises_system_exit_and_the_handler_is_restored(
        settings, tmp_path):
    before = signal.getsignal(signal.SIGTERM)
    front = manager_over(settings, worktree=tmp_path).container.get(Front)
    with pytest.raises(SystemExit, match="terminated by signal 15"):
        with front.session():
            os.kill(os.getpid(), signal.SIGTERM)
    assert signal.getsignal(signal.SIGTERM) == before

