import pytest


@pytest.fixture
def logs(settings):
    settings.logs_dir.mkdir()
    (settings.logs_dir / "watcher.log").write_text("watcher line one\nwatcher line two\n")
    (settings.logs_dir / "agent-manager.log").write_text("Spawned claude for o/n#1\n")
    return settings.logs_dir


def test_the_default_target_is_the_watcher_log(logs, run_cli):
    out = run_cli("logs").out
    assert f"==> {logs / 'watcher.log'} <==" in out
    assert "watcher line two" in out
    assert "Spawned claude" not in out


def test_the_agent_manager_log_is_reachable(logs, run_cli):
    out = run_cli("logs", "agent").out
    assert f"==> {logs / 'agent-manager.log'} <==" in out
    assert "Spawned claude for o/n#1" in out


def test_all_prints_both_sections_watcher_first(logs, run_cli):
    out = run_cli("logs", "all").out
    assert out.index("watcher.log") < out.index("agent-manager.log")
    assert "watcher line two" in out
    assert "Spawned claude for o/n#1" in out


def test_lines_caps_how_much_of_the_log_is_shown(logs, run_cli):
    assert run_cli("logs", "-n", "1").out.splitlines()[1:] == ["watcher line two"]


def test_a_missing_log_still_names_the_path_it_looked_for(run_cli, settings):
    out = run_cli("logs", "agent").out
    assert f"==> {settings.logs_dir / 'agent-manager.log'} <==" in out
    assert "(no log yet)" in out


def _shown(run_cli, settings, text, *args):
    settings.logs_dir.mkdir(exist_ok=True)
    (settings.logs_dir / "watcher.log").write_text(text)
    return run_cli("logs", *args).out.splitlines()[1:]


def test_a_log_whose_last_line_has_no_newline_still_shows_it(run_cli, settings):
    assert _shown(run_cli, settings, "one\ntwo") == ["one", "two"]


def test_blank_lines_inside_a_log_are_shown(run_cli, settings):
    assert _shown(run_cli, settings, "one\n\ntwo\n") == ["one", "", "two"]


def test_a_line_longer_than_one_read_is_shown_whole(run_cli, settings):
    long = "x" * (200 * 1024)
    assert _shown(run_cli, settings, f"{long}\nshort\n", "-n", "2") == [long, "short"]


def test_an_empty_log_shows_nothing_under_its_name(run_cli, settings):
    assert _shown(run_cli, settings, "") == []


def test_the_service_log_on_macos_is_launchds_log_file(run_cli, settings):
    settings.logs_dir.mkdir()
    (settings.logs_dir / "launchd.log").write_text("Traceback: config.toml is broken\n")

    out = run_cli("logs", "service").out

    assert out == (f"==> {settings.logs_dir / 'launchd.log'} <==\n"
                   "Traceback: config.toml is broken\n")


def test_the_service_log_on_linux_is_the_units_journal(machine, run_cli):
    machine.platform = "linux"
    machine.system.journal["github-orchestrator.service"] = ["one", "two", "three"]

    out = run_cli("logs", "service", "-n", "2").out

    assert out == "==> journalctl --user -u github-orchestrator.service <==\ntwo\nthree\n"


def test_all_ends_with_the_service_log(logs, run_cli):
    (logs / "launchd.log").write_text("launchd said this\n")

    out = run_cli("logs", "all").out

    assert out.index("agent-manager.log") < out.index("launchd.log")
    assert "launchd said this" in out


def _followed(machine):
    return [call.cmd for call in machine.system.calls if call.cmd[0] in ("tail", "journalctl")]


def test_follow_keeps_printing_the_watcher_log_as_it_grows(machine, logs, run_cli):
    ran = run_cli("logs", "-f")

    assert ran.code == 0
    assert _followed(machine) == [["tail", "-n", "20", "-F", str(logs / "watcher.log")]]


def test_follow_takes_the_number_of_lines_to_start_from(machine, logs, run_cli):
    run_cli("logs", "agent", "-f", "-n", "5")

    assert _followed(machine) == [["tail", "-n", "5", "-F", str(logs / "agent-manager.log")]]


def test_following_the_service_on_macos_follows_launchds_log_file(machine, logs, run_cli):
    run_cli("logs", "service", "--follow")

    assert _followed(machine) == [["tail", "-n", "20", "-F", str(logs / "launchd.log")]]


def test_following_the_service_on_linux_follows_the_units_journal(machine, run_cli):
    machine.platform = "linux"

    run_cli("logs", "service", "-f")

    assert _followed(machine) == [["journalctl", "--user", "-u", "github-orchestrator.service",
                                   "-n", "20", "-f", "--no-pager"]]


def test_ctrl_c_ends_following_quietly(machine, logs, run_cli):
    machine.system.follow_interrupted = True

    ran = run_cli("logs", "-f")

    assert ran.code == 0
    assert ran.err == ""


def test_follow_takes_one_log_at_a_time(machine, logs, run_cli):
    ran = run_cli("logs", "all", "-f")

    assert ran.code == 2
    assert "one log at a time" in ran.err
    assert _followed(machine) == []
