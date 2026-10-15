from typing import Any

from pr_summary.pull_request import cleaned, pull_request_from, voices
from pr_summary.settings import Settings, settings_from


def person(login: str, name: str | None = None) -> dict[str, str | None]:
    return {"login": login, "__typename": "User", "name": name}


def remark(login: str, body: str, kind: str = "User") -> dict[str, Any]:
    return {"author": {"login": login, "__typename": kind}, "body": body, "url": f"https://github.com/acme/shop/pull/7#{login}"}


GRAPHQL: dict[str, Any] = {
    "data": {
        "repository": {
            "pullRequest": {
                "number": 7,
                "url": "https://github.com/acme/shop/pull/7",
                "title": "[SHOP-3] Hide the export button",
                "body": "Hides the button when exports are off.",
                "createdAt": "2026-10-01T09:00:00Z",
                "headRefName": "SHOP-3-hide-button",
                "baseRefOid": "b" * 40,
                "headRefOid": "h" * 40,
                "changedFiles": 6,
                "author": person("octocat", "Octo Cat"),
                "commits": {
                    "nodes": [
                        {"commit": {"message": "hide the button", "authors": {"nodes": [{"name": "Octo Cat", "user": person("octocat")}]}}},
                        {"commit": {"message": "pair on tests", "authors": {"nodes": [{"name": "Octo Cat", "user": person("octocat")}, {"name": "Hu Bot", "user": person("hubot")}, {"name": "Mona Pair", "user": None}]}}},
                    ]
                },
                "comments": {"nodes": [remark("monalisa", "Why hide it rather than fix exports?"), remark("octocat", "Exports are being rewritten.")]},
                "reviews": {"nodes": [remark("claude", "Summary of the change", "Bot"), remark("monalisa", "")]},
                "reviewThreads": {"nodes": [{"comments": {"nodes": [remark("monalisa", "Is this flag documented?"), remark("hubot", "Yes, in the wiki.")]}}]},
            }
        }
    }
}


def test_the_authors_are_the_pr_author_and_every_commit_author() -> None:
    assert pull_request_from(GRAPHQL).authors == frozenset({"octocat", "hubot"})


def test_the_authors_names_include_co_authors_without_a_login() -> None:
    assert pull_request_from(GRAPHQL).author_names == frozenset({"Octo Cat", "Hu Bot", "Mona Pair"})


def test_the_pull_request_keeps_its_identity_and_commit_messages() -> None:
    pr = pull_request_from(GRAPHQL)

    assert (pr.number, pr.title, pr.branch, pr.base_sha) == (7, "[SHOP-3] Hide the export button", "SHOP-3-hide-button", "b" * 40)
    assert pr.commit_messages == ("hide the button", "pair on tests")


def test_empty_remarks_are_dropped() -> None:
    bodies = [found.body for found in pull_request_from(GRAPHQL).remarks]

    assert "" not in bodies
    assert len(bodies) == 5


def test_voices_split_authors_from_other_humans_and_drop_bots() -> None:
    pr = pull_request_from(GRAPHQL)

    authors, others = voices(pr.remarks, pr.authors, Settings())

    assert [found.body for found in authors] == ["Exports are being rewritten.", "Yes, in the wiki."]
    assert [found.body for found in others] == ["Why hide it rather than fix exports?", "Is this flag documented?"]


def test_configured_bots_are_dropped_too() -> None:
    pr = pull_request_from(GRAPHQL)

    _, others = voices(pr.remarks, pr.authors, settings_from('[pr_summary]\nbots = ["monalisa"]\n'))

    assert others == []


def test_bot_suffixed_logins_are_bots_whatever_their_type() -> None:
    found = pull_request_from(GRAPHQL).remarks[0]
    renamed = type(found)(author="ci[bot]", bot=False, body="Build passed", url="u")

    _, others = voices([renamed], frozenset(), Settings())

    assert others == []


def test_well_known_user_type_bots_and_bot_suffixes_are_bots() -> None:
    found = pull_request_from(GRAPHQL).remarks[0]
    disguised = [type(found)(author=login, bot=False, body="Coverage report", url="u") for login in ["codecov-commenter", "element-bot", "CLAassistant"]]

    _, others = voices(disguised, frozenset(), Settings())

    assert others == []


def test_cleaned_drops_quoted_lines_and_suggestions() -> None:
    body = "> You said this hides it\nIt should be fixed instead.\n```suggestion\nreturn rows\n```\nThanks."

    assert cleaned(body) == "It should be fixed instead.\nThanks."
