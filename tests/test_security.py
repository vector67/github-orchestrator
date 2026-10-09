import subprocess
import time
from typing import Any

from github_orchestrator.change_detection import CiSucceeded
from tests.builders import a_pr
from tests.desktop.scripted_mac import ScriptedMac
from tests.desktop.support import real_desktop
from tests.notifications.support import LONG_AWAKE, Clock, opened
from tests.pr_event_queue.support import ci_failed
from tests.pr_manager.support import manager_over, run_manager, seed_state


class RecordingMac(ScriptedMac):
    def __init__(self) -> None:
        super().__init__()
        self.argvs: list[list[str]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        self.argvs.append(list(argv))
        return super().__call__(argv, **kwargs)


class TestCheckNameFlowsIntoNotify:
    def test_a_check_name_reaches_the_notification_as_one_argument_shown_as_written(self, tmp_path):
        evil_check_name = ('\\" & (do shell script "echo PWNED > /tmp/x") & "\n'
                           "end tell\ndo shell script \"id\" -- '$(id)' `id` \\\\")
        mac = RecordingMac()
        notifications, courier = opened(tmp_path, real_desktop(mac=mac), Clock())

        notifications.pr_status.changed(a_pr(1, "o/n"), CiSucceeded((evil_check_name,)))
        courier.deliver(LONG_AWAKE, None)

        [argv] = mac.argvs
        assert argv[0] == "open"
        assert argv.index("--args") < argv.index("--body")
        assert argv[argv.index("--body") + 1] == f"Checks passed: {evil_check_name} (success)"
        assert mac.world.announcements[0].body == f"Checks passed: {evil_check_name} (success)"


class TestAnsiEscapesInChangesFile:
    def test_terminal_escapes_in_ci_failure_output_are_stripped_from_the_changes_file(self, tmp_path, settings):
        worktree = tmp_path / "wt"
        worktree.mkdir()

        evil_text = "\x1b]8;;file:///etc/passwd\x07click\x1b]8;;\x07 \x1b[2Jcleared"
        manager = manager_over(settings, is_author=True, worktree=worktree)
        manager.event_queue.add(a_pr(1, "o/n"), ci_failed(evil_text))
        manager.run()

        content = manager.pr_processes.read(worktree)
        assert "\x1b" not in content
        assert "\x07" not in content
        assert "click cleared" in content


class TestJiraRegexReDoS:
    def test_jira_regex_handles_pathological_input_in_linear_time(self, tmp_path, settings):
        evil = "A" * 5_000 + "-" + "1" * 5_000
        seed_state(settings, branch=evil)
        start = time.process_time()
        run_manager(settings, is_author=True, worktree=tmp_path)
        elapsed = time.process_time() - start
        assert elapsed < 1.0, f"Regex took {elapsed:.2f}s — possible ReDoS"
