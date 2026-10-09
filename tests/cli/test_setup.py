HUB = "http://127.0.0.1:8720"


def test_setup_says_setup_is_on_the_board_and_opens_its_setup_page(machine, run_cli, restartable):
    machine.config_path.unlink()
    machine.answering_hubs.add(HUB)

    ran = run_cli("setup")

    assert ran.code == 0
    assert "Setup is on the board now: http://127.0.0.1:8720/setup" in ran.out
    assert machine.desktop.opened == ["http://127.0.0.1:8720/setup"]
    assert not machine.config_path.exists()


def test_setup_on_a_watching_config_opens_the_same_page_to_add_or_remove_repos(
        machine, run_cli, restartable):
    machine.answering_hubs.add(HUB)
    before = machine.config_path.read_text()

    ran = run_cli("setup")

    assert ran.code == 0
    assert machine.desktop.opened == ["http://127.0.0.1:8720/setup"]
    assert machine.config_path.read_text() == before


def test_setup_where_nothing_opens_a_browser_still_prints_where_to_go(machine, run_cli, restartable):
    machine.answering_hubs.add(HUB)
    machine.desktop.macos = False

    ran = run_cli("setup")

    assert ran.code == 0
    assert "If your browser didn't open, go to http://127.0.0.1:8720/setup" in ran.out


def test_setup_starts_a_watcher_that_is_not_running_before_opening_the_page(machine, run_cli):
    machine.config_path.unlink()
    machine.while_asleep.append(lambda: machine.answering_hubs.add(HUB))

    ran = run_cli("setup")

    assert ran.code == 0, ran.out
    assert f"Started the watcher. Hub: {HUB}" in ran.out
    assert machine.desktop.opened == ["http://127.0.0.1:8720/setup"]
