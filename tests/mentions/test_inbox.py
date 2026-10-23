import json
import tomllib
from datetime import UTC, datetime, timedelta

from github_orchestrator.change_detection import Poll
from github_orchestrator.conversation import ConversationState
from github_orchestrator.domain import Repo
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    Thread,
    ThreadComment,
)
from github_orchestrator.github.fake import GhError
from github_orchestrator.mentions import MentionsInbox
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


def test_an_unanswered_mention_on_a_merged_pr_is_listed(tmp_path):
    here = _here(tmp_path)
    here.github.add_pr(THE_PR, PullRequestState(author="anna"), status="MERGED",
                       mentioned=True, updated_at="2026-10-22T10:00:00Z")
    here.github.add_thread(THE_PR, _issue("IC_1", 1, "anna", "@octocat ping",
                                          "2026-10-22T10:00:00Z"))

    listed = _searched(here)

    assert listed["mentions"] == [{"repo": REPO, "number": THE_PR.number, "thread": "IC_1",
                                   "comment_id": 1, "kind": "issue", "author": "anna",
                                   "at": "2026-10-22T10:00:00Z", "body": "@octocat ping"}]
