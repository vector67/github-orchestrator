import shutil
from pathlib import Path

import pytest

SHIPPED = Path(__file__).resolve().parents[2] / "src" / "github_orchestrator" / "cli" / "skills"
PACKAGED = SHIPPED / "rebase-on-main"
CREATE_PR = SHIPPED / "create-pr"


def _skill(machine) -> Path:
    return machine.home / ".claude" / "skills" / "rebase-on-main"


def _create_pr(machine) -> Path:
    return machine.home / ".claude" / "skills" / "create-pr"


def _contents(folder: Path) -> dict[str, bytes]:
    return {str(path.relative_to(folder)): path.read_bytes()
            for path in folder.rglob("*") if path.is_file()}


def test_skill_copies_every_packaged_skill_into_claudes_skills(machine, run_cli):
    ran = run_cli("skill")

    assert ran.code == 0, ran.out
    assert _contents(_skill(machine)) == _contents(PACKAGED)
    assert _contents(_create_pr(machine)) == _contents(CREATE_PR)
    assert f"Installed the rebase-on-main skill in {_skill(machine)}" in ran.out
    assert f"Installed the create-pr skill in {_create_pr(machine)}" in ran.out


def test_status_says_missing_for_each_skill_before_any_is_there(machine, run_cli):
    ran = run_cli("skill", "--status")

    assert (ran.code, ran.out) == (0, "create-pr missing\nrebase-on-main missing\n")


def test_status_says_current_for_each_once_the_packaged_skills_are_there(machine, run_cli):
    run_cli("skill")

    ran = run_cli("skill", "--status")

    assert (ran.code, ran.out) == (0, "create-pr current\nrebase-on-main current\n")


def test_status_says_different_for_the_skill_there_that_was_edited(machine, run_cli):
    run_cli("skill")
    (_skill(machine) / "SKILL.md").write_text("my own rebase rules\n")

    ran = run_cli("skill", "--status")

    assert (ran.code, ran.out) == (0, "create-pr current\nrebase-on-main different\n")


def test_skill_leaves_an_edited_skill_alone_installs_a_missing_one_and_names_the_replace_option(
        machine, run_cli):
    run_cli("skill")
    (_skill(machine) / "SKILL.md").write_text("my own rebase rules\n")
    shutil.rmtree(_create_pr(machine))

    ran = run_cli("skill")

    assert ran.code == 1
    assert (_skill(machine) / "SKILL.md").read_text() == "my own rebase rules\n"
    assert _contents(_create_pr(machine)) == _contents(CREATE_PR)
    assert "github-orchestrator skill --replace" in ran.out


def test_replace_puts_the_packaged_skill_over_an_edited_one(machine, run_cli):
    run_cli("skill")
    (_skill(machine) / "SKILL.md").write_text("my own rebase rules\n")
    (_skill(machine) / "notes.md").write_text("mine\n")

    ran = run_cli("skill", "--replace")

    assert ran.code == 0, ran.out
    assert _contents(_skill(machine)) == _contents(PACKAGED)


def test_replace_puts_the_packaged_skill_in_place_of_a_link(machine, run_cli, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _skill(machine).parent.mkdir(parents=True)
    _skill(machine).symlink_to(elsewhere)

    ran = run_cli("skill", "--replace")

    assert ran.code == 0, ran.out
    assert not _skill(machine).is_symlink()
    assert _contents(_skill(machine)) == _contents(PACKAGED)
    assert elsewhere.is_dir()


def test_skill_says_so_when_the_packaged_skill_is_already_there(machine, run_cli):
    run_cli("skill")

    ran = run_cli("skill")

    assert ran.code == 0
    assert f"The rebase-on-main skill in {_skill(machine)} is already this version's" in ran.out


def test_skill_installs_before_the_setup_page_has_filled_in_the_config(machine, run_cli):
    machine.config_path.write_text("")

    ran = run_cli("skill")

    assert ran.code == 0, ran.err
    assert _contents(_skill(machine)) == _contents(PACKAGED)


def _codex_skill(machine) -> Path:
    return machine.home / ".agents" / "skills" / "rebase-on-main"


def test_a_codex_instance_installs_the_skill_where_codex_reads_skills(machine, run_cli):
    machine.configure('agent = "codex"\nagent_command = "codex"\n')

    ran = run_cli("skill")

    assert ran.code == 0, ran.out
    assert _contents(_codex_skill(machine)) == _contents(PACKAGED)
    assert not _skill(machine).exists()
    assert f"Installed the rebase-on-main skill in {_codex_skill(machine)}" in ran.out


def test_a_codex_instance_not_yet_set_up_still_installs_where_codex_reads_skills(
        machine, run_cli):
    machine.config_path.write_text('agent = "codex"\n')

    ran = run_cli("skill")

    assert ran.code == 0, ran.err
    assert _contents(_codex_skill(machine)) == _contents(PACKAGED)


def test_the_skill_finds_its_script_beside_itself_whichever_agent_reads_it():
    said = (PACKAGED / "SKILL.md").read_text()

    assert "~/" not in said
    assert "rebase-on-main.sh" in said


def test_a_claude_instance_with_its_own_config_dir_installs_the_skill_there(machine, run_cli):
    machine.configure('agent_command = "CLAUDE_CONFIG_DIR=~/.claude-work claude"\n')
    work_skill = machine.home / ".claude-work" / "skills" / "rebase-on-main"

    ran = run_cli("skill")

    assert ran.code == 0, ran.out
    assert _contents(work_skill) == _contents(PACKAGED)
    assert not _skill(machine).exists()


def _upgrading(machine) -> None:
    machine.configure()
    machine.answering_hubs.add("http://127.0.0.1:8720")


def test_the_installer_s_start_installs_a_shipped_skill_missing_beside_one_already_there(
        machine, run_cli):
    _upgrading(machine)
    _skill(machine).parent.mkdir(parents=True)
    shutil.copytree(PACKAGED, _skill(machine))

    ran = run_cli("start", "--from-installer")

    assert ran.code == 0, ran.out
    assert _contents(_create_pr(machine)) == _contents(CREATE_PR)
    assert f"Installed the create-pr skill in {_create_pr(machine)}" in ran.out


def test_the_installer_s_start_leaves_an_edited_skill_alone_and_names_the_replace_option(
        machine, run_cli):
    _upgrading(machine)
    _skill(machine).parent.mkdir(parents=True)
    shutil.copytree(PACKAGED, _skill(machine))
    (_skill(machine) / "SKILL.md").write_text("my own rebase rules\n")

    ran = run_cli("start", "--from-installer")

    assert ran.code == 0, ran.out
    assert (_skill(machine) / "SKILL.md").read_text() == "my own rebase rules\n"
    assert "github-orchestrator skill --replace" in ran.out


def _recorded_pr_skill(machine) -> str:
    return machine.settings().config.pr_skill


def test_the_installer_s_start_with_no_terminal_installs_every_missing_skill_without_asking(
        machine, run_cli):
    _upgrading(machine)

    ran = run_cli("start", "--from-installer")

    assert ran.code == 0, ran.out
    assert machine.prompts == []
    assert _contents(_skill(machine)) == _contents(PACKAGED)
    assert _contents(_create_pr(machine)) == _contents(CREATE_PR)
    assert _recorded_pr_skill(machine) == "create-pr"


def test_the_installer_s_start_on_a_terminal_names_each_missing_skill_and_installs_on_yes(
        machine, run_cli):
    _upgrading(machine)
    machine.interactive = True
    machine.answers = [""]

    ran = run_cli("start", "--from-installer")

    assert ran.code == 0, ran.out
    assert machine.prompts == ["Install them? [Y/n] "]
    assert "create-pr: agents run it to open a new pull request" in ran.out
    assert "rebase-on-main: agents run it to rebase a pull request's branch" in ran.out
    assert _contents(_skill(machine)) == _contents(PACKAGED)
    assert _contents(_create_pr(machine)) == _contents(CREATE_PR)


def test_the_installer_s_start_on_a_terminal_asks_only_about_the_skills_missing(
        machine, run_cli):
    _upgrading(machine)
    _skill(machine).parent.mkdir(parents=True)
    shutil.copytree(PACKAGED, _skill(machine))
    machine.interactive = True
    machine.answers = ["y"]

    ran = run_cli("start", "--from-installer")

    assert ran.code == 0, ran.out
    assert "create-pr: agents run it" in ran.out
    assert "rebase-on-main: agents run it" not in ran.out
    assert _contents(_create_pr(machine)) == _contents(CREATE_PR)


def test_a_no_on_the_terminal_leaves_the_skills_out_and_records_an_empty_pr_skill(
        machine, run_cli):
    _upgrading(machine)
    machine.interactive = True
    machine.answers = ["n"]

    ran = run_cli("start", "--from-installer")

    assert ran.code == 0, ran.out
    assert not _skill(machine).exists() and not _create_pr(machine).exists()
    assert "Skills left out: create-pr, rebase-on-main." in ran.out
    assert 'pr_skill = ""' in ran.out
    assert _recorded_pr_skill(machine) == ""


def test_a_no_with_create_pr_there_leaves_the_pr_skill_as_it_was(machine, run_cli):
    _upgrading(machine)
    _create_pr(machine).parent.mkdir(parents=True)
    shutil.copytree(CREATE_PR, _create_pr(machine))
    machine.interactive = True
    machine.answers = ["no"]

    ran = run_cli("start", "--from-installer")

    assert ran.code == 0, ran.out
    assert not _skill(machine).exists()
    assert _recorded_pr_skill(machine) == "create-pr"


@pytest.mark.parametrize("interactive", [True, False])
def test_an_empty_pr_skill_already_recorded_is_the_answer_and_nothing_is_asked_or_installed(
        machine, run_cli, interactive):
    machine.configure('pr_skill = ""\n')
    machine.answering_hubs.add("http://127.0.0.1:8720")
    machine.interactive = interactive

    ran = run_cli("start", "--from-installer")

    assert ran.code == 0, ran.out
    assert machine.prompts == []
    assert not _skill(machine).exists() and not _create_pr(machine).exists()
    assert "Skills left out: create-pr, rebase-on-main" in ran.out
    assert "github-orchestrator skill" in ran.out


def test_the_installer_s_start_asks_nothing_when_every_skill_is_there(machine, run_cli):
    _upgrading(machine)
    run_cli("skill")
    machine.interactive = True

    ran = run_cli("start", "--from-installer")

    assert ran.code == 0, ran.out
    assert machine.prompts == []
    assert f"The create-pr skill in {_create_pr(machine)} is already this version's" in ran.out


def test_installing_the_skills_puts_back_the_create_pr_name_an_earlier_no_left_empty(
        machine, run_cli):
    machine.configure('pr_skill = ""\n')

    ran = run_cli("skill")

    assert ran.code == 0, ran.out
    assert _recorded_pr_skill(machine) == "create-pr"
    assert 'pr_skill = "create-pr"' in ran.out


def test_installing_the_skills_keeps_a_pr_skill_of_your_own(machine, run_cli):
    machine.configure('pr_skill = "team-pr"\n')

    run_cli("skill")

    assert _recorded_pr_skill(machine) == "team-pr"


def test_leave_out_records_an_empty_pr_skill_while_create_pr_is_missing(machine, run_cli):
    ran = run_cli("skill", "--leave-out")

    assert ran.code == 0, ran.out
    assert _recorded_pr_skill(machine) == ""
    assert not _create_pr(machine).exists()


def test_leave_out_keeps_the_create_pr_name_while_create_pr_is_there(machine, run_cli):
    run_cli("skill")

    run_cli("skill", "--leave-out")

    assert _recorded_pr_skill(machine) == "create-pr"


def test_a_codex_instance_s_no_records_an_empty_pr_skill_too(machine, run_cli):
    machine.configure('agent = "codex"\nagent_command = "codex"\n')
    machine.answering_hubs.add("http://127.0.0.1:8720")
    machine.interactive = True
    machine.answers = ["n"]

    ran = run_cli("start", "--from-installer")

    assert ran.code == 0, ran.out
    assert f"missing from {machine.home / '.agents' / 'skills'}" in ran.out
    assert _recorded_pr_skill(machine) == ""


def test_the_installer_s_start_leaves_the_skills_to_the_install_script_when_it_offers_them(
        machine, run_cli):
    _upgrading(machine)
    _skill(machine).parent.mkdir(parents=True)
    shutil.copytree(PACKAGED, _skill(machine))
    machine.extra_environment["GITHUB_ORCHESTRATOR_LEAVE_SKILLS"] = "1"

    ran = run_cli("start", "--from-installer")

    assert ran.code == 0, ran.out
    assert not _create_pr(machine).exists()
    assert "skill" not in ran.out
