from github_orchestrator.board_api.fake import FakeTimer, FakeTimers
from tests.board_api.support import THE_PR, client_for


def tracked(timer: FakeTimer) -> FakeTimers:
    return FakeTimers({THE_PR.repo: timer})


def test_a_pr_whose_repo_names_no_harvest_project_tracks_no_time():
    answer = client_for().get("/api/harvest-timer")

    assert answer.status_code == 200
    assert answer.json() == {"tracked": False, "running": False}


def test_a_tracked_pr_says_whether_its_timer_is_running():
    assert client_for(timers=tracked(FakeTimer())).get("/api/harvest-timer").json() == {
        "tracked": True, "running": False}
    assert client_for(timers=tracked(FakeTimer(is_running=True))).get(
        "/api/harvest-timer").json() == {"tracked": True, "running": True}


def test_starting_and_stopping_run_the_pr_s_timer():
    timer = FakeTimer()
    client = client_for(timers=tracked(timer))

    assert client.post("/api/harvest-timer:start").status_code == 204
    assert timer.is_running

    assert client.post("/api/harvest-timer:stop").status_code == 204
    assert not timer.is_running


def test_a_pr_that_tracks_no_time_has_no_timer_to_start():
    answer = client_for().post("/api/harvest-timer:start")

    assert answer.status_code == 404
    assert answer.json()["errors"][0]["code"] == "not-found"


def test_harvest_refusing_is_answered_with_its_reason():
    client = client_for(timers=tracked(FakeTimer(refusal="Harvest refused POST: 401")))

    for answer in (client.get("/api/harvest-timer"), client.post("/api/harvest-timer:start"),
                   client.post("/api/harvest-timer:stop")):
        assert answer.status_code == 502
        assert answer.json()["errors"][0]["code"] == "harvest-refused"
