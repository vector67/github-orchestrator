from dataclasses import replace

from github_orchestrator.board_api.fake import FakeMentionsList
from github_orchestrator.board_api.interface import ListedMention, MentionsListing
from tests.board_api.support import holding, served_hub
from tests.builders import a_pr

HELD = a_pr(7, "acme/widgets")
GONE = a_pr(8, "acme/widgets")
PING = ListedMention(pr=HELD, thread="IC_1", comment_id=1, kind="issue", author="anna",
                     at="2026-10-22T10:00:00Z", body="@octocat ping",
                     url="https://github.com/acme/widgets/pull/7#issuecomment-1", card=True)


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
                      "on_board": True}]}


def test_a_mention_is_on_the_board_only_when_the_watcher_holds_its_pr_and_its_card_is_made():
    web = served_hub(told=holding(HELD), mentions=_listed(
        PING, replace(PING, thread="IC_2", comment_id=2, card=False),
        replace(PING, pr=GONE, thread="IC_3", comment_id=3)))

    assert [(mention["thread"], mention["on_board"])
            for mention in web.get("/api/mentions").json()["mentions"]] == [
        ("IC_1", True), ("IC_2", False), ("IC_3", False)]


def test_no_mentions_are_listed_before_the_first_search():
    web = served_hub(told=holding(HELD), mentions=FakeMentionsList())

    assert web.get("/api/mentions").json() == {"searched_at": None, "mentions": []}
