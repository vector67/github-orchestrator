HUB = "http://127.0.0.1:8720"


def test_tutorial_opens_the_board_at_its_tour(machine, run_cli, restartable):
    machine.answering_hubs.add(HUB)

    ran = run_cli("tutorial")

    assert ran.code == 0
    assert machine.desktop.opened == [f"{HUB}/?tour=1"]
    assert f"If your browser didn't open, go to {HUB}/?tour=1" in ran.out


def test_tutorial_starts_a_watcher_that_is_not_running_before_opening_the_tour(
        machine, run_cli):
    machine.while_asleep.append(lambda: machine.answering_hubs.add(HUB))

    ran = run_cli("tutorial")

    assert ran.code == 0, ran.out
    assert f"Started the watcher. Hub: {HUB}" in ran.out
    assert machine.desktop.opened == [f"{HUB}/?tour=1"]


def test_tutorial_in_the_terminal_reprints_what_the_installer_set_up_and_opens_nothing(
        machine, run_cli):
    ran = run_cli("tutorial", "--terminal")

    assert ran.code == 0
    assert machine.desktop.opened == []
    for said in ("uv", "gh", "claude", "LaunchAgent", "systemd user unit",
                 f"The board is at {HUB}", "github-orchestrator doctor",
                 "github-orchestrator setup"):
        assert said in ran.out


def test_tutorial_in_the_terminal_names_the_agent_this_instance_runs(machine, run_cli):
    machine.configure('agent = "codex"\nagent_command = "codex"\n')

    ran = run_cli("tutorial", "--terminal")

    assert "  codex   the Codex CLI, which the agents that work on your pull requests run" in ran.out
