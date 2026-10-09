from github_orchestrator.notifications import BoardPages
from github_orchestrator.wiring import make_container
from tests.builders import a_pr


def _pages(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('gh_account = "hubot"\nhub_port = 8721\n'
                      '[[repos]]\nrepo = "hubot/robots"\nlocal_path = "~/repositories/robots"\n')
    container = make_container({"GITHUB_ORCHESTRATOR_CONFIG": str(config),
                                "GITHUB_ORCHESTRATOR_DATA_DIR": str(tmp_path / "data")},
                               tmp_path)
    return container.get(BoardPages)


def test_a_pr_opens_on_its_board_at_the_instances_own_hub(tmp_path):
    assert _pages(tmp_path).board_of(a_pr(101, "hubot/robots")) == (
        "http://127.0.0.1:8721/pr/hubot/robots/101")

