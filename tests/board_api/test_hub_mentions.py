from dataclasses import replace

from github_orchestrator.board_api.fake import FakeMentionsList
from github_orchestrator.board_api.interface import (
    DeferredUntilPr,
    ListedMention,
    MentionDeferral,
    MentionsListing,
    PrMilestone,
)
from tests.board_api.support import holding, served_hub
from tests.builders import a_pr

HELD = a_pr(7, "acme/widgets")
GONE = a_pr(8, "acme/widgets")
PING = ListedMention(pr=HELD, thread="IC_1", comment_id=1, kind="issue", author="anna",
                     at="2026-10-22T10:00:00Z", body="@octocat ping",
                     url="https://github.com/acme/widgets/pull/7#issuecomment-1", on_board=True,
                     building=False)


def _listed(*mentions):
    return FakeMentionsList(MentionsListing(searched_at="2026-10-23T09:00:00+00:00",
                                            mentions=mentions))


def test_the_mentions_list_names_each_mention_and_where_it_is_on_github():
    web = served_hub(told=holding(HELD), mentions=_listed(PING))

    assert web.get("/api/mentions").json() == {
        "searched_at": "2026-10-23T09:00:00+00:00",
        "mentions": [{"repo": "acme/widgets", "number": 7, "thread": "IC_1", "comment_id": 1,
                      "kind": "issue", "author": "anna", "at": "2026-10-22T10:00:00Z",
                      "body": "@octocat ping",
                      "url": "https://github.com/acme/widgets/pull/7#issuecomment-1",
                      "on_board": True, "building": False, "deferred": None}]}


def test_a_mention_deferred_for_a_time_says_until_when():
    web = served_hub(told=holding(HELD), mentions=_listed(replace(PING, deferred=MentionDeferral(
        deferred_at="2026-10-23T09:00:00Z", until_at="2026-10-24T09:00:00Z", until_pr=None))))

    assert web.get("/api/mentions").json()["mentions"][0]["deferred"] == {
        "deferred_at": "2026-10-23T09:00:00Z", "until_at": "2026-10-24T09:00:00Z",
        "until_pr": None}


def test_a_mention_deferred_until_a_pr_names_the_pr_and_what_it_waits_for():
    web = served_hub(told=holding(HELD), mentions=_listed(replace(PING, deferred=MentionDeferral(
        deferred_at="2026-10-23T09:00:00Z", until_at=None,
        until_pr=DeferredUntilPr(pr=GONE, state=PrMilestone.APPROVED)))))

    assert web.get("/api/mentions").json()["mentions"][0]["deferred"]["until_pr"] == {
        "repo": "acme/widgets", "number": 8, "state": "approved"}


def test_deferring_a_mention_for_a_time_hands_the_list_when_it_was_deferred_and_until_when():
    listing = _listed(PING)
    web = served_hub(told=holding(HELD), mentions=listing)

    answered = web.post("/api/mentions:defer", json={
        "repo": "acme/widgets", "number": 7, "comment_id": 1,
        "until_at": "2026-08-29T09:00:00+02:00", "until_pr": None})

    assert (answered.status_code, listing.deferred) == (204, [(HELD, 1, MentionDeferral(
        deferred_at="2026-08-28T10:00:00+00:00", until_at="2026-08-29T09:00:00+02:00",
        until_pr=None))])


def test_deferring_a_mention_until_a_pr_hands_the_list_the_pr_and_its_state():
    listing = _listed(PING)
    web = served_hub(told=holding(HELD), mentions=listing)

    web.post("/api/mentions:defer", json={
        "repo": "acme/widgets", "number": 7, "comment_id": 1, "until_at": None,
        "until_pr": {"repo": "acme/widgets", "number": 8, "state": "new-commit"}})

    assert [deferral.until_pr for _, _, deferral in listing.deferred] == [
        DeferredUntilPr(pr=GONE, state=PrMilestone.NEW_COMMIT)]


def test_a_defer_naming_both_a_time_and_a_pr_is_refused():
    listing = _listed(PING)
    web = served_hub(told=holding(HELD), mentions=listing)

    answered = web.post("/api/mentions:defer", json={
        "repo": "acme/widgets", "number": 7, "comment_id": 1,
        "until_at": "2026-08-29T09:00:00+02:00",
        "until_pr": {"repo": "acme/widgets", "number": 8, "state": "merged"}})

    assert (answered.status_code, listing.deferred) == (400, [])


def test_a_defer_naming_neither_a_time_nor_a_pr_is_refused():
    listing = _listed(PING)
    web = served_hub(told=holding(HELD), mentions=listing)

    answered = web.post("/api/mentions:defer", json={
        "repo": "acme/widgets", "number": 7, "comment_id": 1, "until_at": None, "until_pr": None})

    assert (answered.status_code, listing.deferred) == (400, [])


def test_a_defer_until_a_time_that_is_no_time_is_refused():
    listing = _listed(PING)
    web = served_hub(told=holding(HELD), mentions=listing)

    answered = web.post("/api/mentions:defer", json={
        "repo": "acme/widgets", "number": 7, "comment_id": 1, "until_at": "friday",
        "until_pr": None})

    assert (answered.status_code, listing.deferred) == (400, [])


def test_stopping_a_deferral_hands_the_list_its_pr_and_comment():
    listing = _listed(PING)
    web = served_hub(told=holding(HELD), mentions=listing)

    answered = web.post("/api/mentions:stop-deferring",
                        json={"repo": "acme/widgets", "number": 7, "comment_id": 1})

    assert (answered.status_code, listing.undeferred) == (204, [(HELD, 1)])


def test_a_mention_is_on_the_board_only_when_the_watcher_holds_its_pr_and_its_card_is_made():
    web = served_hub(told=holding(HELD), mentions=_listed(
        PING, replace(PING, thread="IC_2", comment_id=2, on_board=False),
        replace(PING, pr=GONE, thread="IC_3", comment_id=3)))

    assert [(mention["thread"], mention["on_board"])
            for mention in web.get("/api/mentions").json()["mentions"]] == [
        ("IC_1", True), ("IC_2", False), ("IC_3", False)]


def test_a_mention_whose_card_is_being_built_says_so():
    web = served_hub(told=holding(HELD), mentions=_listed(
        replace(PING, on_board=False, building=True), replace(PING, thread="IC_2", comment_id=2,
                                                                on_board=False)))

    assert [(mention["thread"], mention["building"])
            for mention in web.get("/api/mentions").json()["mentions"]] == [
        ("IC_1", True), ("IC_2", False)]


def test_no_mentions_are_listed_before_the_first_search():
    web = served_hub(told=holding(HELD), mentions=FakeMentionsList())

    assert web.get("/api/mentions").json() == {"searched_at": None, "mentions": []}


def test_dismissing_a_mention_hands_its_pr_and_comment_to_the_list():
    listing = _listed(PING)
    web = served_hub(told=holding(HELD), mentions=listing)

    answered = web.post("/api/mentions:dismiss",
                        json={"repo": "acme/widgets", "number": 7, "comment_id": 1})

    assert (answered.status_code, listing.dismissed) == (204, [(HELD, 1)])


def test_dismissing_a_pr_body_mention_hands_no_comment_id():
    listing = _listed(PING)
    web = served_hub(told=holding(HELD), mentions=listing)

    web.post("/api/mentions:dismiss", json={"repo": "acme/widgets", "number": 7, "comment_id": None})

    assert listing.dismissed == [(HELD, None)]


def test_dismissing_a_mention_in_a_malformed_repo_is_refused():
    listing = _listed(PING)
    web = served_hub(told=holding(HELD), mentions=listing)

    answered = web.post("/api/mentions:dismiss",
                        json={"repo": "not a repo", "number": 7, "comment_id": 1})

    assert (answered.status_code, listing.dismissed) == (400, [])
