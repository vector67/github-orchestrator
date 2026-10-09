HUB = "http://127.0.0.1:8720"
FALLBACK = f"If your browser didn't open, go to {HUB}\n"


def test_open_opens_the_board_of_a_running_watcher_and_prints_where_it_is(
        machine, run_cli, restartable):
    machine.answering_hubs.add(HUB)

    ran = run_cli("open")

    assert ran.code == 0, ran.out
    assert ran.out == f"Opening {HUB}\n{FALLBACK}"
    assert machine.desktop.opened == [HUB]
    assert restartable.read_text() == "<plist/>"


def test_open_starts_a_watcher_that_is_not_running_and_waits_for_its_hub(machine, run_cli):
    machine.while_asleep.append(lambda: machine.answering_hubs.add(HUB))

    ran = run_cli("open")

    assert ran.code == 0, ran.out
    assert ran.out == f"Started the watcher. Hub: {HUB} (watching)\nOpening {HUB}\n{FALLBACK}"
    assert machine.desktop.opened == [HUB]


def test_open_opens_nothing_when_the_hub_never_answers(machine, run_cli):
    ran = run_cli("open")

    assert ran.code == 1
    assert machine.desktop.opened == []


def test_open_still_prints_the_address_when_no_browser_opens(machine, run_cli, restartable):
    machine.answering_hubs.add(HUB)
    machine.desktop.macos = False

    ran = run_cli("open")

    assert ran.code == 0
    assert ran.out.endswith(FALLBACK)


def test_open_on_a_linux_without_a_graphical_session_only_prints_the_address(machine, run_cli):
    machine.platform = "linux"
    machine.graphical = False
    machine.system.units["github-orchestrator.service"] = "active"
    machine.answering_hubs.add(HUB)

    ran = run_cli("open")

    assert ran.code == 0
    assert ran.out == FALLBACK
    assert machine.desktop.opened == []


def test_open_uses_the_port_of_the_instance_it_opens(machine, run_cli, restartable):
    machine.configure("hub_port = 9100\n")
    machine.answering_hubs.add("http://127.0.0.1:9100")

    ran = run_cli("open")

    assert machine.desktop.opened == ["http://127.0.0.1:9100"]
    assert ran.out.endswith("If your browser didn't open, go to http://127.0.0.1:9100\n")
