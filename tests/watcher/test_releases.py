import json
from dataclasses import replace
from datetime import timedelta

import pytest

from github_orchestrator.board_api.interface import SetupDesk
from github_orchestrator.domain import HubState
from github_orchestrator.watcher import Releases, Watcher
from tests.watcher.scripted_releases import (
    LATEST,
    ScriptedReleasesApi,
    tagged,
    wheel_asset,
)
from tests.watcher.support import NOW, watcher_container


def _seen(release):
    return release.version, release.wheel, release.checked_at


@pytest.fixture
def api():
    return ScriptedReleasesApi()


def _releases(settings, api, *, now=NOW, token=None) -> Releases:
    releases: Releases = watcher_container(settings, clock=lambda: now, releases_api=api,
                                           github_token=token).get(Releases)
    return releases


def test_the_daily_check_records_the_newest_release_and_when_it_looked(settings, api):
    api.publish("0.2.0")

    _releases(settings, api).check_if_due()

    assert _seen(_releases(settings, api).recorded()) == ("0.2.0", wheel_asset("0.2.0"), NOW)
    assert json.loads(settings.newest_release.read_text())["version"] == "0.2.0"
    assert [asked.url for asked in api.asked] == [LATEST]


def test_a_restart_within_a_day_of_the_last_check_does_not_ask_again(settings, api):
    api.publish("0.2.0")
    _releases(settings, api).check_if_due()

    _releases(settings, api, now=NOW + timedelta(hours=23)).check_if_due()

    assert len(api.asked) == 1


def test_a_day_after_the_last_check_it_asks_again(settings, api):
    api.publish("0.2.0")
    releases = _releases(settings, api)
    releases.check_if_due()
    api.publish("0.3.0")

    later = _releases(settings, api, now=NOW + timedelta(hours=24, seconds=1))
    later.check_if_due()

    assert later.recorded().version == "0.3.0"


def test_a_failed_check_keeps_the_last_answer(settings, api):
    api.publish("0.2.0")
    _releases(settings, api).check_if_due()
    api.answers[LATEST] = OSError("network is unreachable")

    later = _releases(settings, api, now=NOW + timedelta(days=2))
    later.check_if_due()

    assert _seen(later.recorded()) == ("0.2.0", wheel_asset("0.2.0"), NOW)


def test_a_failed_check_is_not_retried_every_loop(settings, api):
    api.answers[LATEST] = OSError("network is unreachable")
    releases = _releases(settings, api)

    releases.check_if_due()
    releases.check_if_due()

    assert len(api.asked) == 1


def test_with_check_for_updates_off_the_hub_never_asks_and_has_nothing_recorded(settings, api):
    api.publish("0.2.0")
    settings = replace(settings, config=replace(settings.config, check_for_updates=False))
    settings.newest_release.write_text(json.dumps(
        {"version": "0.2.0", "wheel": None, "checked_at": NOW.isoformat()}))
    releases = _releases(settings, api)

    releases.check_if_due()

    assert api.asked == []
    assert releases.recorded() is None


def test_an_unreadable_record_reads_as_no_check_yet(settings, api):
    settings.newest_release.write_text("{not json")

    assert _releases(settings, api).recorded() is None


def test_looking_up_with_no_version_asks_for_the_newest_release(settings, api):
    api.publish("0.2.0")

    assert _seen(_releases(settings, api).look_up(None)) == ("0.2.0", wheel_asset("0.2.0"), None)


def test_looking_up_a_version_asks_for_its_tag(settings, api):
    api.publish("0.1.0", latest=False)
    api.publish("0.2.0")

    assert _releases(settings, api).look_up("0.1.0").version == "0.1.0"
    assert api.asked[-1].url == tagged("0.1.0")


def test_a_lookup_that_fails_says_why(settings, api):
    looked = _releases(settings, api).look_up("9.9.9")

    assert isinstance(looked, str)
    assert "9.9.9" in looked and "404" in looked


def test_a_token_in_the_environment_goes_with_every_request(settings, api):
    api.publish("0.2.0")

    _releases(settings, api, token="t0ken").look_up(None)

    assert api.asked[-1].token == "t0ken"


def test_download_saves_the_wheel_under_its_own_name(settings, api, tmp_path):
    api.publish("0.2.0")
    releases = _releases(settings, api)

    saved = releases.download(releases.look_up(None), tmp_path)

    assert saved == tmp_path / "github_orchestrator-0.2.0-py3-none-any.whl"
    assert saved.read_bytes() == b"wheel 0.2.0"
    assert api.asked[-1].accept == "application/octet-stream"


@pytest.mark.parametrize("candidate,running,newer", [
    ("0.2.0", "0.1.0", True),
    ("0.1.0", "0.1.0", False),
    ("0.1.0", "0.2.0", False),
    ("1.0.0", "0.9.9", True),
    ("0.10.0", "0.9.0", True),
    ("0.1.0", "0.1.0rc2", True),
    ("0.1.0-rc.10", "0.1.0-rc.2", True),
    ("0.1.0-rc.2", "0.1.0", False),
    ("0.2.0", None, False),
    ("not-a-version", "0.1.0", False),
])
def test_a_release_is_newer_only_by_semver_order(settings, api, candidate, running, newer):
    api.publish(candidate)

    assert _releases(settings, api).look_up(None).newer_than(running) is newer


def test_a_watcher_waiting_in_setup_runs_the_daily_check(settings, api):
    api.publish("0.2.0")
    states = iter([HubState.SETUP, HubState.WATCHING])

    watcher_container(settings, releases_api=api, sleep=lambda seconds: None).get(
        Watcher).wait_in(HubState.SETUP, lambda: next(states))

    assert [asked.url for asked in api.asked] == [LATEST]


def test_a_watching_watcher_runs_the_daily_check_once_a_cycle(settings, api):
    api.publish("0.2.0")
    settings.config_path.write_text("gh_account = \n")
    container = watcher_container(settings, releases_api=api,
                                  sleep=lambda seconds: container.get(SetupDesk).move_aside())

    container.get(Watcher).run_forever()

    assert [asked.url for asked in api.asked] == [LATEST]
