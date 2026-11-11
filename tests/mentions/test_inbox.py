import json
import shutil
import tomllib
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from github_orchestrator.board_api.interface import (
    NO_MENTIONS_LISTED,
    DeferredUntilPr,
    ListedMention,
    MentionDeferral,
    MentionsList,
    MentionsListing,
    OpenedForMention,
    PrEnded,
    PrMilestone,
)
from github_orchestrator.change_detection import Poll
from github_orchestrator.conversation import ConversationState
from github_orchestrator.domain import Pr, Repo
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    Thread,
    ThreadComment,
)
from github_orchestrator.github.fake import GhError
from github_orchestrator.mentions import MentionsInbox, PrNow, StartUnread
from github_orchestrator.settings.fake import RepoEntry, fake_settings
from tests.change_detection.support import POLLED_AT
from tests.conversation.support import REPO, THE_PR, WORKTREE, at, drain, world

START = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
SEARCHED = "2026-10-23T09:00:00Z"


def _issue(key, comment_id, author, body, created_at):
    return Thread(key=key, kind=CommentKind.ISSUE, comments=(
        ThreadComment(id=comment_id, author=author, body=body, created_at=created_at),))


def _here(tmp_path, *repos, clock=None):
    settings = fake_settings(tmp_path, repos=tuple(
        RepoEntry(Repo.parse(repo), str(tmp_path)) for repo in (REPO, *repos)))
    settings.config_path.write_text(f'mentions_start = "{START.isoformat()}"\n')
    return world(settings, clock=clock or at(SEARCHED))


def _searched(here):
    here.container.get(MentionsInbox).search_if_due()
    return json.loads((here.settings.data_dir / "mentions.json").read_text())


def _mentioned(here, *threads, status="OPEN", body="", created_at=None,
               updated_at="2026-10-22T10:00:00Z"):
    state = PullRequestState(author="anna", branch="widgets", body=body)
    here.github.add_pr(THE_PR, state, status=status, mentioned=True,
                       updated_at=updated_at, created_at=created_at)
    for thread in threads:
        here.github.add_thread(THE_PR, thread)
    return _carded(here, state)


def _carded(here, state):
    here.change_detection.advance(THE_PR, Poll(state, POLLED_AT), set())
    here.working_copies.place(THE_PR, WORKTREE)
    manager = here.conversation_managers.of(THE_PR)
    polled = manager.poll(state)
    polled.commit()
    manager.absorb(polled.activity)
    return manager


def _listed_threads(here):
    return [listed["thread"] for listed in _searched(here)["mentions"]]


def test_a_mention_resolved_on_the_board_leaves_and_a_deferred_one_stays(tmp_path):
    here = _here(tmp_path)
    manager = _mentioned(here,
                         _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"),
                         _issue("IC_2", 2, "anna", "@octocat pong", "2026-10-22T10:01:00Z"))
    with manager.editing("IC_1") as editable:
        editable.resolve()
    drain(manager)
    with manager.editing("IC_2") as editable:
        editable.place(ConversationState.DEFERRED)

    assert _listed_threads(here) == ["IC_2"]


def _review(key, *said):
    return Thread(key=key, kind=CommentKind.REVIEW, path="f", line=1, comments=tuple(
        ThreadComment(id=comment_id, author="anna", body=body, created_at=created_at)
        for comment_id, body, created_at in said))


def test_a_new_mention_in_a_thread_resolved_earlier_counts_again(tmp_path):
    here = _here(tmp_path)
    manager = _mentioned(here, _review("PRRT_1", (1, "@octocat ping", "2026-10-22T10:00:00Z")))
    with manager.editing("PRRT_1") as editable:
        editable.resolve()
    drain(manager)
    here.github.prs[THE_PR].threads.clear()
    here.github.add_thread(THE_PR, _review("PRRT_1", (1, "@octocat ping", "2026-10-22T10:00:00Z"),
                                           (2, "@octocat again", "2026-10-23T10:00:00Z")))

    assert [listed["comment_id"] for listed in _searched(here)["mentions"]] == [2]


def test_a_mention_i_have_replied_to_leaves_though_its_card_is_still_open(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, Thread(key="PRRT_1", kind=CommentKind.REVIEW, path="f", line=1, comments=(
        ThreadComment(id=1, author="anna", body="@octocat wdyt?",
                      created_at="2026-10-22T10:00:00Z"),
        ThreadComment(id=2, author="octocat", body="agreed",
                      created_at="2026-10-22T10:05:00Z"))))

    assert _listed_threads(here) == []


def test_a_mention_made_before_the_start_is_cleared(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat old", "2026-10-21T08:59:59Z"),
               _issue("IC_2", 2, "anna", "@octocat new", "2026-10-21T09:00:00Z"))

    assert _listed_threads(here) == ["IC_2"]


def test_a_comment_edited_after_the_start_to_name_me_dates_from_the_edit(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, Thread(key="IC_1", kind=CommentKind.ISSUE, comments=(
        ThreadComment(id=1, author="anna", body="and @octocat", created_at="2026-10-20T10:00:00Z",
                      updated_at="2026-10-22T10:00:00Z"),)))

    assert [(listed["thread"], listed["at"]) for listed in _searched(here)["mentions"]] == [
        ("IC_1", "2026-10-22T10:00:00Z")]


def test_a_mention_in_the_pr_body_dates_from_when_the_pr_was_opened(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, body="cc @octocat", created_at="2026-10-22T08:00:00Z")

    assert [(listed["thread"], listed["at"]) for listed in _searched(here)["mentions"]] == [
        ("pr-body", "2026-10-22T08:00:00Z")]


def test_a_mention_in_the_body_of_a_pr_opened_before_the_start_is_cleared(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, body="cc @octocat", created_at="2026-10-20T08:00:00Z")

    assert _listed_threads(here) == []


def _start(here):
    return tomllib.loads(here.settings.config_path.read_text())["mentions_start"]


def test_a_search_finding_nothing_outstanding_moves_the_start_to_when_it_began(tmp_path):
    here = _here(tmp_path)
    manager = _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))
    with manager.editing("IC_1") as editable:
        editable.resolve()
    drain(manager)

    _searched(here)

    assert datetime.fromisoformat(_start(here)) == datetime.fromisoformat(SEARCHED)


def test_a_search_finding_a_mention_outstanding_keeps_the_start(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))

    _searched(here)

    assert datetime.fromisoformat(_start(here)) == START


def test_a_pr_github_says_mentions_me_that_names_another_login_keeps_the_start(tmp_path):
    here = _here(tmp_path)
    here.github.add_pr(THE_PR, PullRequestState(author="anna"), mentioned=True,
                       updated_at="2026-10-22T10:00:00Z")
    here.github.add_thread(THE_PR, _issue("IC_1", 1, "anna", "@octocat-renamed ping",
                                          "2026-10-22T10:00:00Z"))

    _searched(here)

    assert datetime.fromisoformat(_start(here)) == START


def test_a_repo_added_after_the_last_search_starts_cleared(tmp_path):
    here = _here(tmp_path, "acme/gadgets")
    (here.settings.data_dir / "mentions.json").write_text(json.dumps({
        "searched_at": "2026-10-22T09:00:00+00:00",
        "started": {"acme/gadgets": START.isoformat()}, "mentions": []}))
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))

    listed = _searched(here)

    assert listed["mentions"] == []
    assert listed["started"] == {"acme/gadgets": START.isoformat(),
                                 REPO: datetime.fromisoformat(SEARCHED).isoformat()}


def test_a_pr_whose_threads_will_not_read_leaves_the_last_list_and_the_start_alone(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))
    listed = here.settings.data_dir / "mentions.json"
    listed.write_text("the last list")

    def unreadable(pr):
        raise GhError("gh api graphql failed (exit 1): HTTP 502")

    here.github.threads = unreadable

    here.container.get(MentionsInbox).search_if_due()

    assert listed.read_text() == "the last list"
    assert datetime.fromisoformat(_start(here)) == START


def test_the_inbox_searches_again_only_once_half_an_hour_has_passed(tmp_path):
    now = [datetime.fromisoformat(SEARCHED)]
    here = _here(tmp_path, clock=lambda: now[0])
    here.github.repos.add(Repo.parse(REPO))
    _searched(here)
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-23T09:10:00Z"),
               updated_at="2026-10-23T09:10:00Z")

    now[0] += timedelta(minutes=29, seconds=59)
    early = _listed_threads(here)
    now[0] += timedelta(seconds=1)

    assert (early, _listed_threads(here)) == ([], ["IC_1"])


def test_an_inbox_whose_start_will_not_read_tries_again_the_next_cycle(tmp_path):
    here = _here(tmp_path)
    here.github.repos.add(Repo.parse(REPO))
    here.settings.config_path.write_text("mentions_start = 2026-10-21T09:00:00Z\n")
    with pytest.raises(StartUnread, match="mentions_start"):
        _searched(here)
    here.settings.config_path.write_text(f'mentions_start = "{START.isoformat()}"\n')

    assert _searched(here)["searched_at"] == datetime.fromisoformat(SEARCHED).isoformat()


def test_an_unanswered_mention_on_a_merged_pr_is_listed(tmp_path):
    here = _here(tmp_path)
    here.github.add_pr(THE_PR, PullRequestState(author="anna"), status="MERGED",
                       mentioned=True, updated_at="2026-10-22T10:00:00Z")
    here.github.add_thread(THE_PR, _issue("IC_1", 1, "anna", "@octocat ping",
                                          "2026-10-22T10:00:00Z"))

    here.container.get(MentionsInbox).search_if_due()

    assert here.container.get(MentionsList).listed() == MentionsListing(
        searched_at="2026-10-23T09:00:00+00:00",
        mentions=(ListedMention(pr=THE_PR, thread="IC_1", comment_id=1, kind="issue",
                                author="anna", at="2026-10-22T10:00:00Z", body="@octocat ping",
                                url="https://github.com/acme/widgets/pull/7#issuecomment-1",
                                on_board=False, building=False, ended=PrEnded.MERGED),))
    assert here.container.get(MentionsInbox).unbuilt() == []


def test_a_listed_mention_says_its_card_is_on_the_board(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))

    here.container.get(MentionsInbox).search_if_due()

    assert [mention.on_board for mention in here.container.get(MentionsList).listed().mentions] == [
        True]


def test_a_pr_body_mention_links_to_the_pr(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, body="cc @octocat", created_at="2026-10-22T08:00:00Z")

    here.container.get(MentionsInbox).search_if_due()

    assert [mention.url for mention in here.container.get(MentionsList).listed().mentions] == [
        "https://github.com/acme/widgets/pull/7"]


def test_the_board_reads_no_mentions_before_the_first_search(tmp_path):
    assert _here(tmp_path).container.get(MentionsList).listed() == MentionsListing(
        searched_at=None, mentions=())


def test_a_mention_github_spells_in_another_case_is_listed_under_the_configured_repo(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))
    here.github.search = lambda repos, whose, updated_since=None: [Pr(Repo.parse("Acme/Widgets"), 7)]

    assert [(listed["repo"], listed["thread"]) for listed in _searched(here)["mentions"]] == [
        (REPO, "IC_1")]


def test_a_mention_in_a_repo_the_config_does_not_name_is_skipped(tmp_path):
    here = _here(tmp_path, "acme/gadgets")
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))
    here.github.search = lambda repos, whose, updated_since=None: [
        Pr(Repo.parse("acme/gadgets-renamed"), 3), THE_PR]

    assert _listed_threads(here) == ["IC_1"]


def _a_pr_whose_state_will_not_read(here):
    gone = Pr(Repo.parse(REPO), 99)
    real_state = here.github.pr_state

    def state(pr):
        if pr == gone:
            raise GhError("gh api graphql failed (exit 1): Could not resolve to a PullRequest")
        return real_state(pr)

    here.github.pr_state = state
    return gone


def test_a_pr_whose_state_will_not_read_is_skipped_and_the_others_listed(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))
    gone = _a_pr_whose_state_will_not_read(here)
    here.github.search = lambda repos, whose, updated_since=None: [gone, THE_PR]

    assert _listed_threads(here) == ["IC_1"]


def test_a_pr_whose_state_will_not_read_keeps_the_start(tmp_path):
    here = _here(tmp_path)
    gone = _a_pr_whose_state_will_not_read(here)
    here.github.search = lambda repos, whose, updated_since=None: [gone]

    assert _listed_threads(here) == []
    assert datetime.fromisoformat(_start(here)) == START


def test_a_listing_whose_start_has_no_time_zone_still_lists_the_mention(tmp_path):
    here = _here(tmp_path)
    (here.settings.data_dir / "mentions.json").write_text(json.dumps({
        "searched_at": "2026-10-22T09:00:00+00:00", "started": {REPO: "2026-10-21T09:00:00"},
        "mentions": []}))
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))

    assert _listed_threads(here) == ["IC_1"]


def _entry(**changed):
    return {"repo": REPO, "number": 7, "thread": "IC_1", "comment_id": 1, "kind": "issue",
            "author": "anna", "at": "2026-10-22T10:00:00Z", "body": "@octocat ping",
            "url": "https://github.com/acme/widgets/pull/7#issuecomment-1", "on_board": False,
            "building": False, **changed}


@pytest.mark.parametrize("on_disk", [
    "", '{"searched_at": "2026-10-23T09:00:00+00:00", "ment', "{not json", "[]",
    json.dumps({"mentions": []}), json.dumps({"searched_at": SEARCHED}),
    json.dumps({"searched_at": SEARCHED, "mentions": [{"repo": REPO}]}),
    json.dumps({"searched_at": SEARCHED, "mentions": ["IC_1"]}),
    json.dumps({"searched_at": SEARCHED, "mentions": [_entry(number="7")]}),
    json.dumps({"searched_at": SEARCHED, "mentions": [_entry(repo="widgets")]}),
])
def test_the_board_reads_a_damaged_listing_as_no_mentions_listed(tmp_path, on_disk):
    here = _here(tmp_path)
    (here.settings.data_dir / "mentions.json").write_text(on_disk)

    assert here.container.get(MentionsList).listed() == NO_MENTIONS_LISTED


def test_the_board_reads_a_folder_where_the_listing_belongs_as_no_mentions_listed(tmp_path):
    here = _here(tmp_path)
    (here.settings.data_dir / "mentions.json").mkdir()

    assert here.container.get(MentionsList).listed() == NO_MENTIONS_LISTED


def test_a_listing_whose_started_is_not_a_table_starts_afresh(tmp_path):
    here = _here(tmp_path)
    (here.settings.data_dir / "mentions.json").write_text(json.dumps({
        "searched_at": "2026-10-22T09:00:00+00:00", "started": [REPO], "mentions": []}))
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))

    assert _listed_threads(here) == ["IC_1"]


def test_the_first_search_writes_its_listing_where_no_data_folder_is_yet(tmp_path):
    settings = replace(fake_settings(tmp_path / "data", repos=(RepoEntry(Repo.parse(REPO),
                                                                         str(tmp_path)),)),
                       config_path=tmp_path / "config.toml")
    settings.config_path.write_text(f'mentions_start = "{START.isoformat()}"\n')
    here = world(settings, clock=at(SEARCHED))
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))
    shutil.rmtree(settings.data_dir, ignore_errors=True)

    assert _listed_threads(here) == ["IC_1"]


def _cardless(here, status="OPEN"):
    here.github.add_pr(THE_PR, PullRequestState(author="anna"), status=status, mentioned=True,
                       updated_at="2026-10-22T10:00:00Z")
    here.github.add_thread(THE_PR, _issue("IC_1", 1, "anna", "@octocat ping",
                                          "2026-10-22T10:00:00Z"))


def _cards(here):
    return [(mention.on_board, mention.building)
            for mention in here.container.get(MentionsList).listed().mentions]


def test_a_mention_on_an_open_pr_with_no_card_is_listed_while_its_card_is_built(tmp_path):
    here = _here(tmp_path)
    _cardless(here)
    inbox = here.container.get(MentionsInbox)

    inbox.search_if_due()

    assert (_cards(here), inbox.unbuilt()) == ([(False, True)], [THE_PR])


def _searched_again(here, now, after):
    now[0] += after
    here.container.get(MentionsInbox).search_if_due()


def test_a_card_still_short_of_two_hours_in_the_building_is_still_being_built(tmp_path):
    now = [datetime.fromisoformat(SEARCHED)]
    here = _here(tmp_path, clock=lambda: now[0])
    _cardless(here)
    here.container.get(MentionsInbox).search_if_due()

    _searched_again(here, now, timedelta(hours=1, minutes=59))

    assert _cards(here) == [(False, True)]


def test_a_card_that_has_not_appeared_two_hours_on_is_said_never_to_and_stays_listed(tmp_path):
    now = [datetime.fromisoformat(SEARCHED)]
    here = _here(tmp_path, clock=lambda: now[0])
    _cardless(here)
    inbox = here.container.get(MentionsInbox)
    inbox.search_if_due()
    _searched_again(here, now, timedelta(hours=1))

    _searched_again(here, now, timedelta(hours=1))

    assert (_cards(here), inbox.unbuilt()) == ([(False, False)], [])


def test_a_card_that_appears_makes_the_mention_open_on_the_board(tmp_path):
    now = [datetime.fromisoformat(SEARCHED)]
    here = _here(tmp_path, clock=lambda: now[0])
    _cardless(here)
    here.container.get(MentionsInbox).search_if_due()
    drain(_carded(here, PullRequestState(author="anna")))

    _searched_again(here, now, timedelta(minutes=30))

    assert _cards(here) == [(True, False)]


def test_a_pr_whose_openness_will_not_read_keeps_its_mention_listed_and_its_card_building(
        tmp_path, caplog):
    here = _here(tmp_path)
    _cardless(here)

    def unreadable(pr):
        raise GhError("gh api graphql failed (exit 1): HTTP 502")

    here.github.relevance = unreadable
    here.container.get(MentionsInbox).search_if_due()

    assert _cards(here) == [(False, True)]
    assert "HTTP 502" in caplog.text


def _dismissed(here, comment_id):
    here.container.get(MentionsList).dismiss(THE_PR, comment_id)


def _listed_now(here):
    return [mention.thread for mention in here.container.get(MentionsList).listed().mentions]


def test_a_dismissed_mention_leaves_the_list_before_the_next_search(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"),
               _issue("IC_2", 2, "anna", "@octocat pong", "2026-10-22T10:01:00Z"))
    here.container.get(MentionsInbox).search_if_due()

    _dismissed(here, 1)

    assert _listed_now(here) == ["IC_2"]


def test_a_dismissed_mention_stays_gone_after_the_next_search(tmp_path):
    now = [datetime.fromisoformat(SEARCHED)]
    here = _here(tmp_path, clock=lambda: now[0])
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"),
               _issue("IC_2", 2, "anna", "@octocat pong", "2026-10-22T10:01:00Z"))
    here.container.get(MentionsInbox).search_if_due()
    _dismissed(here, 1)

    _searched_again(here, now, timedelta(minutes=30))

    assert [listed["thread"] for listed in json.loads(
        (here.settings.data_dir / "mentions.json").read_text())["mentions"]] == ["IC_2"]


def test_a_search_whose_only_mentions_are_dismissed_moves_the_start(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))
    _dismissed(here, 1)

    _searched(here)

    assert datetime.fromisoformat(_start(here)) == datetime.fromisoformat(SEARCHED)


def test_a_dismissed_pr_body_mention_leaves_the_list(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"),
               body="cc @octocat", created_at="2026-10-22T08:00:00Z")
    here.container.get(MentionsInbox).search_if_due()

    _dismissed(here, None)

    assert _listed_now(here) == ["IC_1"]


def test_dismissing_a_comment_on_one_pr_leaves_the_same_id_on_another_listed(tmp_path):
    here = _here(tmp_path)
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))
    here.container.get(MentionsInbox).search_if_due()

    here.container.get(MentionsList).dismiss(Pr(Repo.parse(REPO), 8), 1)

    assert _listed_now(here) == ["IC_1"]


def _deferred_now(here):
    return [mention.deferred for mention in here.container.get(MentionsList).listed().mentions]


def _defer(here, deferral):
    here.container.get(MentionsList).defer(THE_PR, 1, deferral)


AN_HOUR_ON = MentionDeferral(deferred_at=SEARCHED, until_at="2026-10-23T10:00:00Z", until_pr=None)
OPEN_PR = PrNow(head_sha="aaa", approved=False, last_event_at=None, closed=False, merged=False)


def _one_mention(here):
    _mentioned(here, _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z"))
    here.container.get(MentionsInbox).search_if_due()


def _until(state):
    return MentionDeferral(deferred_at=SEARCHED, until_at=None,
                           until_pr=DeferredUntilPr(pr=THE_PR, state=state))


def _settled(here, prs=None):
    here.container.get(MentionsInbox).settle_deferrals({THE_PR: OPEN_PR} if prs is None else prs)


def test_a_deferred_mention_stays_listed_with_its_deferral(tmp_path):
    here = _here(tmp_path)
    _one_mention(here)

    _defer(here, AN_HOUR_ON)

    assert _deferred_now(here) == [AN_HOUR_ON]


def test_a_deferral_for_a_time_lapses_once_its_time_comes(tmp_path):
    now = [datetime.fromisoformat(SEARCHED)]
    here = _here(tmp_path, clock=lambda: now[0])
    _one_mention(here)
    _defer(here, AN_HOUR_ON)

    now[0] += timedelta(hours=1)

    assert _deferred_now(here) == [None]


def test_stopping_a_deferral_by_hand_counts_the_mention_again(tmp_path):
    here = _here(tmp_path)
    _one_mention(here)
    _defer(here, AN_HOUR_ON)

    here.container.get(MentionsList).stop_deferring(THE_PR, 1)

    assert _deferred_now(here) == [None]


def test_a_deferral_stays_after_the_next_search(tmp_path):
    now = [datetime.fromisoformat(SEARCHED)]
    here = _here(tmp_path, clock=lambda: now[0])
    _one_mention(here)
    _defer(here, replace(AN_HOUR_ON, until_at="2026-10-24T09:00:00Z"))

    _searched_again(here, now, timedelta(minutes=30))

    assert [deferral is not None for deferral in _deferred_now(here)] == [True]


def test_a_new_comment_in_the_mentioned_thread_ends_its_deferral(tmp_path):
    here = _here(tmp_path)
    _one_mention(here)
    _defer(here, _until(PrMilestone.MERGED))
    here.github.prs[THE_PR].threads.clear()
    here.github.add_thread(THE_PR, Thread(key="IC_1", kind=CommentKind.ISSUE, comments=(
        ThreadComment(id=1, author="anna", body="@octocat ping",
                      created_at="2026-10-22T10:00:00Z"),
        ThreadComment(id=3, author="bob", body="any news?", created_at="2026-10-23T09:30:00Z"))))
    _carded(here, PullRequestState(author="anna", branch="widgets"))

    _settled(here)

    assert _deferred_now(here) == [None]


def test_a_deferral_holds_while_nothing_it_waits_for_has_happened(tmp_path):
    here = _here(tmp_path)
    _one_mention(here)
    _defer(here, _until(PrMilestone.APPROVED))

    _settled(here)

    assert _deferred_now(here) == [_until(PrMilestone.APPROVED)]


def test_a_deferral_until_approved_ends_when_the_watcher_sees_the_approval(tmp_path):
    here = _here(tmp_path)
    _one_mention(here)
    _defer(here, _until(PrMilestone.APPROVED))

    _settled(here, {THE_PR: replace(OPEN_PR, approved=True)})

    assert _deferred_now(here) == [None]


def test_a_deferral_until_a_new_commit_ends_once_the_head_moves_after_it_was_seen(tmp_path):
    here = _here(tmp_path)
    _one_mention(here)
    _defer(here, _until(PrMilestone.NEW_COMMIT))
    _settled(here)

    _settled(here, {THE_PR: replace(OPEN_PR, head_sha="bbb")})

    assert _deferred_now(here) == [None]


def test_a_deferral_until_any_activity_ends_on_a_new_comment_anywhere_on_the_pr(tmp_path):
    here = _here(tmp_path)
    ping = _issue("IC_1", 1, "anna", "@octocat ping", "2026-10-22T10:00:00Z")
    _mentioned(here, ping, _review("PRRT_2", (2, "@octocat pong", "2026-10-22T10:01:00Z")))
    here.container.get(MentionsInbox).search_if_due()
    _defer(here, _until(PrMilestone.ANY_ACTIVITY))
    here.github.prs[THE_PR].threads.clear()
    here.github.add_thread(THE_PR, ping)
    here.github.add_thread(THE_PR, _review("PRRT_2", (2, "@octocat pong", "2026-10-22T10:01:00Z"),
                                           (3, "bump", "2026-10-23T09:30:00Z")))
    _carded(here, PullRequestState(author="anna", branch="widgets"))

    _settled(here)

    assert _deferred_now(here)[0] is None


@pytest.mark.parametrize(("state", "polled"), [
    (PrMilestone.APPROVED, OPEN_PR),
    (PrMilestone.NEW_COMMIT, replace(OPEN_PR, head_sha="bbb")),
    (PrMilestone.MERGED, OPEN_PR),
    (PrMilestone.CLOSED, OPEN_PR),
    (PrMilestone.ANY_ACTIVITY, replace(OPEN_PR, last_event_at="2026-10-23T08:00:00Z")),
    (PrMilestone.NEEDS_YOU, replace(OPEN_PR, approved=True, head_sha="bbb",
                                    last_event_at="2026-10-23T10:00:00Z")),
], ids=lambda value: getattr(value, "value", ""))
def test_a_deferral_holds_on_what_it_does_not_wait_for(tmp_path, state, polled):
    here = _here(tmp_path)
    _one_mention(here)
    _defer(here, _until(state))

    _settled(here, {THE_PR: polled})

    assert _deferred_now(here)[0] is not None


CLOSED_UNMERGED = replace(OPEN_PR, closed=True, merged=False)
MERGED_PR = replace(OPEN_PR, closed=True, merged=True)


@pytest.mark.parametrize(("state", "polled"), [
    (PrMilestone.CLOSED, CLOSED_UNMERGED),
    (PrMilestone.ANY_ACTIVITY, CLOSED_UNMERGED),
    (PrMilestone.MERGED, MERGED_PR),
    (PrMilestone.ANY_ACTIVITY, MERGED_PR),
], ids=["closed-on-close", "activity-on-close", "merged-on-merge", "activity-on-merge"])
def test_a_deferral_ends_when_its_pr_ends_the_way_it_waits_for(tmp_path, state, polled):
    here = _here(tmp_path)
    _one_mention(here)
    _defer(here, _until(state))

    _settled(here, {THE_PR: polled})

    assert _deferred_now(here) == [None]


@pytest.mark.parametrize(("state", "polled"), [
    (PrMilestone.MERGED, CLOSED_UNMERGED),
    (PrMilestone.APPROVED, CLOSED_UNMERGED),
    (PrMilestone.NEW_COMMIT, CLOSED_UNMERGED),
    (PrMilestone.NEEDS_YOU, CLOSED_UNMERGED),
    (PrMilestone.CLOSED, MERGED_PR),
], ids=["merged-on-close", "approved-on-close", "commit-on-close", "needs-you-on-close",
        "closed-on-merge"])
def test_a_deferral_holds_when_its_pr_ends_another_way(tmp_path, state, polled):
    here = _here(tmp_path)
    _one_mention(here)
    _defer(here, _until(state))

    _settled(here, {THE_PR: polled})

    assert _deferred_now(here)[0] is not None


def test_a_deferral_until_any_activity_ends_on_an_event_the_watcher_saw_after_it(tmp_path):
    here = _here(tmp_path)
    _one_mention(here)
    _defer(here, _until(PrMilestone.ANY_ACTIVITY))

    _settled(here, {THE_PR: replace(OPEN_PR, last_event_at="2026-10-23T09:05:00Z")})

    assert _deferred_now(here) == [None]


def test_a_deferral_on_a_pr_the_watcher_no_longer_tracks_holds_until_stopped_by_hand(tmp_path):
    here = _here(tmp_path)
    _one_mention(here)
    _defer(here, _until(PrMilestone.MERGED))

    _settled(here, {})

    assert _deferred_now(here) == [_until(PrMilestone.MERGED)]


def test_a_deferral_until_a_new_commit_keeps_the_head_it_first_saw(tmp_path):
    here = _here(tmp_path)
    _one_mention(here)
    _defer(here, _until(PrMilestone.NEW_COMMIT))
    _settled(here)

    _settled(here)

    assert _deferred_now(here) == [replace(_until(PrMilestone.NEW_COMMIT), head_sha="aaa")]


def test_a_comment_from_before_the_deferral_leaves_it_held(tmp_path):
    here = _here(tmp_path)
    _one_mention(here)
    _defer(here, AN_HOUR_ON)

    _settled(here)

    assert _deferred_now(here) == [AN_HOUR_ON]


def test_a_deferral_for_a_time_leaves_the_disk_once_it_lapses(tmp_path):
    now = [datetime.fromisoformat(SEARCHED)]
    here = _here(tmp_path, clock=lambda: now[0])
    _one_mention(here)
    _defer(here, AN_HOUR_ON)
    now[0] += timedelta(hours=1)

    _settled(here)

    assert json.loads((here.settings.data_dir / "mentions-deferred.json").read_text()) == {}


@pytest.mark.parametrize(("status", "ended"), [("OPEN", None), ("MERGED", PrEnded.MERGED),
                                               ("CLOSED", PrEnded.CLOSED)])
def test_a_listed_mention_says_whether_its_pr_merged_or_closed(tmp_path, status, ended):
    here = _here(tmp_path)
    _cardless(here, status=status)

    here.container.get(MentionsInbox).search_if_due()

    assert [mention.ended for mention in here.container.get(MentionsList).listed().mentions] == [
        ended]


def _opened_now(here):
    return here.container.get(MentionsList).listed().opened


def _open(here, status="MERGED"):
    _cardless(here, status=status)
    here.container.get(MentionsInbox).search_if_due()
    here.container.get(MentionsList).open(THE_PR, 1)


def test_a_mention_opened_in_context_holds_its_pr(tmp_path):
    here = _here(tmp_path)

    _open(here)

    assert here.container.get(MentionsInbox).opened() == [THE_PR]


def test_a_pr_that_ended_opened_for_a_mention_is_outside_the_wall(tmp_path):
    here = _here(tmp_path)

    _open(here)

    assert _opened_now(here) == (OpenedForMention(pr=THE_PR, comment_id=1, outside_wall=True),)


def test_an_open_pr_opened_for_a_mention_stays_inside_the_wall(tmp_path):
    here = _here(tmp_path)

    _open(here, status="OPEN")

    assert _opened_now(here) == (OpenedForMention(pr=THE_PR, comment_id=1, outside_wall=False),)


def test_a_pr_added_to_the_wall_is_inside_it(tmp_path):
    here = _here(tmp_path)
    _open(here)

    here.container.get(MentionsList).add_to_wall(THE_PR)

    assert _opened_now(here) == (OpenedForMention(pr=THE_PR, comment_id=1, outside_wall=False),)


def test_a_pr_opened_for_a_mention_is_let_go_once_none_of_its_mentions_is_outstanding(tmp_path):
    here = _here(tmp_path)
    _open(here)

    _dismissed(here, 1)

    assert (_opened_now(here), here.container.get(MentionsInbox).opened()) == ((), [])


def test_a_pr_added_to_the_wall_stays_held_once_its_mentions_are_gone(tmp_path):
    here = _here(tmp_path)
    _open(here)
    here.container.get(MentionsList).add_to_wall(THE_PR)

    _dismissed(here, 1)

    assert here.container.get(MentionsInbox).opened() == [THE_PR]


def test_adding_a_pr_no_mention_opened_to_the_wall_holds_nothing(tmp_path):
    here = _here(tmp_path)
    _cardless(here)
    here.container.get(MentionsInbox).search_if_due()

    here.container.get(MentionsList).add_to_wall(THE_PR)

    assert here.container.get(MentionsInbox).opened() == []


@pytest.mark.parametrize("on_disk", ["", "{not json", "[]", json.dumps({str(THE_PR): "x"}),
                                     json.dumps({"nonsense": {"comment_id": 1,
                                                              "on_wall": False}})])
def test_a_damaged_record_of_opened_prs_opens_none(tmp_path, on_disk):
    here = _here(tmp_path)
    _cardless(here)
    here.container.get(MentionsInbox).search_if_due()
    (here.settings.data_dir / "mentions-opened.json").write_text(on_disk)

    assert (_opened_now(here), here.container.get(MentionsInbox).opened()) == ((), [])
