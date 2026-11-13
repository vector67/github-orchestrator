import subprocess

import pytest

from tests.builders import a_pr
from tests.working_copies.support import real_working_copies

THE_PR = a_pr(12, "acme/widgets")


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _commit(clone, files, message):
    for name, text in files.items():
        path = clone / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    _git(clone, "add", "-f", *files)
    _git(clone, "commit", "-q", "-m", message)


def _build(root):
    origin = root / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = root / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True,
                   capture_output=True)
    _git(seed, "config", "user.email", "octocat@example.com")
    _git(seed, "config", "user.name", "Octocat")
    _commit(seed, {"CLAUDE.md": "be kind\n", ".claude/settings.json": "{}\n",
                   "app.py": "print(1)\n"}, "base")
    _git(seed, "push", "-q", "origin", "main")
    _git(seed, "checkout", "-q", "-b", "stacked-base")
    _commit(seed, {"CLAUDE.md": "be bold\n"}, "change the instructions")
    _git(seed, "push", "-q", "origin", "stacked-base")
    _git(seed, "checkout", "-q", "main")
    _commit(seed, {"CLAUDE.md": "be brief\n"}, "main moves on")
    _git(seed, "push", "-q", "origin", "main")


@pytest.fixture
def clone(tmp_path, git_template):
    git_template(_build)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(work)], check=True,
                   capture_output=True)
    _git(work, "config", "user.email", "octocat@example.com")
    _git(work, "config", "user.name", "Octocat")
    _git(work, "checkout", "-q", "-b", "feature", "main~1")
    return work


@pytest.fixture
def copies(settings):
    return real_working_copies(settings)


def test_a_branch_that_changes_no_agent_configuration_holds_nothing(clone, copies):
    _commit(clone, {"app.py": "print(2)\n", "docs/notes.md": "CLAUDE.md is elsewhere\n"},
            "work")

    config = copies.agent_config(THE_PR, str(clone))

    assert config is not None
    assert config.changed == ()
    assert not config.held
    assert config.project_settings


def test_a_branch_that_changes_agent_configuration_is_held_naming_each_file(clone, copies):
    _commit(clone, {".claude/settings.json": '{"hooks": {}}\n', ".mcp.json": "{}\n",
                    "lib/AGENTS.md": "x\n", "lib/CLAUDE.local.md": "x\n",
                    "lib/deep/CLAUDE.md": "x\n", ".codex/config.toml": "x\n",
                    ".agents/skills/s.md": "x\n", "app.py": "print(2)\n",
                    "lib/.claude/settings.json": "{}\n"}, "work")

    config = copies.agent_config(THE_PR, str(clone))

    assert config is not None
    assert config.changed == (".agents/skills/s.md", ".claude/settings.json",
                              ".codex/config.toml", ".mcp.json", "lib/AGENTS.md",
                              "lib/CLAUDE.local.md", "lib/deep/CLAUDE.md")
    assert config.held
    assert not config.project_settings


def test_what_the_default_branch_changed_since_the_branch_left_it_is_not_counted(clone, copies):
    config = copies.agent_config(THE_PR, str(clone))

    assert config is not None
    assert config.changed == ()


def test_a_branch_stacked_on_another_is_compared_with_the_default_branch(clone, copies):
    _git(clone, "checkout", "-q", "-b", "stacked", "origin/stacked-base")
    _commit(clone, {"app.py": "print(3)\n"}, "stacked work")

    config = copies.agent_config(THE_PR, str(clone))

    assert config is not None
    assert config.changed == ("CLAUDE.md",)


def test_allowing_the_changes_lifts_the_hold_and_loads_project_settings(clone, copies):
    _commit(clone, {"CLAUDE.md": "be bold\n"}, "work")
    held = copies.agent_config(THE_PR, str(clone))
    assert held is not None

    copies.answer_agent_config(THE_PR, held.digest, allowed=True)

    config = copies.agent_config(THE_PR, str(clone))
    assert config is not None
    assert not config.held
    assert config.project_settings


def test_turning_the_changes_down_lifts_the_hold_and_loads_user_settings_only(clone, copies):
    _commit(clone, {"CLAUDE.md": "be bold\n"}, "work")
    held = copies.agent_config(THE_PR, str(clone))
    assert held is not None

    copies.answer_agent_config(THE_PR, held.digest, allowed=False)

    config = copies.agent_config(THE_PR, str(clone))
    assert config is not None
    assert not config.held
    assert not config.project_settings


def test_a_push_that_changes_the_configuration_again_holds_it_again(clone, copies):
    _commit(clone, {"CLAUDE.md": "be bold\n"}, "work")
    held = copies.agent_config(THE_PR, str(clone))
    assert held is not None
    copies.answer_agent_config(THE_PR, held.digest, allowed=True)

    _commit(clone, {"CLAUDE.md": "be reckless\n"}, "more work")

    config = copies.agent_config(THE_PR, str(clone))
    assert config is not None
    assert config.held


def test_a_push_that_leaves_the_configuration_alone_keeps_the_answer(clone, copies):
    _commit(clone, {"CLAUDE.md": "be bold\n"}, "work")
    held = copies.agent_config(THE_PR, str(clone))
    assert held is not None
    copies.answer_agent_config(THE_PR, held.digest, allowed=True)

    _commit(clone, {"app.py": "print(4)\n"}, "more work")

    config = copies.agent_config(THE_PR, str(clone))
    assert config is not None
    assert not config.held
    assert config.project_settings


def test_git_that_cannot_say_answers_none(tmp_path, copies):
    assert copies.agent_config(THE_PR, str(tmp_path / "nowhere")) is None
