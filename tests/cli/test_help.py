import re

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


def test_the_thread_command_still_answers_for_the_agents_that_call_it(run_cli):
    assert "open" in _help(run_cli, "thread")


def _accepted(run_cli, *argv):
    ran = run_cli(*argv, "not-a-command")
    assert ran.code == 2
    choices = re.search(r"invalid choice: .*\(choose from (.*)\)", ran.err).group(1)
    return [choice.strip("'") for choice in choices.split(", ")]


def _entries(page, section):
    lines = page.split(f"\n{section}:\n", 1)[1].split("\n\n", 1)[0].splitlines()
    entries = {}
    for index, line in enumerate(lines):
        if not re.match(r"  \S", line):
            continue
        name, _, said = line.strip().partition("  ")
        following = lines[index + 1] if index + 1 < len(lines) else ""
        continued = re.match(r" {3,}\S", following) and not re.match(r"  -", following)
        entries[name.split(",")[-1].split()[0]] = said.strip() or (following.strip() if continued else "")
    return entries


def _verbs(page):
    listing = page.split("\npositional arguments:\n", 1)[1].split("\n\n", 1)[0].splitlines()
    verbs = {}
    for index, line in enumerate(listing):
        if re.match(r" {4}\S", line):
            verb, _, said = line.strip().partition(" ")
            following = listing[index + 1] if index + 1 < len(listing) else ""
            verbs[verb] = said.strip() or (following.strip() if re.match(r" {5,}\S", following) else "")
    return verbs


def _pages(run_cli):
    pages = [(command,) for command in _accepted(run_cli)]
    pages += [("thread", verb) for verb in _accepted(run_cli, "thread")]
    return pages


def test_the_full_help_lists_every_command_the_parser_accepts(run_cli):
    listed = [name for names in _sections(run_cli("--help").out).values() for name in names]
    assert sorted(listed) == sorted(_accepted(run_cli))


def test_the_thread_help_lists_every_verb_the_parser_accepts_with_its_summary(run_cli):
    verbs = _verbs(run_cli("thread", "--help").out)
    accepted = _accepted(run_cli, "thread")
    assert sorted(verbs) == sorted(accepted)
    assert [verb for verb in accepted if not verbs[verb]] == []


def test_help_with_a_command_or_a_thread_verb_shows_its_own_page(run_cli):
    for argv in _pages(run_cli):
        asked = run_cli("help", *argv)
        assert asked.code == 0, argv
        assert asked.out == run_cli(*argv, "--help").out, argv


def test_every_command_and_thread_verb_describes_itself_on_its_own_page(run_cli):
    undescribed = []
    for argv in _pages(run_cli):
        page = run_cli(*argv, "--help").out
        after_usage = "\n" + page.split("\n\n", 1)[1]
        between = after_usage.split("\noptions:\n", 1)[0].split("\npositional arguments:\n", 1)[0]
        if not between.strip():
            undescribed.append(argv)
    assert undescribed == []


def test_every_option_and_argument_of_every_command_says_what_it_takes(run_cli):
    unexplained = []
    for argv in _pages(run_cli):
        page = run_cli(*argv, "--help").out
        sections = ["options"] + (["positional arguments"] if argv != ("thread",) else [])
        for section in sections:
            if f"\n{section}:\n" in page:
                unexplained += [(*argv, name) for name, said in _entries(page, section).items() if not said]
    assert unexplained == []


def test_a_required_option_says_it_is_required(run_cli):
    assert "PR number (required)" in _help(run_cli, "thread", "show")


def test_an_option_with_a_default_says_what_the_default_is(run_cli):
    assert "(default: manual)" in _help(run_cli, "thread", "place")
    assert "(default: 20)" in _help(run_cli, "logs")


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


def test_help_prints_the_same_page_as_the_full_help(run_cli):
    ran = run_cli("help")
    assert ran.code == 0
    assert ran.out == run_cli("--help").out


def test_the_full_help_ends_with_the_debugging_commands_after_the_groups(run_cli):
    ran = run_cli("--help")
    assert ran.code == 0
    sections = _sections(ran.out)
    assert list(sections) == ["everyday", "service", "maintenance", "learning", "agents",
                              "debugging"]
    assert sections["agents"] == ["thread"]
    assert sections["debugging"] == ["queue", "undismiss"]
    assert ran.out.rstrip().endswith("Clear a PR's dismissal so it comes back to the wall.")


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
