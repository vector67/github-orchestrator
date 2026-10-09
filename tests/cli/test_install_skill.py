from pathlib import Path

PACKAGED = (Path(__file__).resolve().parents[2] / "src" / "github_orchestrator" / "cli" / "skills"
            / "rebase-on-main")


def _skill(machine) -> Path:
    return machine.home / ".claude" / "skills" / "rebase-on-main"


def _contents(folder: Path) -> dict[str, bytes]:
    return {str(path.relative_to(folder)): path.read_bytes()
            for path in folder.rglob("*") if path.is_file()}


def test_skill_copies_the_packaged_skill_into_claudes_skills(machine, run_cli):
    ran = run_cli("skill")

    assert ran.code == 0, ran.out
    assert _contents(_skill(machine)) == _contents(PACKAGED)
    assert f"Installed the rebase-on-main skill in {_skill(machine)}" in ran.out


def test_status_says_missing_before_the_skill_is_there(machine, run_cli):
    ran = run_cli("skill", "--status")

    assert (ran.code, ran.out) == (0, "missing\n")


def test_status_says_current_once_the_packaged_skill_is_there(machine, run_cli):
    run_cli("skill")

    ran = run_cli("skill", "--status")

    assert (ran.code, ran.out) == (0, "current\n")


def test_status_says_different_when_the_skill_there_was_edited(machine, run_cli):
    run_cli("skill")
    (_skill(machine) / "SKILL.md").write_text("my own rebase rules\n")

    ran = run_cli("skill", "--status")

    assert (ran.code, ran.out) == (0, "different\n")


def test_skill_leaves_an_edited_skill_alone_and_names_the_replace_option(machine, run_cli):
    run_cli("skill")
    (_skill(machine) / "SKILL.md").write_text("my own rebase rules\n")

    ran = run_cli("skill")

    assert ran.code == 1
    assert (_skill(machine) / "SKILL.md").read_text() == "my own rebase rules\n"
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
