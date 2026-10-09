from pathlib import Path

from github_orchestrator.domain import Clone, Repo
from github_orchestrator.settings import ConfigFile
from github_orchestrator.settings.fake import OrchestratorConfig, Settings
from github_orchestrator.wiring import make_container, other_instances

CHECKOUT_CONFIG = "github_orchestrator.settings._load.CHECKOUT_CONFIG"

CONFIGURED = (
    'gh_account = "hubot"\n'
    '[[repos]]\n'
    'repo = "hubot/robots"\n'
    'local_path = "~/repositories/robots"\n'
)


def _settings(env, home):
    return make_container(env, home).get(Settings)


def _configured(tmp_path, text=CONFIGURED):
    config = tmp_path / "elsewhere.toml"
    config.write_text(text)
    return {"GITHUB_ORCHESTRATOR_CONFIG": str(config)}


def test_the_data_dir_prefers_the_explicit_override(tmp_path):
    env = {"GITHUB_ORCHESTRATOR_DATA_DIR": "/tmp/od", "XDG_DATA_HOME": "/tmp/xdg"}
    assert _settings(env, tmp_path).data_dir == Path("/tmp/od")


def test_the_data_dir_override_expands_a_tilde(tmp_path):
    env = {"GITHUB_ORCHESTRATOR_DATA_DIR": "~/od"}
    assert _settings(env, tmp_path).data_dir == Path.home() / "od"


def test_the_data_dir_follows_xdg_data_home(tmp_path):
    env = {"XDG_DATA_HOME": "/tmp/xdg"}
    assert _settings(env, tmp_path).data_dir == Path("/tmp/xdg/github-orchestrator")


def test_the_data_dir_keeps_a_legacy_install_when_xdg_is_unset(tmp_path):
    legacy = tmp_path / ".config" / "local" / "share" / "github-orchestrator"
    legacy.mkdir(parents=True)
    assert _settings({}, tmp_path).data_dir == legacy


def test_the_data_dir_defaults_to_the_xdg_default(tmp_path):
    assert _settings({}, tmp_path).data_dir == (
        tmp_path / ".local" / "share" / "github-orchestrator"
    )


def test_the_config_path_prefers_the_env_override(tmp_path):
    env = {"GITHUB_ORCHESTRATOR_CONFIG": "/tmp/elsewhere.toml"}
    assert _settings(env, tmp_path).config_path == Path("/tmp/elsewhere.toml")


def _left_in_a_checkout(tmp_path, monkeypatch, *, exists):
    checkout_config = tmp_path / "checkout" / "config.toml"
    if exists:
        checkout_config.parent.mkdir()
        checkout_config.write_text(CONFIGURED)
    monkeypatch.setattr(CHECKOUT_CONFIG, checkout_config)
    return checkout_config


def test_the_config_path_defaults_to_config_toml_in_the_config_folder(tmp_path, monkeypatch):
    _left_in_a_checkout(tmp_path, monkeypatch, exists=False)
    assert _settings({}, tmp_path).config_path == (
        tmp_path / ".config" / "github-orchestrator" / "config.toml")


def test_a_config_left_in_the_checkout_is_still_read_while_the_config_folder_has_none(
        tmp_path, monkeypatch):
    checkout_config = _left_in_a_checkout(tmp_path, monkeypatch, exists=True)
    settings = _settings({}, tmp_path)
    assert settings.config_path == checkout_config
    assert settings.config.gh_account == "hubot"


def test_the_config_folders_config_wins_over_one_left_in_the_checkout(tmp_path, monkeypatch):
    _left_in_a_checkout(tmp_path, monkeypatch, exists=True)
    default = _another_instance(tmp_path, "config")
    assert _settings({}, tmp_path).config_path == default


def test_the_config_comes_from_the_file_the_config_path_names(tmp_path):
    settings = _settings(_configured(tmp_path), tmp_path)
    assert settings.config.gh_account == "hubot"
    assert settings.repos == {
        Repo("hubot", "robots"): Clone(Path.home() / "repositories" / "robots", "")}


def test_a_broken_config_falls_back_to_the_defaults_and_is_reported(tmp_path):
    env = _configured(tmp_path, 'claud_enabled = false\n')
    container = make_container(env, tmp_path)
    assert container.get(Settings).config == OrchestratorConfig()
    assert "claud_enabled" in container.get(ConfigFile).check()


def test_the_settings_are_read_once_when_the_container_is_built(tmp_path):
    env = _configured(tmp_path)
    container = make_container(env, tmp_path)
    Path(env["GITHUB_ORCHESTRATOR_CONFIG"]).write_text(
        CONFIGURED.replace("hubot", "octocat")
    )

    first = container.get(Settings)

    assert first.config.gh_account == "hubot"
    assert container.get(Settings) is first


def test_every_data_file_keeps_its_place_under_the_data_dir(tmp_path):
    settings = _settings({"GITHUB_ORCHESTRATOR_DATA_DIR": str(tmp_path)}, tmp_path)
    assert {
        "state": settings.state_dir,
        "queues": settings.queues_dir,
        "transcripts": settings.transcripts_dir,
        "logs": settings.logs_dir,
        "on_hold": settings.on_hold_dir,
        "dismissed": settings.dismissed_dir,
        "mismatched": settings.mismatched_dir,
        "pr_managers": settings.pr_managers_dir,
        "worktree_conflicts": settings.worktree_conflicts_dir,
        "threads": settings.threads_dir,
        "thread-worktrees": settings.thread_worktrees_dir,
        "board": settings.board_dir,
        "runs.jsonl": settings.runs_log,
        "watcher.heartbeat": settings.watcher_heartbeat,
        "watcher.failures.json": settings.watcher_failures,
        "watcher.lock": settings.watcher_lock,
    } == {name: tmp_path / name for name in (
        "state", "queues", "transcripts", "logs", "on_hold", "dismissed",
        "mismatched", "pr_managers", "worktree_conflicts", "threads",
        "thread-worktrees", "board", "runs.jsonl",
        "watcher.heartbeat", "watcher.failures.json", "watcher.lock",
    )}


def test_a_child_given_the_child_environment_finds_the_same_config_and_data(tmp_path):
    env = {**_configured(tmp_path), "GITHUB_ORCHESTRATOR_DATA_DIR": str(tmp_path / "data")}
    parent = _settings(env, tmp_path)

    child = _settings(parent.child_environment(), tmp_path / "elsewhere")

    assert child.data_dir == parent.data_dir
    assert child.config_path == parent.config_path
    assert child.config == parent.config


def test_the_child_environment_holds_only_what_the_child_needs_to_find_them(tmp_path):
    env = {**_configured(tmp_path), "XDG_DATA_HOME": str(tmp_path / "xdg"), "HOME": "/x"}
    assert set(_settings(env, tmp_path).child_environment()) == {
        "GITHUB_ORCHESTRATOR_DATA_DIR", "GITHUB_ORCHESTRATOR_CONFIG"}


def _another_instance(home, name):
    folder = home / ".config" / "github-orchestrator"
    folder.mkdir(parents=True, exist_ok=True)
    config = folder / f"{name}.toml"
    config.write_text(CONFIGURED)
    return config


def test_each_toml_in_the_config_folder_is_another_instance_with_data_beside_the_default(tmp_path):
    api = _another_instance(tmp_path, "api")
    second = _another_instance(tmp_path, "second")
    (second.parent / "notes.txt").write_text("")
    shared = tmp_path / ".local" / "share"

    assert other_instances({}, tmp_path) == {
        "api": {"GITHUB_ORCHESTRATOR_DATA_DIR": str(shared / "github-orchestrator-api"),
                "GITHUB_ORCHESTRATOR_CONFIG": str(api)},
        "second": {"GITHUB_ORCHESTRATOR_DATA_DIR": str(shared / "github-orchestrator-second"),
                   "GITHUB_ORCHESTRATOR_CONFIG": str(second)},
    }


def test_another_instance_keeps_its_data_beside_the_default_whatever_this_one_was_pointed_at(tmp_path):
    _another_instance(tmp_path, "second")
    env = {"GITHUB_ORCHESTRATOR_DATA_DIR": "/tmp/od", "XDG_DATA_HOME": "/tmp/xdg"}

    [data_dir] = [instance["GITHUB_ORCHESTRATOR_DATA_DIR"]
                  for instance in other_instances(env, tmp_path).values()]

    assert data_dir == "/tmp/xdg/github-orchestrator-second"


def test_with_no_config_folder_there_is_no_other_instance(tmp_path):
    assert other_instances({}, tmp_path) == {}


def test_the_default_config_in_the_config_folder_is_not_another_instance(tmp_path):
    _another_instance(tmp_path, "config")
    api = _another_instance(tmp_path, "api")

    assert {name: instance["GITHUB_ORCHESTRATOR_CONFIG"]
            for name, instance in other_instances({}, tmp_path).items()} == {"api": str(api)}


def test_an_instance_named_in_the_environment_reads_its_own_config_and_data(tmp_path):
    work = _another_instance(tmp_path, "work")

    settings = _settings({"GITHUB_ORCHESTRATOR_INSTANCE": "work"}, tmp_path)

    assert settings.config_path == work
    assert settings.data_dir == tmp_path / ".local" / "share" / "github-orchestrator-work"
    assert settings.config.gh_account == "hubot"


def test_an_explicit_config_and_data_dir_win_over_the_instance_name(tmp_path):
    env = {**_configured(tmp_path), "GITHUB_ORCHESTRATOR_DATA_DIR": "/tmp/od",
           "GITHUB_ORCHESTRATOR_INSTANCE": "work"}

    settings = _settings(env, tmp_path)

    assert settings.config_path == Path(env["GITHUB_ORCHESTRATOR_CONFIG"])
    assert settings.data_dir == Path("/tmp/od")


def test_a_named_instance_s_others_are_the_default_one_and_every_other_name(tmp_path, monkeypatch):
    _left_in_a_checkout(tmp_path, monkeypatch, exists=False)
    _another_instance(tmp_path, "work")
    api = _another_instance(tmp_path, "api")
    shared = tmp_path / ".local" / "share"

    others = other_instances({"GITHUB_ORCHESTRATOR_INSTANCE": "work"}, tmp_path)

    assert others == {
        None: {"GITHUB_ORCHESTRATOR_DATA_DIR": str(shared / "github-orchestrator"),
               "GITHUB_ORCHESTRATOR_CONFIG": str(api.with_name("config.toml"))},
        "api": {"GITHUB_ORCHESTRATOR_DATA_DIR": str(shared / "github-orchestrator-api"),
                "GITHUB_ORCHESTRATOR_CONFIG": str(api)},
    }


def test_an_instance_pointed_at_by_its_config_path_is_not_its_own_other(tmp_path, monkeypatch):
    _left_in_a_checkout(tmp_path, monkeypatch, exists=False)
    work = _another_instance(tmp_path, "work")

    others = other_instances({"GITHUB_ORCHESTRATOR_CONFIG": str(work)}, tmp_path)

    assert list(others) == [None]
