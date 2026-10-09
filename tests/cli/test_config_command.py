from tests.cli.support import configured

BROKEN = configured("unknown_key = 1\n")


def _rows(out):
    return out.splitlines()[2:]


def test_help_survives_a_broken_config(machine, run_cli):
    machine.config_path.write_text(BROKEN)
    ran = run_cli("--help")
    assert ran.code == 0
    assert ran.out.startswith("usage: github-orchestrator ")
    assert "unknown_key" not in ran.out + ran.err


def test_a_broken_config_stops_a_real_command(machine, run_cli):
    machine.config_path.write_text(BROKEN)
    ran = run_cli("runs")
    assert ran.code == 2
    assert "unknown key 'unknown_key'" in ran.err
    assert ran.out == ""


def test_config_prints_effective_values_and_where_each_came_from(machine, run_cli):
    machine.configure("agents_enabled = false\n")
    ran = run_cli("config")
    assert ran.code == 0
    assert ran.out.startswith(f"{machine.config_path}\n\n")
    rows = _rows(ran.out)
    assert any(row.split() == ["agents_enabled", "False", "config.toml"] for row in rows)
    assert any(row.split() == ["watcher_poll_interval", "60", "default"] for row in rows)
    assert any(row.split() == ["repos", "octocat/hello-world", "at",
                               "/tmp/github-orchestrator-tests/hello-world", "config.toml"]
               for row in rows)


def test_config_pads_the_key_column_but_not_the_values(machine, run_cli):
    machine.configure("agents_enabled = false\n")
    rows = _rows(run_cli("config").out)
    width = max(len(row.split()[0]) for row in rows)
    assert f"{'agents_enabled':<{width}}  False  config.toml" in rows


def test_config_prints_the_table_before_refusing_an_unset_config(machine, run_cli):
    machine.config_path.write_text("watcher_poll_interval = 30\n")

    ran = run_cli("config")

    assert ran.code == 2
    rows = _rows(ran.out)
    assert any(row.split() == ["watcher_poll_interval", "30", "config.toml"] for row in rows)
    [account_row] = [row for row in rows if row.startswith("gh_account")]
    assert account_row.endswith("your-github-username  unset")
    for key in ("gh_account", "repos"):
        assert key in ran.err
    assert "setup" in ran.err


def test_config_names_a_file_that_is_not_there_yet(machine, run_cli):
    machine.config_path.unlink()
    ran = run_cli("config")
    assert ran.code == 2
    assert ran.out.startswith(f"{machine.config_path} (no file there yet)\n\n")


def test_config_reports_a_broken_config_instead_of_crashing(machine, run_cli):
    machine.config_path.write_text(BROKEN)
    ran = run_cli("config")
    assert ran.code == 2
    assert "unknown key 'unknown_key'" in ran.err
    assert ran.out == ""
