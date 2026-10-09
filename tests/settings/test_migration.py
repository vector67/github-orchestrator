from pathlib import Path

import pytest

from github_orchestrator.domain import Clone, HubState, Repo
from github_orchestrator.settings import ConfigFile
from tests.settings.support import (
    ConfigProblem,
    load_config,
    read_from,
    settings_read_from,
)

OLD = '''# GitHub Orchestrator Configuration
# dashboard_refresh_interval = 30

claude_enabled = true
claude_command = "CLAUDE_CONFIG_DIR=~/.claude-work claude"

local_path = "/src/widgets"
watch_repo = "acme/widgets"

gh_account = "octocat"
board_font_dir = "~/design/fonts"

pr_windows = "browser"
hub_port = 8722
idle_threshold = 45

new_worktree_command = "cp $GITHUB_ORCHESTRATOR_SOURCE_REPO/.env ."

first_names_only = true
'''

CURRENT = 'gh_account = "octocat"\n\n[[repos]]\nrepo = "acme/widgets"\nlocal_path = "/src/widgets"\n'


def _config(tmp_path: Path, body: str = OLD) -> Path:
    config = tmp_path / "config.toml"
    config.write_text(body)
    return config


def _data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


def _migrated(config: Path) -> list[str]:
    config_file: ConfigFile = read_from(config, _data_dir(config.parent)).get(ConfigFile)
    return config_file.migrate()


@pytest.mark.parametrize("line", ['pr_windows = "browser"\n', 'pr_windows = "tmux"\n',
                                  "idle_threshold = 30\n"])
def test_a_config_from_tmux_mode_is_refused_with_the_command_that_migrates_it(tmp_path, line):
    config = _config(tmp_path, line + CURRENT)

    with pytest.raises(ConfigProblem) as refused:
        load_config(config)

    said = str(refused.value)
    assert said.startswith(f"{config}: {line.split(' ')[0]} ")
    assert "`github-orchestrator restart`" in said


def test_a_config_from_tmux_mode_leaves_the_hub_broken_until_it_is_migrated(tmp_path):
    config = _config(tmp_path, 'pr_windows = "browser"\n' + CURRENT)

    assert read_from(config).get(ConfigFile).state() is HubState.BROKEN


def test_migrating_keeps_every_setting_this_release_still_reads(tmp_path):
    config = _config(tmp_path)

    _migrated(config)

    loaded = load_config(config)
    assert (loaded.gh_account, loaded.agents_enabled, loaded.agent_command, loaded.hub_port,
            loaded.board_font_dir, loaded.first_names_only) == (
        "octocat", True, "CLAUDE_CONFIG_DIR=~/.claude-work claude", 8722, "~/design/fonts", True)
    assert settings_read_from(config).repos == {
        Repo("acme", "widgets"): Clone(Path("/src/widgets"),
                                       "cp $GITHUB_ORCHESTRATOR_SOURCE_REPO/.env .")}


def test_migrating_writes_one_repos_entry_carrying_the_new_worktree_command(tmp_path):
    config = _config(tmp_path)

    _migrated(config)

    assert config.read_text() == (
        'agents_enabled = true\n'
        'agent_command = "CLAUDE_CONFIG_DIR=~/.claude-work claude"\n'
        'gh_account = "octocat"\n'
        'board_font_dir = "~/design/fonts"\n'
        'hub_port = 8722\n'
        'first_names_only = true\n'
        '\n'
        '[[repos]]\n'
        'repo = "acme/widgets"\n'
        'local_path = "/src/widgets"\n'
        'new_worktree_command = "cp $GITHUB_ORCHESTRATOR_SOURCE_REPO/.env ."\n')


def test_migrating_keeps_the_old_file_beside_it_and_says_where(tmp_path):
    config = _config(tmp_path)

    said = _migrated(config)

    assert (tmp_path / "config.toml.bak").read_text() == OLD
    assert said == [f"Rewrote {config} for this release; the old one is "
                    f"{tmp_path / 'config.toml.bak'}"]


def test_a_second_migration_changes_nothing(tmp_path):
    config = _config(tmp_path)
    _migrated(config)
    first = config.read_text()

    assert _migrated(config) == []

    assert config.read_text() == first
    assert sorted(path.name for path in tmp_path.iterdir()) == ["config.toml", "config.toml.bak"]


def test_a_backup_an_earlier_migration_left_is_never_written_over(tmp_path):
    config = _config(tmp_path)
    (tmp_path / "config.toml.bak").write_text("kept\n")
    (tmp_path / "config.toml.bak.1").write_text("kept too\n")

    _migrated(config)

    assert (tmp_path / "config.toml.bak").read_text() == "kept\n"
    assert (tmp_path / "config.toml.bak.1").read_text() == "kept too\n"
    assert (tmp_path / "config.toml.bak.2").read_text() == OLD


def test_a_config_this_release_reads_is_left_alone(tmp_path):
    config = _config(tmp_path, CURRENT)

    assert _migrated(config) == []

    assert config.read_text() == CURRENT
    assert not (tmp_path / "config.toml.bak").exists()


@pytest.mark.parametrize("body", [None, "gh_account = [\n"])
def test_a_config_that_is_missing_or_cannot_be_read_is_left_alone(tmp_path, body):
    config = tmp_path / "config.toml"
    if body is not None:
        config.write_text(body)

    assert _migrated(config) == []

    assert sorted(path.name for path in tmp_path.iterdir()) == (
        [] if body is None else ["config.toml"])


def test_a_migrated_config_passes_the_check_of_the_file_that_migrated_it(tmp_path):
    config = _config(tmp_path)
    config_file = read_from(config, _data_dir(tmp_path)).get(ConfigFile)
    assert config_file.check() is not None

    config_file.migrate()

    assert config_file.check() is None


def test_migrating_removes_what_tmux_mode_left_in_the_data_dir_and_nothing_else(tmp_path):
    config = _config(tmp_path, CURRENT)
    data = _data_dir(tmp_path)
    window_ids = data / "tmux_window_ids" / "acme" / "widgets"
    window_ids.mkdir(parents=True)
    (window_ids / "7.txt").write_text("@12")
    (data / "glow_theme").write_text("dark")
    kept = [data / "pr_managers" / "acme" / "widgets" / "7.json", data / "board" / "x",
            data / "glow_theme.bak", data / "tmux_window_ids.txt"]
    for path in kept:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("kept")

    said = _migrated(config)

    assert not (data / "tmux_window_ids").exists()
    assert not (data / "glow_theme").exists()
    assert all(path.read_text() == "kept" for path in kept)
    assert said == [f"Removed {data / 'tmux_window_ids'}, which only tmux mode read",
                    f"Removed {data / 'glow_theme'}, which only tmux mode read"]


AGENT_KEYS_BEFORE = (
    'gh_account = "octocat"\n'
    'claude_timeout = 1800\n'
    'claude_enabled = false\n'
    'claude_command = "CLAUDE_CONFIG_DIR=~/.claude-work claude"\n'
    'claude_model = "sonnet"\n'
    'summary_model = "haiku"\n'
    '\n[[repos]]\nrepo = "acme/widgets"\nlocal_path = "/src/widgets"\n')


def test_the_old_agent_keys_are_read_under_their_new_names_before_migrating(tmp_path):
    loaded = load_config(_config(tmp_path, AGENT_KEYS_BEFORE))

    assert (loaded.agent_timeout, loaded.agents_enabled, loaded.agent_command,
            loaded.agent_model, loaded.summary_model) == (
        1800, False, "CLAUDE_CONFIG_DIR=~/.claude-work claude", "sonnet", "haiku")


def test_migrating_renames_the_old_agent_keys_where_they_stood(tmp_path):
    config = _config(tmp_path, AGENT_KEYS_BEFORE)

    said = _migrated(config)

    assert config.read_text() == (
        'gh_account = "octocat"\n'
        'agent_timeout = 1800\n'
        'agents_enabled = false\n'
        'agent_command = "CLAUDE_CONFIG_DIR=~/.claude-work claude"\n'
        'agent_model = "sonnet"\n'
        'summary_model = "haiku"\n'
        '\n[[repos]]\nrepo = "acme/widgets"\nlocal_path = "/src/widgets"\n')
    assert (tmp_path / "config.toml.bak").read_text() == AGENT_KEYS_BEFORE
    assert said == [f"Rewrote {config} for this release; the old one is "
                    f"{tmp_path / 'config.toml.bak'}"]


def test_an_agent_key_under_both_its_old_and_new_name_is_refused(tmp_path):
    config = _config(tmp_path, 'claude_model = "sonnet"\nagent_model = "opus"\n' + CURRENT)

    with pytest.raises(ConfigProblem) as refused:
        load_config(config)

    assert str(refused.value) == (
        f"{config}: claude_model is the old name of agent_model; keep agent_model and "
        "remove claude_model")
