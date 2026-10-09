from datetime import datetime
from pathlib import Path

import pytest

from github_orchestrator.domain import Clone, HubState, Repo
from github_orchestrator.settings import ConfigFile
from github_orchestrator.settings.fake import OrchestratorConfig, Tracker
from tests.settings.support import (
    ConfigProblem,
    describe_config,
    example_config,
    load_config,
    read_from,
    settings_read_from,
)

SET_BY_SETUP = ("gh_account", "repos")

CONFIGURED = {"gh_account": "octocat"}

HELLO = '\n[[repos]]\nrepo = "octocat/hello"\nlocal_path = "/tmp/hello"\n'


def write_config(tmp_path, body=""):
    already_set = {line.split("=", 1)[0].strip() for line in body.splitlines()}
    prefix = "".join(
        f'{key} = "{value}"\n'
        for key, value in CONFIGURED.items() if key not in already_set
    )
    repos = "" if "[[repos]]" in body or "watch_repo" in already_set else HELLO
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(prefix + body + repos)
    return toml_file


def repos_read_from(toml_file):
    return settings_read_from(toml_file).repos


def test_each_watched_repo_is_read_with_its_clone_and_its_own_new_worktree_command(tmp_path):
    toml_file = write_config(tmp_path, (
        'new_worktree_command = "make setup"\n'
        '\n[[repos]]\nrepo = "acme/widgets"\nlocal_path = "/src/widgets"\n'
        'new_worktree_command = "cp $GITHUB_ORCHESTRATOR_SOURCE_REPO/.env ."\n'
        '\n[[repos]]\nrepo = "acme/gadgets"\nlocal_path = "/src/gadgets"\n'))

    assert repos_read_from(toml_file) == {
        Repo("acme", "widgets"): Clone(Path("/src/widgets"),
                                       "cp $GITHUB_ORCHESTRATOR_SOURCE_REPO/.env ."),
        Repo("acme", "gadgets"): Clone(Path("/src/gadgets"), "make setup"),
    }


def test_a_clone_under_the_home_folder_is_read_with_the_home_folder_expanded(tmp_path):
    toml_file = write_config(
        tmp_path, '[[repos]]\nrepo = "acme/widgets"\nlocal_path = "~/src/widgets"\n')

    assert repos_read_from(toml_file)[Repo("acme", "widgets")].path == (
        Path.home() / "src" / "widgets")


def test_the_old_watch_repo_and_local_path_read_as_one_watched_repo(tmp_path):
    toml_file = write_config(tmp_path, (
        'watch_repo = "acme/widgets"\nlocal_path = "/src/widgets"\n'
        'new_worktree_command = "make setup"\n'))

    assert repos_read_from(toml_file) == {
        Repo("acme", "widgets"): Clone(Path("/src/widgets"), "make setup")}


def test_a_config_with_both_the_old_keys_and_repos_is_refused(tmp_path):
    toml_file = write_config(tmp_path, (
        'watch_repo = "acme/widgets"\nlocal_path = "/src/widgets"\n'
        '[[repos]]\nrepo = "acme/gadgets"\nlocal_path = "/src/gadgets"\n'))

    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)

    assert "watch_repo" in str(e.value)
    assert "[[repos]]" in str(e.value)


@pytest.mark.parametrize("entry, named", [
    ('repo = "github-orchestrator"\nlocal_path = "/src/x"\n', "owner/name"),
    ('local_path = "/src/x"\n', "repo"),
    ('repo = "acme/widgets"\n', "local_path"),
    ('repo = "acme/widgets"\nlocal_path = 3\n', "local_path"),
    ('repo = "acme/widgets"\nlocal_path = "/src/x"\nlocal_pth = "/src/y"\n', "local_pth"),
])
def test_a_repos_entry_that_names_no_repo_and_clone_is_refused(tmp_path, entry, named):
    toml_file = write_config(tmp_path, f"[[repos]]\n{entry}")

    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)

    assert str(toml_file) in str(e.value)
    assert named in str(e.value)


def test_a_repos_that_is_not_a_list_of_tables_is_refused(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('gh_account = "octocat"\nrepos = "acme/widgets"\n')

    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)

    assert "[[repos]]" in str(e.value)


def test_the_same_repo_watched_twice_is_refused(tmp_path):
    toml_file = write_config(tmp_path, (
        '[[repos]]\nrepo = "acme/widgets"\nlocal_path = "/src/a"\n'
        '[[repos]]\nrepo = "acme/widgets"\nlocal_path = "/src/b"\n'))

    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)

    assert "acme/widgets" in str(e.value)
    assert "twice" in str(e.value)


def test_load_config_keeps_the_defaults_the_file_leaves_alone(tmp_path):
    config = load_config(write_config(tmp_path))
    assert isinstance(config, OrchestratorConfig)
    assert config.dashboard_refresh_interval == 1
    assert config.watcher_poll_interval == 60
    assert config.agent_timeout == 3600


def test_load_config_reads_toml(tmp_path):
    toml_file = write_config(
        tmp_path, 'dashboard_refresh_interval = 10\nclaude_timeout = 1800\n'
    )
    config = load_config(toml_file)
    assert config.dashboard_refresh_interval == 10
    assert config.agent_timeout == 1800
    assert config.watcher_poll_interval == 60


def test_load_config_reads_claude_enabled(tmp_path):
    toml_file = write_config(tmp_path, 'agents_enabled = false\n')
    config = load_config(toml_file)
    assert config.agents_enabled is False


def test_load_config_rejects_an_unknown_key(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('claud_enabled = false\n')
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    message = str(e.value)
    assert str(toml_file) in message
    assert "claud_enabled" in message
    assert "agents_enabled" in message


def test_an_unknown_key_with_no_near_match_lists_the_known_ones(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('zzzzzzzz = 3600\n')
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    assert "known keys" in str(e.value)
    assert "watcher_poll_interval" in str(e.value)


def test_load_config_rejects_a_quoted_bool(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('agents_enabled = "false"\n')
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    message = str(e.value)
    assert str(toml_file) in message
    assert "agents_enabled" in message
    assert "bool" in message
    assert "str" in message


def test_a_bool_is_not_accepted_for_an_int_field(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('watcher_poll_interval = true\n')
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    assert "watcher_poll_interval" in str(e.value)


@pytest.mark.parametrize("value", ["github-orchestrator"])
def test_an_old_watch_repo_that_is_not_owner_slash_name_is_refused(tmp_path, value):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(f'watch_repo = "{value}"\n')
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    assert str(toml_file) in str(e.value)
    assert "owner/name" in str(e.value)


def test_the_type_check_does_not_depend_on_how_the_annotation_is_spelled(
    tmp_path, monkeypatch
):
    for field in OrchestratorConfig.__dataclass_fields__.values():
        monkeypatch.setattr(field, "type", field.type.__name__)

    toml_file = write_config(tmp_path, "watcher_poll_interval = 30\n")
    assert load_config(toml_file).watcher_poll_interval == 30

    toml_file = write_config(tmp_path, 'watcher_poll_interval = "30"\n')
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    assert "int" in str(e.value)


def _toml_literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    return repr(value)


def test_load_config_accepts_every_documented_key(tmp_path):
    import tomllib

    values = {key: CONFIGURED.get(key, getattr(OrchestratorConfig(), key))
              for key in sorted(OrchestratorConfig.__dataclass_fields__) if key != "repos"}
    toml_file = write_config(tmp_path, "".join(
        f"{key} = {_toml_literal(value)}\n" for key, value in values.items()))

    assert tomllib.loads(toml_file.read_text()) == {
        **values, "repos": [{"repo": "octocat/hello", "local_path": "/tmp/hello"}]}
    config = load_config(toml_file)
    assert {key: getattr(config, key) for key in values} == values


def test_python_style_false_names_the_file_and_the_line(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('agents_enabled = False\n')
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    assert str(toml_file) in str(e.value)
    assert "line 1" in str(e.value)


def test_a_config_that_is_not_utf8_names_the_file(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_bytes(b'gh_account = "caf\xe9"\n')
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    assert str(toml_file) in str(e.value)


def test_a_config_that_cannot_be_opened_names_the_file(tmp_path):
    directory = tmp_path / "config.toml"
    directory.mkdir()
    with pytest.raises(ConfigProblem) as e:
        load_config(directory)
    assert str(directory) in str(e.value)


def test_describe_config_reports_value_and_source(tmp_path):
    toml_file = write_config(tmp_path, 'agents_enabled = false\n')
    rows = describe_config(toml_file)
    by_key = {row.key: (row.value, row.source) for row in rows}
    assert by_key["agents_enabled"] == (False, "config.toml")
    assert by_key["watcher_poll_interval"] == (60, "default")
    assert len(rows) == len(OrchestratorConfig.__dataclass_fields__)
    assert set(by_key) == set(OrchestratorConfig.__dataclass_fields__)


def test_load_config_reads_the_claude_command(tmp_path):
    toml_file = write_config(tmp_path, 'agent_command = "CLAUDE_CONFIG_DIR=~/.claude-work claude"\n')
    assert load_config(toml_file).agent_command == "CLAUDE_CONFIG_DIR=~/.claude-work claude"


def test_a_config_that_names_no_tracker_files_no_tickets(tmp_path):
    config = load_config(write_config(tmp_path))

    assert (config.tracker, config.tracker_project) == (Tracker.NONE, "")


def test_a_github_tracker_needs_no_project(tmp_path):
    config = load_config(write_config(tmp_path, 'tracker = "github"\n'))

    assert (config.tracker, config.tracker_project) == (Tracker.GITHUB, "")


def test_a_jira_tracker_reads_its_default_project(tmp_path):
    config = load_config(write_config(
        tmp_path, 'tracker = "jira"\ntracker_project = "PROJ"\n'))

    assert (config.tracker, config.tracker_project) == (Tracker.JIRA, "PROJ")


def test_a_tracker_that_is_neither_github_nor_jira_is_refused(tmp_path):
    toml_file = write_config(tmp_path, 'tracker = "linear"\n')
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    message = str(e.value)
    assert "tracker" in message
    assert '"github"' in message
    assert '"jira"' in message


def test_a_jira_tracker_with_no_project_is_refused(tmp_path):
    toml_file = write_config(tmp_path, 'tracker = "jira"\n')
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    assert str(toml_file) in str(e.value)
    assert "tracker_project" in str(e.value)


@pytest.mark.parametrize("project", ["proj", "PROJ-1", "P", "1ROJ", "PR OJ"])
def test_a_tracker_project_that_is_no_jira_project_key_is_refused(tmp_path, project):
    toml_file = write_config(tmp_path, f'tracker = "jira"\ntracker_project = "{project}"\n')
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    assert "tracker_project" in str(e.value)
    assert project in str(e.value)


@pytest.mark.parametrize("tracker", ["", 'tracker = "github"\n'])
def test_a_tracker_project_without_a_jira_tracker_is_refused(tmp_path, tracker):
    toml_file = write_config(tmp_path, f'{tracker}tracker_project = "PROJ"\n')
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    assert "tracker_project" in str(e.value)
    assert '"jira"' in str(e.value)


def test_the_hub_listens_on_a_port_below_the_boards_by_default(tmp_path):
    assert load_config(write_config(tmp_path)).hub_port == 8720


@pytest.mark.parametrize("port", [8730, 8829, 0, 65536])
def test_a_hub_port_a_board_could_take_or_no_port_at_all_is_refused(tmp_path, port):
    toml_file = write_config(tmp_path, f"hub_port = {port}\n")
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    assert "hub_port" in str(e.value)
    assert str(port) in str(e.value)


def test_an_empty_config_file_names_every_key_it_needs(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text("# nothing set\n")
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    message = str(e.value)
    assert str(toml_file) in message
    for key in SET_BY_SETUP:
        assert key in message


def test_every_setting_is_written_down_in_the_example_file():
    example = example_config()
    documented = {
        line.removeprefix("#").split("=", 1)[0].strip()
        for line in example.splitlines()
        if "=" in line and not line.removeprefix("#").lstrip().startswith("#")
    } | {line.strip("[] ") for line in example.splitlines() if line.startswith("[[")}

    missing = sorted(set(OrchestratorConfig.__dataclass_fields__) - documented)

    assert not missing, (
        f"{', '.join(missing)} can be set in config.toml but the example file "
        f"never names it, so nobody reading it knows the key exists"
    )


def test_copying_the_example_file_verbatim_is_refused(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(example_config())
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    for key in SET_BY_SETUP:
        assert key in str(e.value)


def test_describe_config_marks_the_keys_nobody_set_unset(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text("agents_enabled = false\n")

    by_key = {row.key: row for row in describe_config(toml_file)}

    assert [key for key, row in by_key.items() if row.unset] == list(SET_BY_SETUP)
    assert by_key["gh_account"].source == "unset"
    assert by_key["agents_enabled"].source == "config.toml"
    assert by_key["watcher_poll_interval"].source == "default"


def test_describe_config_with_no_file_marks_them_unset_too(tmp_path):
    rows = describe_config(tmp_path / "nonexistent.toml")

    by_key = {row.key: row for row in rows}
    assert [key for key, row in by_key.items() if row.unset] == list(SET_BY_SETUP)
    assert {by_key[key].source for key in SET_BY_SETUP} == {"unset"}
    assert by_key["watcher_poll_interval"].source == "default"


def test_describe_config_marks_a_placeholder_left_in_the_file_unset(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(
        'gh_account = "your-github-username"\n'
        'watch_repo = "octocat/hello"\n'
        'local_path = "/tmp/hello"\n'
    )

    by_key = {row.key: row for row in describe_config(toml_file)}

    assert by_key["gh_account"].unset and by_key["gh_account"].source == "unset"
    assert not by_key["repos"].unset and by_key["repos"].source == "config.toml"


def test_describe_config_still_refuses_a_file_it_cannot_read(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text("claud_enabled = false\n")

    with pytest.raises(ConfigProblem) as e:
        describe_config(toml_file)

    assert "claud_enabled" in str(e.value)


def test_the_config_is_read_once_so_a_later_fix_is_not_seen_until_the_next_start(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text("claud_enabled = false\n")
    config_file = read_from(toml_file).get(ConfigFile)
    write_config(tmp_path)

    assert "claud_enabled" in config_file.check()


def test_a_config_that_reads_cleanly_passes_the_check(tmp_path):
    assert read_from(write_config(tmp_path)).get(ConfigFile).check() is None


def test_writing_sets_the_keys_and_the_repos_and_keeps_every_other_value(tmp_path):
    toml_file = write_config(
        tmp_path, 'agents_enabled = false\nhub_port = 8900\nnew_worktree_command = "make"\n')

    read_from(toml_file).get(ConfigFile).write(
        {"gh_account": "someone"}, repos={Repo("acme", "widgets"): Clone(Path("/src/widgets"), "")})

    config = load_config(toml_file)
    assert (config.gh_account, config.agents_enabled, config.hub_port) == (
        "someone", False, 8900)
    assert repos_read_from(toml_file) == {
        Repo("acme", "widgets"): Clone(Path("/src/widgets"), "make")}


def test_writing_over_the_old_watch_repo_and_local_path_leaves_only_repos(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(
        'gh_account = "octocat"\nwatch_repo = "octocat/hello"\nlocal_path = "/tmp/hello"\n')

    read_from(toml_file).get(ConfigFile).write(
        {}, repos={Repo("acme", "widgets"): Clone(Path("/src/widgets"), "")})

    assert "watch_repo" not in toml_file.read_text()
    assert set(repos_read_from(toml_file)) == {Repo("acme", "widgets")}


def test_writing_where_there_is_no_file_writes_one(tmp_path):
    toml_file = tmp_path / "nested" / "config.toml"

    read_from(toml_file).get(ConfigFile).write(
        CONFIGURED, repos={Repo("octocat", "hello"): Clone(Path("/tmp/hello"), "")})

    assert load_config(toml_file).gh_account == "octocat"
    assert set(repos_read_from(toml_file)) == {Repo("octocat", "hello")}


def test_a_written_value_with_quotes_and_backslashes_reads_back_as_written(tmp_path):
    toml_file = write_config(tmp_path)
    weird = '/tmp/a "quoted" \\ path'

    read_from(toml_file).get(ConfigFile).write(
        {"agent_command": weird}, repos={Repo("octocat", "hello"): Clone(Path(weird), "")})

    assert load_config(toml_file).agent_command == weird
    assert repos_read_from(toml_file)[Repo("octocat", "hello")].path == Path(weird)


def test_writing_keeps_a_repo_s_own_new_worktree_command_and_leaves_an_empty_one_to_the_default(
        tmp_path):
    toml_file = write_config(tmp_path, 'new_worktree_command = "make"\n')

    read_from(toml_file).get(ConfigFile).write({}, repos={
        Repo("acme", "widgets"): Clone(Path("/src/widgets"), "cp .env ."),
        Repo("acme", "gadgets"): Clone(Path("/src/gadgets"), "")})

    assert repos_read_from(toml_file) == {
        Repo("acme", "widgets"): Clone(Path("/src/widgets"), "cp .env ."),
        Repo("acme", "gadgets"): Clone(Path("/src/gadgets"), "make")}


def test_writing_true_false_and_numbers_reads_them_back_as_written(tmp_path):
    toml_file = write_config(tmp_path)

    read_from(toml_file).get(ConfigFile).write(
        {"agents_enabled": False, "max_thread_runs": 2, "agent_model": "sonnet"},
        repos={Repo("octocat", "hello"): Clone(Path("/tmp/hello"), "")})

    config = load_config(toml_file)
    assert (config.agents_enabled, config.max_thread_runs, config.agent_model) == (
        False, 2, "sonnet")


def test_a_write_that_would_not_read_back_is_refused_and_writes_nothing(tmp_path):
    toml_file = write_config(tmp_path)
    before = toml_file.read_text()
    config_file = read_from(toml_file).get(ConfigFile)

    refused = config_file.check_write(
        {"hub_port": 8731}, repos={Repo("octocat", "hello"): Clone(Path("/tmp/hello"), "")})

    assert refused is not None and "hub_port" in refused and "8730-8829" in refused
    assert toml_file.read_text() == before


def test_a_write_that_reads_back_passes_the_check(tmp_path):
    config_file = read_from(tmp_path / "config.toml").get(ConfigFile)

    assert config_file.check_write(
        {"gh_account": "octocat", "hub_port": 8900},
        repos={Repo("octocat", "hello"): Clone(Path("/tmp/hello"), "")}) is None
    assert not (tmp_path / "config.toml").exists()


def test_the_watched_repos_are_listed_as_the_file_writes_them(tmp_path):
    toml_file = write_config(tmp_path, (
        '[[repos]]\nrepo = "acme/widgets"\nlocal_path = "~/src/widgets"\n'
        'new_worktree_command = "cp .env ."\n'
        '\n[[repos]]\nrepo = "acme/gadgets"\nlocal_path = "/src/gadgets"\n'))

    listed = read_from(toml_file).get(ConfigFile).repos()

    assert [(str(entry.repo), entry.local_path, entry.new_worktree_command)
            for entry in listed] == [("acme/widgets", "~/src/widgets", "cp .env ."),
                                     ("acme/gadgets", "/src/gadgets", None)]


def test_a_config_that_will_not_parse_lists_no_repos(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text("gh_account = \n")

    assert read_from(toml_file).get(ConfigFile).repos() == ()


def test_a_broken_config_moved_aside_leaves_its_hub_port_behind_so_the_hub_comes_back_there(
        tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('hub_port = 8721\ngh_acount = "octocat"\n')

    read_from(toml_file).get(ConfigFile).move_aside(datetime(2026, 10, 9, 8, 30, 5))

    assert toml_file.read_text() == "hub_port = 8721\n"
    assert read_from(toml_file).get(ConfigFile).state() is HubState.SETUP


def test_a_broken_config_is_moved_aside_under_the_time_it_was_moved(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text("gh_account = \n")

    moved = read_from(toml_file).get(ConfigFile).move_aside(datetime(2026, 10, 9, 8, 30, 5))

    assert moved == str(tmp_path / "config.toml.broken-20261009-083005")
    assert Path(moved).read_text() == "gh_account = \n"
    assert not toml_file.exists()


def test_a_missing_config_says_to_run_setup_in_the_cli_s_own_words(tmp_path):
    missing = tmp_path / "nonexistent.toml"
    with pytest.raises(ConfigProblem) as e:
        load_config(missing)
    assert str(e.value) == (
        f"{missing}: the config file does not exist — run "
        "`github-orchestrator setup`, which opens the board's setup "
        "page to write it")


def test_an_unset_config_says_to_run_setup_in_the_cli_s_own_words(tmp_path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text('[[repos]]\nrepo = "octocat/hello"\nlocal_path = "/tmp/hello"\n')
    with pytest.raises(ConfigProblem) as e:
        load_config(toml_file)
    assert str(e.value) == (
        f"{toml_file}: gh_account must be set to your own values — run "
        "`github-orchestrator setup`, which opens the board's setup "
        "page to ask for them")


@pytest.mark.parametrize(("body", "state"), [
    (None, HubState.SETUP),
    ("hub_port = 8890\n", HubState.SETUP),
    ('gh_account = "octocat"\n', HubState.SETUP),
    ('gh_account = "octocat"' + HELLO, HubState.WATCHING),
    ('gh_account = "octocat"\nclaud_enabled = false' + HELLO, HubState.BROKEN),
    ("gh_account = \n", HubState.BROKEN),
])
def test_the_config_chooses_the_hub_s_state(tmp_path, body, state):
    toml_file = tmp_path / "config.toml"
    if body is not None:
        toml_file.write_text(body)

    assert read_from(toml_file).get(ConfigFile).state() is state


def test_the_state_is_read_from_the_file_as_it_is_now(tmp_path):
    toml_file = tmp_path / "config.toml"
    config_file = read_from(toml_file).get(ConfigFile)
    write_config(tmp_path)

    assert config_file.state() is HubState.WATCHING


@pytest.mark.parametrize("body", ["hub_port = 8890\n", "hub_port = 8890\nclaud_enabled = 1\n"])
def test_a_config_that_is_not_watching_still_says_which_port_the_hub_takes(tmp_path, body):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(body)

    assert settings_read_from(toml_file).config.hub_port == 8890


def test_an_instance_runs_claude_unless_it_says_otherwise(tmp_path):
    config = load_config(write_config(tmp_path))

    assert (config.agent, config.agent_command, config.agent_model, config.summary_model) == (
        "claude", "claude", "opus", "haiku")


def test_a_codex_instance_takes_codexs_command_and_models_by_default(tmp_path):
    config = load_config(write_config(tmp_path, 'agent = "codex"\n'))

    assert config.agent == "codex"
    assert config.agent_command.endswith("codex")
    assert (config.agent_model, config.summary_model) == ("gpt-6-luna", "gpt-6-luna")


def test_a_codex_instance_keeps_the_command_and_models_it_names(tmp_path):
    config = load_config(write_config(
        tmp_path, 'agent = "codex"\nagent_command = "/opt/codex"\nagent_model = "gpt-x"\n'
                  'summary_model = "gpt-y"\n'))

    assert (config.agent_command, config.agent_model, config.summary_model) == (
        "/opt/codex", "gpt-x", "gpt-y")


def test_an_agent_this_release_cannot_run_is_refused_with_the_ones_it_can(tmp_path):
    toml_file = write_config(tmp_path, 'agent = "gemini"\n')

    with pytest.raises(ConfigProblem) as refused:
        load_config(toml_file)

    assert str(refused.value).endswith('agent must be "claude" or "codex", got \'gemini\'')


def test_the_agents_defaults_show_as_defaults_not_as_set(tmp_path):
    toml_file = write_config(tmp_path, 'agent = "codex"\n')

    by_key = {row.key: row for row in read_from(toml_file).get(ConfigFile).describe().rows}

    assert (by_key["agent"].source, by_key["agent_model"].source) == ("config.toml", "default")
    assert by_key["agent_model"].value == "gpt-6-luna"
