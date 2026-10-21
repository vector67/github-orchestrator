from pathlib import Path

from github_orchestrator.board_api.fake import FakeHarvestSetup
from tests.board_api.support import served_hub


def test_preparing_the_harvest_extension_answers_the_folder_to_load():
    setup = FakeHarvestSetup(Path("/data/harvest-extension"))

    answer = served_hub(harvest=setup).post("/api/harvest-extension:prepare")

    assert answer.status_code == 200
    assert answer.json() == {"folder": "/data/harvest-extension"}
    assert setup.prepared == 1


def test_chrome_without_harvest_is_refused_with_the_reason():
    setup = FakeHarvestSetup("Chrome has no Harvest Time Tracker installed")

    answer = served_hub(harvest=setup).post("/api/harvest-extension:prepare")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "harvest-extension-missing"
    assert answer.json()["errors"][0]["detail"] == "Chrome has no Harvest Time Tracker installed"
