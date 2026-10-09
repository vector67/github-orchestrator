import pytest


def _help(run_cli, *argv):
    ran = run_cli(*argv, "--help")
    assert ran.code == 0
    return " ".join(ran.out.split())


@pytest.mark.parametrize("command,description", [
    ("status", "Show overall system status"),
    ("config", "Print every setting's effective value"),
    ("setup", "Open the board's setup page"),
    ("tutorial", "Open the board's tour"),
    ("queue", "Show pending events for a PR"),
    ("logs", "the service's log"),
    ("runs", "Summarise today's agent runs"),
    ("undismiss", "Clear a PR's dismissal"),
    ("restart-all", "rewrite and reload the watcher's service"),
    ("stop", "stop the watcher's service"),
])
def test_each_command_explains_itself_on_its_own_help_page(run_cli, command, description):
    assert description in _help(run_cli, command)


def test_the_top_level_help_describes_running_the_tool_not_only_inspecting_it(run_cli):
    assert "Run and inspect github-orchestrator" in _help(run_cli)


def test_the_agent_only_thread_command_is_left_out_of_the_top_level_help(run_cli):
    shown = _help(run_cli)
    assert "status" in shown
    assert "thread" not in shown


def test_the_thread_command_still_answers_for_the_agents_that_call_it(run_cli):
    assert "open" in _help(run_cli, "thread")


def _sections(text):
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        if line and not line.startswith(" ") and line.endswith(":"):
            current = line[:-1]
            sections[current] = []
        elif current is not None and line.strip():
            sections[current].append(line.split()[0])
    return sections


def test_help_lists_the_commands_in_their_groups(run_cli):
    ran = run_cli("help")
    assert ran.code == 0
    assert _sections(ran.out) == {
        "everyday": ["open", "status", "logs", "runs"],
        "service": ["start", "stop", "restart", "restart-all"],
        "maintenance": ["update", "doctor", "config", "uninstall", "setup", "skill"],
        "learning": ["tutorial"],
    }


def test_the_full_help_ends_with_the_debugging_commands_after_the_groups(run_cli):
    ran = run_cli("--help")
    assert ran.code == 0
    sections = _sections(ran.out)
    assert list(sections) == ["everyday", "service", "maintenance", "learning", "debugging"]
    assert sections["debugging"] == ["queue", "undismiss"]
    assert ran.out.rstrip().endswith("Clear a PR's dismissal so the watcher reopens its window.")


def test_help_leaves_out_the_debugging_and_agent_commands(run_cli):
    sections = _sections(run_cli("help").out)
    listed = [name for names in sections.values() for name in names]
    assert "debugging" not in sections
    for hidden in ("queue", "undismiss", "thread"):
        assert hidden not in listed


def test_running_the_tool_bare_prints_the_grouped_help(run_cli):
    ran = run_cli()
    assert ran.code == 0
    assert ran.out == run_cli("help").out


def test_help_needs_no_config_on_a_fresh_install(machine, run_cli):
    machine.config_path.unlink()
    for argv in ((), ("help",)):
        ran = run_cli(*argv)
        assert ran.code == 0
        assert "everyday" in ran.out


def test_help_with_a_command_shows_that_command_s_own_page(run_cli):
    ran = run_cli("help", "logs")
    assert ran.code == 0
    assert ran.out == run_cli("logs", "--help").out


@pytest.mark.parametrize("command,example", [
    ("help", "github-orchestrator help logs"),
    ("status", "github-orchestrator status"),
    ("logs", "github-orchestrator logs agent -n 50"),
    ("runs", "github-orchestrator runs"),
    ("start", "github-orchestrator start"),
    ("stop", "github-orchestrator stop --all"),
    ("restart", "github-orchestrator restart"),
    ("restart-all", "github-orchestrator restart-all"),
    ("config", "github-orchestrator config"),
    ("setup", "github-orchestrator setup"),
    ("queue", "github-orchestrator queue 88"),
    ("undismiss", "github-orchestrator undismiss --repo acme/widgets 88"),
])
def test_each_command_s_page_ends_with_an_example(run_cli, command, example):
    assert run_cli(command, "--help").out.rstrip().endswith(f"Example: {example}")


def test_version_prints_the_installed_version(run_cli):
    from importlib import metadata

    ran = run_cli("--version")

    assert ran.code == 0
    assert ran.out == f"github-orchestrator {metadata.version('github-orchestrator')}\n"
