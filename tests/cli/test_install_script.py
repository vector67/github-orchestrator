import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.cli.support import Ran

SCRIPT = Path(__file__).resolve().parents[2] / "install.sh"


def _assigned() -> dict[str, str]:
    return dict(re.findall(r'^([A-Z_]+)="([^"$]*)"$', SCRIPT.read_text(), re.MULTILINE))


def _by_hand() -> list[str]:
    text = SCRIPT.read_text()
    block = text[text.index("by_hand() {"):text.index("\n}\n", text.index("by_hand() {"))]
    lines = re.findall(r'note "([^"]*)"', block)
    names = _assigned()
    return [re.sub(r"\$([A-Z_]+)", lambda found: names[found.group(1)], line) for line in lines]


def _sh(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sh", str(SCRIPT), *argv], capture_output=True, text=True, timeout=30,
                          stdin=subprocess.DEVNULL)


@pytest.mark.no_replay
@pytest.mark.skipif(shutil.which("dash") is None, reason="dash is the strict POSIX sh to parse with")
def test_the_installer_is_plain_posix_sh():
    parsed = subprocess.run(["dash", "-n", str(SCRIPT)], capture_output=True, text=True)

    assert parsed.returncode == 0, parsed.stderr


@pytest.mark.no_replay
def test_help_lists_every_flag_and_its_environment_twin():
    shown = _sh("--help")

    assert shown.returncode == 0
    for flag in ("--yes", "--notifier", "--version X", "--no-modify-path", "--no-open",
                 "--wheel URL|PATH", "--linger"):
        assert flag in shown.stdout
    for twin in ("YES", "NOTIFIER", "VERSION", "NO_PATH", "NO_OPEN", "WHEEL", "LINGER",
                 "GITHUB_TOKEN"):
        assert f"GITHUB_ORCHESTRATOR_{twin}" in shown.stdout


@pytest.mark.no_replay
def test_an_unknown_option_is_refused_before_anything_runs():
    refused = _sh("--colour")

    assert refused.returncode == 2
    assert "unknown option: --colour" in refused.stderr


@pytest.mark.parametrize(("program", "platform"), [
    ("gh", "darwin"), ("gh", "linux"), ("claude", "darwin"), ("git", "darwin"),
    ("claude", "linux")])
def test_doctor_names_the_same_source_for_a_requirement_as_the_installer(
        machine, run_cli, program, platform):
    machine.platform = platform
    machine.installed.discard(program)

    ran: Ran = run_cli("doctor")

    [fix] = [line.strip().removeprefix("fix: ") for line, after in
             zip(ran.out.splitlines(), ran.out.splitlines()[1:] + [""])
             if f"{program} is not on PATH" in line for line in [after]]
    assert any(source in fix for source in _by_hand()), (fix, _by_hand())


def test_the_installer_installs_the_tool_on_the_python_update_installs_it_on():
    assert _assigned()["TOOL_PYTHON"] == "3.12"
    assert 'uv tool install --force --python "$TOOL_PYTHON"' in SCRIPT.read_text()


def test_the_installer_asks_the_release_api_update_and_the_daily_check_ask():
    assert _assigned()["REPO"] == "vector67/github-orchestrator"
    assert "https://api.github.com/repos/$REPO/releases" in SCRIPT.read_text()


@pytest.mark.no_replay
@pytest.mark.skipif(sys.platform != "darwin",
                    reason="on Linux the installer first needs a user manager, which CI lacks")
def test_with_no_terminal_and_no_yes_the_installer_says_what_it_would_do_and_changes_nothing(
        tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    ran = subprocess.run(["sh", str(SCRIPT)], capture_output=True, text=True, timeout=60,
                         stdin=subprocess.DEVNULL, start_new_session=True,
                         env={"HOME": str(home), "PATH": "/usr/bin:/bin"})

    assert ran.returncode == 1
    assert "no terminal to ask on" in ran.stdout + ran.stderr
    assert "| sh -s -- -y" in ran.stdout + ran.stderr
    assert list(home.iterdir()) == []


@pytest.mark.no_replay
def test_help_lists_the_skill_flags_and_their_environment_twin():
    shown = _sh("--help")

    for flag in ("--skill", "--no-skill", "GITHUB_ORCHESTRATOR_SKILL=yes|no"):
        assert flag in shown.stdout


_STUBS = Path(__file__).resolve().parent / "install_stubs"


def _installed(tmp_path: Path, *argv: str, state: str, **environment: str) -> tuple[str, list[str]]:
    stubs = tmp_path / "stubs"
    tool_bin = tmp_path / "tool-bin"
    home = tmp_path / "home"
    for folder in (stubs, tool_bin, home):
        folder.mkdir(exist_ok=True)
    for name in ("uv", "gh", "claude", "codex", "github-orchestrator"):
        (tool_bin if name == "github-orchestrator" else stubs).joinpath(name).symlink_to(_STUBS / name)
    wheel = tmp_path / "github_orchestrator-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"")
    calls = tmp_path / "calls"
    calls.touch()
    ran = subprocess.run(
        ["sh", str(SCRIPT), "--wheel", str(wheel), "--no-open", *argv],
        capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
        start_new_session=True,
        env={"HOME": str(home), "PATH": f"{stubs}:{tool_bin}:/usr/bin:/bin",
             "TOOL_BIN": str(tool_bin), "CALLS": str(calls), "SKILL_STATE": state,
             **environment})
    assert ran.returncode == 0, ran.stdout + ran.stderr
    return ran.stdout, calls.read_text().splitlines()


_ON_A_MAC = pytest.mark.skipif(
    sys.platform != "darwin", reason="on Linux the installer first needs a user manager")


@pytest.mark.no_replay
@_ON_A_MAC
def test_yes_installs_a_missing_rebase_skill(tmp_path):
    said, calls = _installed(tmp_path, "-y", state="missing")

    assert "skill" in calls
    assert "rebase-on-main" in said


@pytest.mark.no_replay
@_ON_A_MAC
@pytest.mark.parametrize(("argv", "environment"), [
    (("--no-skill",), {}), ((), {"GITHUB_ORCHESTRATOR_SKILL": "no"})])
def test_no_skill_leaves_a_missing_skill_out_and_names_the_command_that_adds_it(
        tmp_path, argv, environment):
    said, calls = _installed(tmp_path, "-y", *argv, state="missing", **environment)

    assert "skill" not in calls
    assert "github-orchestrator skill" in said


@pytest.mark.no_replay
@_ON_A_MAC
@pytest.mark.parametrize("argv", [(), ("--skill",)])
def test_yes_leaves_a_different_skill_alone_and_says_so(tmp_path, argv):
    said, calls = _installed(tmp_path, "-y", *argv, state="different")

    assert [call for call in calls if call.startswith("skill") and call != "skill --status"] == []
    assert "github-orchestrator skill --replace" in said


@pytest.mark.no_replay
@_ON_A_MAC
def test_a_current_skill_is_left_as_it_is(tmp_path):
    said, calls = _installed(tmp_path, "-y", state="current")

    assert calls.count("skill") == 0
    assert "skill --status" in calls


@pytest.mark.no_replay
def test_help_lists_the_agent_flag_and_its_environment_twin():
    shown = _sh("--help")

    for said in ("--agent claude|codex", "GITHUB_ORCHESTRATOR_AGENT=claude|codex"):
        assert said in shown.stdout


@pytest.mark.no_replay
def test_an_agent_the_installer_does_not_know_is_refused_before_anything_runs():
    refused = _sh("--agent", "gemini")

    assert refused.returncode == 2
    assert "claude or codex, not gemini" in refused.stderr


def _config(tmp_path: Path) -> Path:
    return tmp_path / "home" / ".config" / "github-orchestrator" / "config.toml"


@pytest.mark.no_replay
@_ON_A_MAC
@pytest.mark.parametrize(("argv", "environment"), [
    (("--agent", "codex"), {}), ((), {"GITHUB_ORCHESTRATOR_AGENT": "codex"})])
def test_choosing_codex_writes_it_into_the_config_and_finds_codex(tmp_path, argv, environment):
    said, calls = _installed(tmp_path, "-y", *argv, state="missing", **environment)

    assert _config(tmp_path).read_text() == 'agent = "codex"\n'
    assert "codex-cli 0.9.0" in said
    assert "~/.agents/skills" in said
    assert "skill" in calls


@pytest.mark.no_replay
@_ON_A_MAC
def test_yes_alone_keeps_claude_and_writes_no_agent(tmp_path):
    said, _ = _installed(tmp_path, "-y", state="missing")

    assert not _config(tmp_path).exists()
    assert "~/.claude/skills" in said


@pytest.mark.no_replay
@_ON_A_MAC
def test_choosing_codex_for_a_config_already_there_puts_the_agent_above_its_tables(tmp_path):
    config = _config(tmp_path)
    config.parent.mkdir(parents=True)
    kept = 'gh_account = "octocat"\n\n[[repos]]\nrepo = "acme/widgets"\nlocal_path = "/src/w"\n'
    config.write_text(kept)

    _installed(tmp_path, "-y", "--agent", "codex", state="current")

    assert config.read_text() == 'agent = "codex"\n' + kept


@pytest.mark.no_replay
@_ON_A_MAC
def test_choosing_claude_for_a_codex_config_switches_it_back(tmp_path):
    config = _config(tmp_path)
    config.parent.mkdir(parents=True)
    config.write_text('agent = "codex"\ngh_account = "octocat"\n')

    _installed(tmp_path, "-y", "--agent", "claude", state="current")

    assert config.read_text() == 'agent = "claude"\ngh_account = "octocat"\n'


def test_doctor_and_the_installer_name_the_same_place_to_get_codex(machine, run_cli):
    machine.configure('agent = "codex"\nagent_command = "codex"\n')

    ran: Ran = run_cli("doctor")

    [fix] = [after.strip().removeprefix("fix: ") for line, after in
             zip(ran.out.splitlines(), ran.out.splitlines()[1:] + [""])
             if "codex is not on PATH" in line]
    assert _assigned()["CODEX_INSTALL"] in fix
