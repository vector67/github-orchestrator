import fcntl
import json
import os
import re
import socket
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pytest

from github_orchestrator.domain import Repo
from tests.cli.scripted_system import Job

HUB = "http://127.0.0.1:8720"
UNIT = "github-orchestrator.service"
PLIST = Path("Library") / "LaunchAgents" / "com.github-orchestrator.watcher.plist"


@dataclass
class Finding:
    level: str
    reason: str
    fix: str = ""


def _findings(out: str) -> list[Finding]:
    found: list[Finding] = []
    for line in out.splitlines():
        level, _, rest = line.strip().partition(" ")
        if level in ("ok", "warn", "FAIL"):
            found.append(Finding(level, rest.strip()))
        elif line.strip().startswith("fix: "):
            found[-1].fix = line.strip().removeprefix("fix: ")
    return found


def _finding(out: str, says: str) -> Finding:
    matching = [finding for finding in _findings(out) if says in finding.reason]
    assert len(matching) == 1, (says, out)
    return matching[0]


@pytest.mark.parametrize(("program", "source"), [
    ("gh", "https://github.com/cli/cli/releases/latest"),
    ("claude", "curl -fsSL https://claude.ai/install.sh | bash"),
    ("git", "xcode-select --install"),
])
def test_a_missing_requirement_fails_and_names_where_to_get_it(machine, run_cli, program, source):
    machine.installed.discard(program)

    ran = run_cli("doctor")

    assert ran.code == 1
    missing = _finding(ran.out, f"{program} is not on PATH")
    assert missing.level == "FAIL"
    assert source in missing.fix
    assert "brew" not in missing.fix


@pytest.mark.parametrize(("program", "source"), [
    ("gh", "the linux_amd64 or linux_arm64 tarball from https://github.com/cli/cli/releases/latest"),
    ("claude", "curl -fsSL https://claude.ai/install.sh | bash"),
    ("git", "sudo apt install git"),
])
def test_on_linux_a_missing_requirement_names_where_linux_gets_it(machine, run_cli, program, source):
    machine.platform = "linux"
    machine.installed.discard(program)

    ran = run_cli("doctor")

    missing = _finding(ran.out, f"{program} is not on PATH")
    assert source in missing.fix
    assert "brew" not in missing.fix


def test_the_configured_claude_command_is_the_one_looked_for(machine, run_cli):
    machine.configure('agent_command = "claude-work"\n')

    ran = run_cli("doctor")

    assert _finding(ran.out, "claude-work is not on PATH").level == "FAIL"


def test_gh_is_found_with_its_version(machine, run_cli):
    machine.system.gh_version = "gh version 2.81.0 (2025-10-01)\nhttps://github.com/cli/cli/releases/tag/v2.81.0\n"

    ran = run_cli("doctor")

    found = _finding(ran.out, "gh 2.81.0")
    assert found.level == "ok"
    assert "/opt/homebrew/bin/gh" in found.reason


def test_a_config_that_does_not_parse_fails_with_its_problem_and_doctor_still_runs(machine, run_cli):
    machine.configure('colour = "blue"\n')

    ran = run_cli("doctor")

    broken = _finding(ran.out, "unknown key 'colour'")
    assert broken.level == "FAIL"
    assert str(machine.config_path) in broken.fix
    assert _finding(ran.out, "git at").level == "ok"


def test_a_config_that_parses_is_ok(machine, run_cli):
    ran = run_cli("doctor")

    assert _finding(ran.out, f"config {machine.config_path} parses").level == "ok"


@pytest.fixture
def installed(machine, tmp_path):
    python = tmp_path / "tools" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    machine.python = str(python)
    machine.system.starts_as = Job(program=str(python))
    machine.system.exec_program = str(python)
    return python


@pytest.fixture
def started(machine, run_cli, installed):
    machine.answering_hubs.add(HUB)
    assert run_cli("start").code == 0
    return machine


@pytest.fixture
def linux(machine):
    machine.platform = "linux"
    return machine


def test_a_missing_launchagent_fails_and_says_to_start(machine, run_cli):
    ran = run_cli("doctor")

    missing = _finding(ran.out, "no LaunchAgent")
    assert missing.level == "FAIL"
    assert str(machine.home / PLIST) in missing.reason
    assert missing.fix == "github-orchestrator start"


def test_a_launchagent_that_is_not_loaded_fails_and_says_to_start(started, run_cli):
    started.system.job = None

    ran = run_cli("doctor")

    unloaded = _finding(ran.out, "not loaded")
    assert (unloaded.level, unloaded.fix) == ("FAIL", "github-orchestrator start")


def test_a_running_launchagent_is_ok_with_its_pid(started, run_cli):
    ran = run_cli("doctor")

    assert _finding(ran.out, "LaunchAgent is running as pid 4242").level == "ok"


def test_a_launchagent_whose_program_is_gone_says_to_restart(started, run_cli, installed):
    installed.unlink()

    ran = run_cli("doctor")

    gone = _finding(ran.out, f"{installed} does not exist")
    assert (gone.level, gone.fix) == ("FAIL", "github-orchestrator restart")


def test_a_code_signing_kill_says_to_restart(started, run_cli):
    started.system.job = Job(state="not running", program=started.python,
                             last_exit="9: Killed: 9", last_exit_reason="OS_REASON_CODESIGNING")

    ran = run_cli("doctor")

    killed = _finding(ran.out, "code-signing")
    assert (killed.level, killed.fix) == ("FAIL", "github-orchestrator restart")


def test_a_launchagent_that_is_not_running_names_its_last_exit(started, run_cli):
    started.system.job = Job(state="not running", program=started.python, last_exit="1")

    ran = run_cli("doctor")

    stopped = _finding(ran.out, "launchd state: not running")
    assert stopped.level == "FAIL"
    assert "last exit code 1" in stopped.reason
    assert "github-orchestrator restart" in stopped.fix


def test_a_requirement_missing_from_the_watchers_path_says_to_restart_with_a_path_that_finds_it(
        started, run_cli):
    started.off_service_path.add("gh")

    ran = run_cli("doctor")

    off = _finding(ran.out, "gh is not on the watcher's PATH")
    assert off.level == "FAIL"
    assert "/usr/bin:/bin" in off.reason
    assert off.fix == "github-orchestrator restart, from a shell whose PATH finds gh"


def test_a_requirement_on_the_watchers_path_is_not_mentioned_twice(started, run_cli):
    ran = run_cli("doctor")

    assert "watcher's PATH" not in ran.out


def test_linux_without_a_user_manager_points_at_running_in_the_foreground(linux, run_cli):
    linux.system.user_manager = False

    ran = run_cli("doctor")

    unreachable = _finding(ran.out, "user manager")
    assert (unreachable.level, unreachable.fix) == (
        "FAIL", "github-orchestrator start --foreground")


def test_linux_without_the_unit_file_says_to_start(linux, run_cli):
    ran = run_cli("doctor")

    missing = _finding(ran.out, "no systemd unit")
    assert (missing.level, missing.fix) == ("FAIL", "github-orchestrator start")


@pytest.fixture
def started_on_linux(linux, run_cli, installed):
    linux.answering_hubs.add(HUB)
    assert run_cli("start").code == 0
    return linux


def test_a_running_unit_is_ok_with_its_pid(started_on_linux, run_cli):
    ran = run_cli("doctor")

    assert _finding(ran.out, f"{UNIT} is enabled and running as pid 4242").level == "ok"


def test_a_disabled_unit_says_to_start(started_on_linux, run_cli):
    started_on_linux.system.disabled.add(UNIT)

    ran = run_cli("doctor")

    disabled = _finding(ran.out, "is disabled")
    assert (disabled.level, disabled.fix) == ("FAIL", "github-orchestrator start")


@pytest.mark.parametrize(("state", "result"), [("activating", "success"),
                                               ("failed", "start-limit-hit"),
                                               ("failed", "exit-code")])
def test_a_unit_restarting_in_a_loop_says_to_restart(started_on_linux, run_cli, state, result):
    started_on_linux.system.units[UNIT] = state
    started_on_linux.system.result = result
    started_on_linux.system.restarts = 5

    ran = run_cli("doctor")

    looping = _finding(ran.out, "restarting in a loop")
    assert looping.level == "FAIL"
    assert "5 restarts" in looping.reason
    assert looping.fix.startswith("github-orchestrator restart")


def test_a_unit_that_is_not_running_names_its_state(started_on_linux, run_cli):
    started_on_linux.system.units[UNIT] = "inactive"

    ran = run_cli("doctor")

    stopped = _finding(ran.out, "systemd state: inactive")
    assert stopped.level == "FAIL"
    assert "github-orchestrator restart" in stopped.fix


def test_a_unit_whose_program_is_gone_says_to_restart(started_on_linux, run_cli, installed):
    installed.unlink()

    ran = run_cli("doctor")

    gone = _finding(ran.out, f"{installed} does not exist")
    assert (gone.level, gone.fix) == ("FAIL", "github-orchestrator restart")


def test_the_units_path_is_the_one_requirements_are_looked_for_on(started_on_linux, run_cli):
    started_on_linux.off_service_path.add("git")

    ran = run_cli("doctor")

    assert _finding(ran.out, "git is not on the watcher's PATH").level == "FAIL"


def test_lingering_off_is_a_warning_with_the_command_that_turns_it_on(started_on_linux, run_cli):
    started_on_linux.system.linger = False

    ran = run_cli("doctor")

    lingering = _finding(ran.out, "lingering is off")
    assert lingering.level == "warn"
    assert lingering.fix == "loginctl enable-linger"


def test_lingering_on_is_ok(started_on_linux, run_cli):
    ran = run_cli("doctor")

    assert _finding(ran.out, "lingering is on").level == "ok"


def test_a_hub_answering_from_the_services_watcher_is_ok(started, run_cli):
    ran = run_cli("doctor")

    assert _finding(ran.out, f"the hub answers at {HUB} from the watcher, pid 4242, "
                             "watching").level == "ok"
    assert _finding(ran.out, "hub_port 8720 is held by this instance's hub").level == "ok"


def test_a_hub_in_another_state_than_its_config_chooses_says_to_restart(started, run_cli):
    started.hub_state = "setup"

    ran = run_cli("doctor")

    behind = _finding(ran.out, f"the hub at {HUB} is in setup")
    assert behind.level == "FAIL"
    assert "its config is watching" in behind.reason
    assert behind.fix == "github-orchestrator restart"


def test_a_watcher_whose_hub_answers_is_running_whatever_its_lock_says(started, run_cli):
    _beat(started, 34)

    ran = run_cli("doctor")

    assert _finding(ran.out, "the watcher last polled 34s ago").level == "ok"


def test_a_hub_that_does_not_answer_says_to_restart(started, run_cli):
    started.answering_hubs.clear()

    ran = run_cli("doctor")

    silent = _finding(ran.out, f"the hub at {HUB} does not answer")
    assert silent.level == "FAIL"
    assert silent.fix.startswith("github-orchestrator restart")


def test_a_hub_answering_from_another_process_names_both_pids(started, run_cli):
    started.hub_pid = 99

    ran = run_cli("doctor")

    stray = _finding(ran.out, "from pid 99")
    assert stray.level == "FAIL"
    assert "4242" in stray.reason
    assert stray.fix == "stop pid 99, then github-orchestrator restart"


def test_a_hub_port_nothing_holds_is_free(machine, run_cli):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    machine.configure(f"hub_port = {port}\n")

    ran = run_cli("doctor")

    assert _finding(ran.out, f"hub_port {port} is free").level == "ok"


def test_a_hub_port_another_program_holds_fails_with_how_to_move(machine, run_cli):
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        port = holder.getsockname()[1]
        machine.configure(f"hub_port = {port}\n")

        ran = run_cli("doctor")

    taken = _finding(ran.out, f"hub_port {port} is held by a program that does not answer")
    assert taken.level == "FAIL"
    assert str(machine.config_path) in taken.fix
    assert f"lsof -nP -iTCP:{port} -sTCP:LISTEN" in taken.fix


@contextmanager
def _watcher_lock(machine):
    lock = machine.settings().watcher_lock
    lock.write_text("")
    with open(lock, "a") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def _beat(machine, seconds_ago):
    stamp = machine.now - timedelta(seconds=seconds_ago)
    machine.settings().watcher_heartbeat.write_text(stamp.isoformat())


def test_a_recent_poll_is_ok(machine, run_cli):
    _beat(machine, 34)
    with _watcher_lock(machine):
        ran = run_cli("doctor")

    assert _finding(ran.out, "the watcher last polled 34s ago").level == "ok"


def test_a_failing_watcher_names_its_last_error(machine, run_cli):
    _beat(machine, 600)
    machine.settings().watcher_failures.write_text(
        json.dumps({"consecutive": 3, "last_error": "gh exploded"}))
    with _watcher_lock(machine):
        ran = run_cli("doctor")

    failing = _finding(ran.out, "gh exploded")
    assert failing.level == "FAIL"
    assert "last good poll 10m ago" in failing.reason
    assert failing.fix == "github-orchestrator logs shows the whole error"


def test_a_watcher_that_stopped_polling_says_to_restart(machine, run_cli):
    _beat(machine, 3600)
    with _watcher_lock(machine):
        ran = run_cli("doctor")

    overdue = _finding(ran.out, "the watcher last polled 1h ago")
    assert (overdue.level, overdue.fix) == ("FAIL", "github-orchestrator restart")


def test_a_watcher_that_is_not_running_says_to_restart(machine, run_cli):
    _beat(machine, 34)

    ran = run_cli("doctor")

    stopped = _finding(ran.out, "the watcher is not running")
    assert (stopped.level, stopped.fix) == ("FAIL", "github-orchestrator restart")


def test_a_watcher_that_has_not_polled_yet_is_a_warning(machine, run_cli):
    with _watcher_lock(machine):
        ran = run_cli("doctor")

    assert _finding(ran.out, "has not finished a poll yet").level == "warn"


REPO = "octocat/hello-world"


@pytest.fixture
def clone(machine, tmp_path):
    path = tmp_path / "clones" / "hello-world"
    path.mkdir(parents=True)
    machine.config_path.write_text(
        f'gh_account = "octocat"\n[[repos]]\nrepo = "{REPO}"\nlocal_path = "{path}"\n')
    machine.github.repos.add(Repo.parse(REPO))
    machine.system.remotes[str(path)] = f"https://github.com/{REPO}.git"
    return path


def test_a_token_for_the_account_is_ok(machine, run_cli):
    ran = run_cli("doctor")

    assert _finding(ran.out, "gh has a token for octocat").level == "ok"


def test_no_token_for_the_account_says_to_log_in(machine, run_cli):
    machine.github.tokens.clear()

    ran = run_cli("doctor")

    refused = _finding(ran.out, "gh auth token --user octocat failed")
    assert (refused.level, refused.fix) == ("FAIL", "gh auth login, as octocat")


def test_a_repo_the_account_can_see_is_ok(clone, run_cli):
    ran = run_cli("doctor")

    assert _finding(ran.out, f"octocat can see {REPO}").level == "ok"


def test_a_repo_the_account_cannot_see_names_access_and_the_repo_scope(machine, clone, run_cli):
    machine.github.repos.clear()

    ran = run_cli("doctor")

    unseen = _finding(ran.out, f"gh cannot see {REPO} as octocat")
    assert unseen.level == "FAIL"
    assert "gh auth refresh --scopes repo" in unseen.fix


def test_a_clone_whose_origin_is_the_repo_is_ok(clone, run_cli):
    ran = run_cli("doctor")

    assert _finding(ran.out, f"the clone at {clone} has origin {REPO}").level == "ok"


@pytest.mark.parametrize("url", [f"git@github.com:{REPO}.git", f"https://github.com/{REPO}",
                                 f"ssh://git@github.com/{REPO}.git"])
def test_every_way_of_writing_a_github_remote_is_read(machine, clone, run_cli, url):
    machine.system.remotes[str(clone)] = url

    ran = run_cli("doctor")

    assert _finding(ran.out, f"has origin {REPO}").level == "ok"


def test_a_missing_clone_says_how_to_clone_it(machine, clone, run_cli):
    clone.rmdir()

    ran = run_cli("doctor")

    missing = _finding(ran.out, f"no clone of {REPO} at {clone}")
    assert (missing.level, missing.fix) == ("FAIL", f"gh repo clone {REPO} {clone}")


def test_a_clone_that_is_not_a_git_repository_fails(machine, clone, run_cli):
    del machine.system.remotes[str(clone)]

    ran = run_cli("doctor")

    assert _finding(ran.out, f"{clone} is not a git repository").level == "FAIL"


def test_a_clone_of_another_repo_says_how_to_point_it_back(machine, clone, run_cli):
    machine.system.remotes[str(clone)] = "https://github.com/someone/else.git"

    ran = run_cli("doctor")

    elsewhere = _finding(ran.out, "origin is https://github.com/someone/else.git")
    assert elsewhere.level == "FAIL"
    assert elsewhere.fix == (f"git -C {clone} remote set-url origin "
                             f"https://github.com/{REPO}.git")


def test_each_watched_repo_gets_its_own_access_and_clone_check(machine, clone, run_cli):
    gadgets = clone.parent / "gadgets"
    gadgets.mkdir()
    machine.config_path.write_text(
        machine.config_path.read_text()
        + f'[[repos]]\nrepo = "acme/gadgets"\nlocal_path = "{gadgets}"\n')

    ran = run_cli("doctor")

    assert _finding(ran.out, f"octocat can see {REPO}").level == "ok"
    assert _finding(ran.out, f"the clone at {clone} has origin {REPO}").level == "ok"
    unseen = _finding(ran.out, "gh cannot see acme/gadgets as octocat")
    assert unseen.level == "FAIL"
    assert _finding(ran.out, f"{gadgets} is not a git repository").level == "FAIL"


def test_an_incomplete_config_skips_github_and_the_repo(machine, run_cli):
    machine.config_path.write_text("")

    ran = run_cli("doctor")

    assert "gh has a token" not in ran.out
    assert "can see" not in ran.out


CONNECTED = "atlassian: https://mcp.atlassian.com/v1/mcp (HTTP) - ✔ Connected\n"


def _skill(machine):
    return machine.home / ".claude" / "skills" / "rebase-on-main"


def test_the_rebase_skill_in_place_is_ok(machine, run_cli):
    _skill(machine).mkdir(parents=True)

    ran = run_cli("doctor")

    assert _finding(ran.out, "rebase-on-main skill is in").level == "ok"


def test_a_missing_rebase_skill_is_a_warning_fixed_by_the_skill_command(machine, run_cli):
    ran = run_cli("doctor")

    missing = _finding(ran.out, "rebase-on-main skill is not in")
    assert missing.level == "warn"
    assert missing.fix == "github-orchestrator skill"


def test_a_connected_atlassian_server_is_ok(machine, run_cli):
    machine.system.mcp_list = CONNECTED

    ran = run_cli("doctor")

    assert _finding(ran.out, "Atlassian MCP server is connected").level == "ok"


def test_a_missing_atlassian_server_is_a_warning(machine, run_cli):
    ran = run_cli("doctor")

    missing = _finding(ran.out, "Atlassian MCP server")
    assert missing.level == "warn"
    assert "claude mcp add" in missing.fix


def test_an_atlassian_server_that_needs_authentication_is_a_warning(machine, run_cli):
    machine.system.mcp_list = "claude.ai Atlassian MCP: https://mcp.atlassian.com/v2/mcp - ! Needs authentication\n"

    ran = run_cli("doctor")

    assert _finding(ran.out, "Atlassian MCP server is not connected").level == "warn"


def test_a_failing_mcp_list_says_the_atlassian_server_could_not_be_checked(machine, run_cli):
    machine.system.mcp_list_exit = 1

    ran = run_cli("doctor")

    assert _finding(ran.out, "could not check for the Atlassian MCP server").level == "warn"


@pytest.fixture
def codex(machine):
    machine.configure('agent = "codex"\nagent_command = "codex"\n')
    machine.installed.add("codex")
    return machine


def test_a_codex_instance_finds_codex_and_its_login(codex, run_cli):
    ran = run_cli("doctor")

    assert _finding(ran.out, "codex at /opt/homebrew/bin/codex").level == "ok"
    assert _finding(ran.out, "codex is logged in: Logged in using ChatGPT").level == "ok"
    assert ["codex", "login", "status"] in [call.cmd for call in codex.system.calls]


def test_a_codex_instance_asks_nothing_of_claude(codex, run_cli):
    codex.installed.discard("claude")

    ran = run_cli("doctor")

    assert "claude" not in ran.out
    assert "Atlassian" not in ran.out
    assert not [call for call in codex.system.calls if call.cmd[-2:] == ["mcp", "list"]]


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_a_codex_instance_without_codex_says_where_to_get_it(codex, run_cli, platform):
    codex.platform = platform
    codex.installed.discard("codex")

    ran = run_cli("doctor")

    missing = _finding(ran.out, "codex is not on PATH")
    assert missing.level == "FAIL"
    assert "npm install -g @openai/codex" in missing.fix


def test_a_codex_that_is_not_logged_in_says_to_log_in(codex, run_cli):
    codex.system.login_status = "Not logged in\n"
    codex.system.login_status_exit = 1

    ran = run_cli("doctor")

    refused = _finding(ran.out, "codex is not logged in: Not logged in")
    assert (refused.level, refused.fix) == ("FAIL", "codex login")


def test_a_codex_instance_looks_for_the_rebase_skill_where_codex_reads_skills(codex, run_cli):
    ran = run_cli("doctor")

    missing = _finding(ran.out, "rebase-on-main skill is not in")
    assert str(codex.home / ".agents" / "skills") in missing.reason
    assert missing.fix == "github-orchestrator skill"


def test_missing_notifier_apps_are_a_warning_with_how_to_build_them(machine, run_cli):
    machine.desktop.notifier_apps = False

    ran = run_cli("doctor")

    missing = _finding(ran.out, "notifier apps are missing")
    assert (missing.level, missing.fix) == ("warn", "sh build.sh")


def test_ready_notifications_are_ok(machine, run_cli):
    ran = run_cli("doctor")

    assert _finding(ran.out, "desktop notifications are set up").level == "ok"


def test_the_board_ports_in_use_are_reported(machine, run_cli):
    ran = run_cli("doctor")

    assert re.fullmatch(r"\d+ of 100 board ports are in use",
                        _finding(ran.out, "board ports").reason)


def test_each_instance_is_checked_under_its_own_name(machine, run_cli):
    work = machine.another_instance("work")

    ran = run_cli("doctor")

    default, named = ran.out.split("\nInstance work\n")
    assert "Default instance\n" in default
    assert f"config {work.config_path} parses" in named
    assert f"config {machine.config_path} parses" in default
    assert "board ports" not in named


INSTALLER = ("curl -LsSf https://github.com/vector67/github-orchestrator/releases/latest/download/"
             "install.sh | sh")


def _venv(machine, venv, receipt=None):
    command = venv / "bin" / "github-orchestrator"
    command.parent.mkdir(parents=True)
    command.touch()
    (venv / "bin" / "python").touch()
    if receipt is not None:
        (venv / "uv-receipt.toml").write_text(receipt)
    machine.python = str(venv / "bin" / "python")
    return command


def _on_path(machine, tmp_path, target):
    link = tmp_path / "local-bin" / "github-orchestrator"
    link.parent.mkdir(exist_ok=True)
    link.symlink_to(target)
    machine.located["github-orchestrator"] = str(link)
    return link


EDITABLE = '[tool]\nrequirements = [{ name = "github-orchestrator", editable = "/src/gho" }]\n'


def test_a_uv_tool_install_names_its_version_folder_and_source(machine, run_cli, tmp_path):
    venv = tmp_path / "uv" / "tools" / "github-orchestrator"
    _venv(machine, venv, EDITABLE)

    ran = run_cli("doctor")

    install = _finding(ran.out, "a uv tool in")
    assert install.level == "ok"
    assert re.fullmatch(rf"github-orchestrator \S+, a uv tool in {venv}, installed from "
                        r"/src/gho \(editable\)", install.reason)


@pytest.mark.parametrize(("requirement", "source"), [
    ('{ name = "github-orchestrator", path = "/dl/gho-0.4.0-py3-none-any.whl" }',
     "/dl/gho-0.4.0-py3-none-any.whl"),
    ('{ name = "github-orchestrator", url = "https://example.com/gho.whl" }',
     "https://example.com/gho.whl"),
    ('{ name = "github-orchestrator" }', "the package index"),
])
def test_the_receipt_names_where_the_tool_came_from(machine, run_cli, tmp_path, requirement,
                                                    source):
    _venv(machine, tmp_path / "tool", f"[tool]\nrequirements = [{requirement}]\n")

    ran = run_cli("doctor")

    assert _finding(ran.out, "a uv tool in").reason.endswith(f"installed from {source}")


def test_an_install_from_a_checkout_is_a_warning_with_the_editable_tool_install(
        machine, run_cli, tmp_path):
    checkout = tmp_path / "checkout"
    _venv(machine, checkout / ".venv")
    (checkout / "pyproject.toml").touch()

    ran = run_cli("doctor")

    old = _finding(ran.out, "not a uv tool install")
    assert old.level == "warn"
    assert old.fix == f"uv tool install --force --editable {checkout}"


def test_an_install_that_is_neither_a_tool_nor_a_checkout_points_at_the_installer(
        machine, run_cli, tmp_path):
    _venv(machine, tmp_path / "somewhere")

    ran = run_cli("doctor")

    assert _finding(ran.out, "not a uv tool install").fix == INSTALLER


def test_the_command_on_path_that_is_the_tools_own_is_ok(machine, run_cli, tmp_path):
    command = _venv(machine, tmp_path / "tool", EDITABLE)
    link = _on_path(machine, tmp_path, command)

    ran = run_cli("doctor")

    assert _finding(ran.out, f"github-orchestrator on PATH ({link}) is the uv tool's command"
                    ).level == "ok"


def test_no_command_on_path_says_to_put_the_tools_folder_on_it(machine, run_cli, tmp_path):
    _venv(machine, tmp_path / "tool", EDITABLE)
    machine.installed.discard("github-orchestrator")

    ran = run_cli("doctor")

    missing = _finding(ran.out, "github-orchestrator is not on PATH")
    assert (missing.level, missing.fix) == ("FAIL", "uv tool update-shell, then open a new terminal")


def test_a_leftover_link_into_a_checkout_fails_and_says_how_to_put_the_tool_back(
        machine, run_cli, tmp_path):
    _venv(machine, tmp_path / "tool", EDITABLE)
    checkout = tmp_path / "checkout"
    leftover = checkout / ".venv" / "bin" / "github-orchestrator"
    leftover.parent.mkdir(parents=True)
    leftover.touch()
    (checkout / "pyproject.toml").touch()
    link = _on_path(machine, tmp_path, leftover)

    ran = run_cli("doctor")

    stale = _finding(ran.out, f"is a link into the checkout at {checkout}")
    assert stale.level == "FAIL"
    assert str(link) in stale.reason
    assert stale.fix == "uv tool install --force --editable /src/gho"


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_a_healthy_install_is_all_ok_and_exits_0(machine, run_cli, tmp_path, clone, platform):
    machine.platform = platform
    command = _venv(machine, tmp_path / "uv-tool", EDITABLE)
    _on_path(machine, tmp_path, command)
    machine.system.starts_as = Job(program=machine.python)
    machine.system.exec_program = machine.python
    machine.answering_hubs.add(HUB)
    assert run_cli("start").code == 0
    _skill(machine).mkdir(parents=True)
    machine.system.mcp_list = CONNECTED
    _beat(machine, 34)

    with _watcher_lock(machine):
        ran = run_cli("doctor")

    assert ran.code == 0, ran.out
    assert {finding.level for finding in _findings(ran.out)} == {"ok"}


def test_a_claude_command_with_settings_in_front_is_looked_for_by_its_program(machine, run_cli):
    machine.configure('agent_command = "CLAUDE_CONFIG_DIR=~/.claude-work claude"\n')
    machine.system.mcp_list = CONNECTED

    ran = run_cli("doctor")

    assert _finding(ran.out, "claude at /opt/homebrew/bin/claude").level == "ok"
    assert _finding(ran.out, "Atlassian MCP server is connected").level == "ok"
    listed = [call.cmd for call in machine.system.calls if call.cmd[-2:] == ["mcp", "list"]]
    assert listed == [["env", f"CLAUDE_CONFIG_DIR={os.path.expanduser('~/.claude-work')}", "claude",
                       "mcp", "list"]]


def test_without_gh_the_github_checks_leave_the_fix_to_the_gh_line(machine, run_cli):
    machine.installed.discard("gh")

    ran = run_cli("doctor")

    assert "gh auth login" not in ran.out
    assert "gh has a token" not in ran.out
    assert _finding(ran.out, "gh is not on PATH").level == "FAIL"


def test_lingering_is_reported_before_the_unit_is_written(linux, run_cli):
    linux.system.linger = False

    ran = run_cli("doctor")

    assert _finding(ran.out, "lingering is off").level == "warn"


def test_lingering_is_reported_when_the_user_manager_is_gone(linux, run_cli):
    linux.system.user_manager = False
    linux.system.linger = False

    ran = run_cli("doctor")

    assert _finding(ran.out, "lingering is off").level == "warn"


def test_a_watcher_whose_hub_is_in_setup_polls_nothing_and_that_is_not_its_fault(
        started, run_cli):
    started.config_path.write_text("")
    started.hub_state = "setup"

    ran = run_cli("doctor")

    assert _finding(ran.out, "the watcher polls nothing until the config is complete").level == "ok"


def test_a_newer_release_the_hub_has_seen_is_a_warning_with_the_update_command(started, run_cli):
    started.newest_release = {"version": "0.6.0", "checked_at": "2026-09-24T08:00:00+00:00",
                              "newer": True}

    found = _finding(run_cli("doctor").out, "0.6.0 is out")

    assert found.level == "warn"
    assert found.fix == "github-orchestrator update"


def test_the_old_one_repo_keys_are_a_warning_that_restart_rewrites(machine, run_cli):
    machine.config_path.write_text('gh_account = "octocat"\nwatch_repo = "octocat/hello-world"\n'
                                   'local_path = "/tmp/github-orchestrator-tests/hello-world"\n')

    found = _finding(run_cli("doctor").out, "watch_repo and local_path")

    assert found.level == "warn"
    assert "github-orchestrator restart" in found.fix


def test_a_tool_installed_from_a_downloaded_wheel_is_reinstalled_with_the_installer(
        machine, run_cli, tmp_path):
    _venv(machine, tmp_path / "tool", '[tool]\nrequirements = [{ name = "github-orchestrator", '
                                      'path = "/tmp/x/github_orchestrator-0.4.0-py3-none-any.whl" }]\n')
    _on_path(machine, tmp_path, tmp_path / "elsewhere")

    ran = run_cli("doctor")

    assert _finding(ran.out, "github-orchestrator on PATH").fix == INSTALLER


def test_a_config_still_waiting_for_setup_is_a_warning_that_points_at_the_setup_page(
        machine, run_cli):
    machine.config_path.unlink()

    found = _finding(run_cli("doctor").out, "the config file does not exist")

    assert found.level == "warn"
    assert found.fix == "github-orchestrator setup"
