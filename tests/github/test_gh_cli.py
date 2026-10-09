import json
import logging

import pytest

from github_orchestrator.domain import Location, Repo, Side
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    ReviewState,
    Thread,
    ThreadComment,
    Verdict,
)
from github_orchestrator.github.fake import (
    Check,
    FakeGitHub,
    GhError,
    PushEvent,
    Review,
)
from tests.builders import a_pr
from tests.github.scripted_gh import Failure, Raw, ScriptedGh, Timeout
from tests.github.support import real_github

REPO = "acme/widgets"
ME = "octocat"
PULL = f"GET repos/{REPO}/pulls/7"
REVIEWS = f"GET repos/{REPO}/pulls/7/reviews"
TIMELINE = f"GET repos/{REPO}/issues/7/timeline"
STATE = "graphql mergeStateStatus"


def _world(**fields):
    world = FakeGitHub(account=ME)
    state = {"author": "anna", "head_sha": "a" * 40, "branch": "PROJ-7", **fields}
    world.add_pr(a_pr(7, REPO), PullRequestState(**state), created_at="2026-09-01T00:00:00Z")
    return world


def _pull(*, runs=(), **fields):
    node = {"number": 7, "title": "Widgets", "url": "https://github.com/pr/7",
            "author": {"login": "anna", "__typename": "User"},
            "headRefName": "PROJ-7", "headRefOid": "a" * 40, "baseRefName": "main",
            "isDraft": False, "createdAt": "2026-09-01T00:00:00Z",
            "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
            "reviewRequests": {"nodes": []},
            "verdicts": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "readiness": {"nodes": []},
            "pushes": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            "commits": _head(list(runs)),
            **fields}
    return {"data": {"repository": {"pr7": node}}}


def _head(*suites):
    return {"nodes": [{"commit": {"checkSuites": {"nodes": [
        {"checkRuns": {"nodes": runs}} for runs in suites]}}}]}


def _run(name, conclusion="SUCCESS", **fields):
    return {"name": name, "status": "COMPLETED", "conclusion": conclusion,
            "url": f"https://ci/{name}", "summary": name, **fields}


def _state(answer):
    return real_github(gh=ScriptedGh().answer(STATE, answer)).pr_state(a_pr(7, REPO))


def test_a_token_gh_does_not_hold_names_the_account_and_the_way_out():
    github = real_github(gh=ScriptedGh(tokens={}))

    with pytest.raises(GhError) as excinfo:
        github.search([Repo.parse(REPO)], "author")

    message = str(excinfo.value)
    assert "no oauth token found" in message
    assert ME in message
    assert "gh auth login" in message
    assert "gh_account" in message


def test_every_call_goes_out_as_the_account_the_github_was_built_for():
    world = _world()
    world.tokens.clear()
    world.tokens["someone-else"] = "gho_else"

    assert real_github(world, account="someone-else").head_branch(a_pr(7, REPO)) == "PROJ-7"
    with pytest.raises(GhError, match="gh auth login"):
        real_github(world, account=ME).pr_state(a_pr(7, REPO))


def test_the_token_is_asked_of_gh_once_however_many_calls_follow():
    gh = ScriptedGh(_world())
    github = real_github(gh=gh)

    github.head_branch(a_pr(7, REPO))
    github.head_branch(a_pr(7, REPO))

    assert gh.token_requests == [ME]


def test_a_token_github_no_longer_takes_is_asked_of_gh_again():
    world = _world()
    github = real_github(world)
    github.head_branch(a_pr(7, REPO))
    world.tokens[ME] = "gho_rotated"

    assert github.head_branch(a_pr(7, REPO)) == "PROJ-7"


def test_a_prs_whole_state_is_one_question_to_github():
    gh = ScriptedGh(_world(push_events=(PushEvent("committed", "2026-09-03T00:00:00Z"),)))

    real_github(gh=gh).pr_state(a_pr(7, REPO))

    assert [call.route for call in gh.calls] == ["graphql"]


def _many(count):
    world = FakeGitHub(account=ME)
    for number in range(1, count + 1):
        world.add_pr(a_pr(number, REPO), PullRequestState(author="anna", branch=f"PROJ-{number}"))
        world.add_thread(a_pr(number, REPO), Thread(
            key=f"IC_{number}", kind=CommentKind.ISSUE,
            comments=(ThreadComment(id=number, author="anna", body="hi"),)))
    return world, [a_pr(number, REPO) for number in range(1, count + 1)]


def test_the_states_and_threads_of_prs_fetched_ahead_are_one_question_to_github():
    world, prs = _many(3)
    gh = ScriptedGh(world)
    github = real_github(gh=gh)

    github.prefetch(prs)
    read = [(github.pr_state(pr).branch, [t.key for t in github.threads(pr)]) for pr in prs]

    assert read == [("PROJ-1", ["IC_1"]), ("PROJ-2", ["IC_2"]), ("PROJ-3", ["IC_3"])]
    assert [call.route for call in gh.calls] == ["graphql"]


def test_prs_fetched_ahead_go_ten_to_a_question_to_stay_inside_githubs_node_limit():
    world, prs = _many(12)
    gh = ScriptedGh(world)
    github = real_github(gh=gh)

    github.prefetch(prs)
    branches = [github.pr_state(pr).branch for pr in prs]

    assert branches == [f"PROJ-{n}" for n in range(1, 13)]
    assert [call.query.count("pullRequest(number:") for call in gh.calls] == [10, 2]


def test_a_fetch_ahead_github_refuses_leaves_each_pr_to_be_read_on_its_own(caplog):
    world, prs = _many(2)
    gh = ScriptedGh(world).answer(STATE, Failure("gh: Something went wrong (HTTP 502)"))
    github = real_github(gh=gh)

    with caplog.at_level(logging.WARNING):
        github.prefetch(prs)

    assert github.pr_state(prs[0]).branch == "PROJ-1"
    assert [t.key for t in github.threads(prs[1])] == ["IC_2"]
    assert "HTTP 502" in caplog.text


def test_threads_a_fetch_ahead_could_not_hold_on_one_page_are_read_in_full():
    world, prs = _many(1)
    gh = ScriptedGh(world)

    def more_to_come(request):
        answer = gh.world_answers(request)
        answer["data"]["repository"]["pr1"]["comments"]["pageInfo"] = {
            "hasNextPage": True, "endCursor": "c1"}
        return answer

    gh.answer(STATE, more_to_come)
    github = real_github(gh=gh)

    github.prefetch(prs)

    assert [t.key for t in github.threads(prs[0])] == ["IC_1"]
    assert len(gh.calls) == 2


def test_a_refusal_carries_ghs_own_words_its_exit_code_and_the_command():
    gh = ScriptedGh().answer(STATE, Failure("gh: Not Found (HTTP 404)"))

    with pytest.raises(GhError) as excinfo:
        real_github(gh=gh).pr_state(a_pr(7, REPO))

    message = str(excinfo.value)
    assert "Not Found (HTTP 404)" in message
    assert "exit 1" in message
    assert "gh graphql (owner=acme, name=widgets)" in message


def test_a_refusal_with_nothing_on_stderr_still_reports_the_exit_code():
    gh = ScriptedGh().answer(STATE, Failure(""))

    with pytest.raises(GhError) as excinfo:
        real_github(gh=gh).pr_state(a_pr(7, REPO))

    message = str(excinfo.value)
    assert "exit 1" in message
    assert message.rstrip().endswith(">")


def test_a_failed_search_names_the_search_command():
    gh = ScriptedGh().answer("search prs", Failure(
        "gh: To use GitHub CLI in a GitHub Actions workflow, set the GH_TOKEN"))

    with pytest.raises(GhError, match="gh search prs"):
        real_github(gh=gh).search([Repo.parse("o/n")], "author")


def test_every_repo_is_searched_in_one_gh_call_with_no_cap_below_githubs():
    gh = ScriptedGh().answer("search prs", [])

    real_github(gh=gh).search([Repo.parse("acme/widgets"), Repo.parse("acme/gadgets")],
                              "author")

    [call] = [request for request in gh.calls if request.route == "search prs"]
    assert [word for word in call.argv if word.startswith("--repo=")] == [
        "--repo=acme/gadgets", "--repo=acme/widgets"]
    assert "--limit=1000" in call.argv


def test_a_search_result_with_no_repository_is_skipped():
    gh = ScriptedGh().answer("search prs", [
        {"number": 1, "repository": None, "title": "broken", "url": "https://example"},
        {"number": 2, "repository": {"nameWithOwner": "ok/repo"},
         "title": "fine", "url": "https://example/2"},
    ])

    assert [pr.number for pr in real_github(gh=gh).search([Repo.parse("ok/repo")], "author")] == [2]


def test_a_search_result_whose_repository_is_not_owner_and_name_is_skipped():
    gh = ScriptedGh().answer("search prs", [
        {"number": 1, "repository": {"nameWithOwner": "../escape"},
         "title": "broken", "url": "https://example"},
        {"number": 2, "repository": {"nameWithOwner": "ok/repo"},
         "title": "fine", "url": "https://example/2"},
    ])

    assert real_github(gh=gh).search([Repo.parse("ok/repo")], "author") == [
        a_pr(2, "ok/repo")]


def test_access_gh_refuses_repeats_why_and_names_the_repo_and_the_account():
    gh = ScriptedGh().answer("repo view", Failure("gh: Could not resolve to a Repository"))

    message = real_github(gh=gh).check_access(ME, Repo.parse("octocat/typo"))

    assert message is not None
    assert "Could not resolve to a Repository" in message
    assert "octocat/typo" in message
    assert ME in message


def test_a_mutation_github_answers_with_errors_is_a_failure():
    gh = ScriptedGh().answer("graphql", {
        "data": {"addPullRequestReviewThreadReply": None},
        "errors": [{"message": "Could not resolve to a node with the global id of 'PRRT_bogus'."}],
    })

    with pytest.raises(GhError, match="Could not resolve to a node"):
        real_github(gh=gh).reply_to_thread("PRRT_bogus", "on it")


def test_a_write_github_refuses_carries_its_reason():
    gh = ScriptedGh().answer(f"POST repos/{REPO}/pulls/7/comments",
                             Failure("gh: Validation Failed (HTTP 422)"))

    with pytest.raises(GhError, match="Validation Failed"):
        real_github(gh=gh).post_review_comment(a_pr(7, REPO), "a" * 40,
                                               Location("src/app.py", 12, Side.AFTER), "x")


def test_a_comment_github_has_already_lost_counts_as_deleted():
    gh = ScriptedGh().answer(f"DELETE repos/{REPO}/pulls/comments/101",
                             Failure("gh: Not Found (HTTP 404)"))

    assert real_github(gh=gh).delete_comment(a_pr(7, REPO), CommentKind.REVIEW, 101) is None


def test_a_delete_github_refuses_reaches_the_caller():
    gh = ScriptedGh().answer(f"DELETE repos/{REPO}/pulls/comments/101",
                             Failure("gh: Forbidden (HTTP 403)"))

    with pytest.raises(GhError, match="HTTP 403"):
        real_github(gh=gh).delete_comment(a_pr(7, REPO), CommentKind.REVIEW, 101)


@pytest.mark.parametrize("answer", [
    Failure("gh: error connecting to api.github.com"), Timeout(), Raw("<html>"),
])
def test_an_answer_github_could_not_give_leaves_the_comment_unknown(answer):
    gh = ScriptedGh().answer(f"GET repos/{REPO}/pulls/comments/11", answer)

    assert real_github(gh=gh).comment_exists(a_pr(7, REPO), CommentKind.REVIEW, 11) is None


def test_whether_a_comment_is_there_is_asked_of_github_every_time():
    world = _world()
    github = real_github(world)
    posted = github.post_review_comment(a_pr(7, REPO), "a" * 40,
                                        Location("src/app.py", 12, Side.AFTER), "x")

    first = github.comment_exists(a_pr(7, REPO), CommentKind.REVIEW, posted.id)
    world.delete_comment(a_pr(7, REPO), CommentKind.REVIEW, posted.id)

    assert (first, github.comment_exists(a_pr(7, REPO), CommentKind.REVIEW, posted.id)) == (True, False), (
        "the memo belongs to whoever asks, not to GitHub")


def test_reviews_past_one_page_are_read_from_every_page_gh_prints():
    gh = (ScriptedGh()
          .answer(STATE, _pull(verdicts={"pageInfo": {"hasNextPage": True}, "nodes": []}))
          .answer(REVIEWS, Raw(
              '[{"user": {"login": "anna"}, "state": "APPROVED"}]'
              '[{"user": {"login": "bob"}, "state": "APPROVED"}]')))

    assert [r.author for r in real_github(gh=gh).pr_state(a_pr(7, REPO)).reviews] == ["anna", "bob"]


def test_a_body_holding_bracket_newline_bracket_is_not_split_into_pages():
    body = "Here:\n```\n[1, 2]\n[3, 4]\n```"
    gh = (ScriptedGh()
          .answer("graphql states: PENDING",
                  {"data": {"repository": {"pullRequest": {"reviews": {"nodes": []}}}}})
          .answer(f"POST repos/{REPO}/pulls/7/reviews", {"id": 5})
          .answer(f"GET repos/{REPO}/pulls/7/reviews/5/comments",
                  Raw(json.dumps([{"id": 1, "path": "a.py", "body": body}]))))

    sent = real_github(gh=gh).post_review(
        a_pr(7, REPO), "a" * 40, Verdict.COMMENT, "see",
        [(Location("a.py", 1, Side.AFTER), body)])

    assert [listed.comment.body for listed in sent.comments] == [body]


def test_a_conflicting_pr_is_not_mergeable_and_dirty():
    state = _state(_pull(mergeable="CONFLICTING", mergeStateStatus="DIRTY"))

    assert (state.mergeable, state.mergeable_state) == (False, "dirty")


def test_a_rerun_check_is_reported_once_at_its_latest_run():
    older = _run("quality-checks", "FAILURE", databaseId=1, startedAt="2026-05-22T06:28:00Z",
                 completedAt="2026-05-22T06:45:00Z")
    newer = _run("quality-checks", "SUCCESS", databaseId=2, startedAt="2026-05-22T07:33:00Z",
                 completedAt="2026-05-22T07:50:00Z")
    for runs in ([older, newer], [newer, older]):
        checks = _state(_pull(runs=runs)).checks

        assert checks == (Check("quality-checks", "completed", "success",
                                "https://ci/quality-checks", "quality-checks"),)


def test_reruns_with_no_start_time_are_told_apart_by_finish_then_by_id():
    runs = [
        _run("unit-tests", "FAILURE", databaseId=10, completedAt="2026-05-22T06:00:00Z"),
        _run("unit-tests", "SUCCESS", databaseId=11, completedAt="2026-05-22T08:00:00Z"),
        _run("integration-tests", "FAILURE", databaseId=12),
        _run("integration-tests", "SUCCESS", databaseId=13),
    ]

    checks = {c.name: c.conclusion for c in _state(_pull(runs=runs)).checks}

    assert checks == {"unit-tests": "success", "integration-tests": "success"}


def test_reruns_github_cannot_order_keep_the_first():
    [check] = _state(_pull(runs=[_run("tests", "FAILURE"), _run("tests", "SUCCESS")])).checks

    assert check.conclusion == "failure"


def test_distinct_checks_all_come_back():
    runs = [_run("quality-checks", databaseId=1), _run("unit-tests", databaseId=2),
            _run("integration-tests", databaseId=3)]

    names = sorted(c.name for c in _state(_pull(runs=runs)).checks)

    assert names == ["integration-tests", "quality-checks", "unit-tests"]


def test_an_actions_check_links_to_its_job_and_another_apps_to_its_page_on_github():
    job = f"https://github.com/{REPO}/actions/runs/5/job/1"
    runs = [_run("tests", url=f"https://github.com/{REPO}/runs/1", detailsUrl=job),
            _run("sonar", url=f"https://github.com/{REPO}/runs/2",
                 detailsUrl="https://sonar.example/7")]

    links = {c.name: c.html_url for c in _state(_pull(runs=runs)).checks}

    assert links == {"tests": job, "sonar": f"https://github.com/{REPO}/runs/2"}


def test_the_runs_of_every_check_suite_on_the_head_come_back():
    head = _head([_run("tests"), _run("lint")], [], [_run("claude", "SKIPPED")])

    assert [c.name for c in _state(_pull(commits=head)).checks] == ["tests", "lint", "claude"]


def test_checks_come_newest_run_first_as_the_rest_api_lists_them():
    head = _head([_run("tests", databaseId=1)], [_run("lint", databaseId=3), _run("docs", databaseId=2)])

    assert [c.name for c in _state(_pull(commits=head)).checks] == ["lint", "docs", "tests"]


def test_a_head_commit_nothing_has_checked_has_no_checks():
    assert _state(_pull(commits=_head())).checks == ()


def test_a_pr_and_a_review_from_deleted_accounts_name_nobody():
    state = _state(_pull(author=None, verdicts={"pageInfo": {"hasNextPage": False}, "nodes": [
        {"author": None, "state": "APPROVED", "submittedAt": None, "commit": None}]}))

    assert state.author is None
    assert state.reviews == (Review(None, ReviewState.APPROVED),)


def test_a_bot_is_named_the_way_github_names_it_everywhere_else():
    bot = {"login": "dependabot", "__typename": "Bot"}

    state = _state(_pull(author=bot, verdicts={"pageInfo": {"hasNextPage": False}, "nodes": [
        {"author": bot, "state": "COMMENTED", "submittedAt": None, "commit": None}]}))

    assert (state.author, state.reviews[0].author) == ("dependabot[bot]", "dependabot[bot]")


def test_errors_github_sends_beside_the_pull_request_are_logged_and_the_state_kept(caplog):
    answer = {**_pull(), "errors": [{"message": "Resource not accessible by integration"}]}

    with caplog.at_level(logging.WARNING):
        state = _state(answer)

    assert state.branch == "PROJ-7"
    assert "Resource not accessible" in caplog.text


def test_a_requested_reviewer_that_is_neither_user_nor_team_is_dropped():
    state = _state(_pull(reviewRequests={"nodes": [
        {"requestedReviewer": {}},
        {"requestedReviewer": {"login": "alice"}},
        {"requestedReviewer": {"slug": "platform"}},
    ]}))

    assert state.pending_reviewers == ("alice", "@platform")


def test_pushes_past_one_page_are_read_from_the_timeline():
    gh = (ScriptedGh()
          .answer(STATE, _pull(pushes={"pageInfo": {"hasNextPage": True}, "nodes": []}))
          .answer(TIMELINE, [{"event": "committed", "at": "2026-09-03T00:00:00Z"}]))

    state = real_github(gh=gh).pr_state(a_pr(7, REPO))

    assert state.push_events == (PushEvent("committed", "2026-09-03T00:00:00Z"),)


def test_a_push_timeline_github_cannot_answer_still_says_when_it_was_ready():
    gh = (ScriptedGh()
          .answer(STATE, _pull(pushes={"pageInfo": {"hasNextPage": True}, "nodes": []},
                               readiness={"nodes": [{"createdAt": "2026-09-02T00:00:00Z"}]}))
          .answer(TIMELINE, Failure("gh: Server Error (HTTP 502)")))

    state = real_github(gh=gh).pr_state(a_pr(7, REPO))

    assert state.ready_for_review_at == "2026-09-02T00:00:00Z"
    assert state.push_events == ()


def test_pushes_are_dated_by_their_commit_or_by_the_force_push():
    state = _state(_pull(pushes={"pageInfo": {"hasNextPage": False}, "nodes": [
        {"__typename": "PullRequestCommit", "commit": {"committedDate": "2026-09-03T00:00:00Z"}},
        {"__typename": "PullRequestCommit", "commit": {"committedDate": None}},
        {"__typename": "HeadRefForcePushedEvent", "createdAt": "2026-09-04T00:00:00Z"},
    ]}))

    assert state.push_events == (PushEvent("committed", "2026-09-03T00:00:00Z"),
                                 PushEvent("committed", ""),
                                 PushEvent("head_ref_force_pushed", "2026-09-04T00:00:00Z"))


def test_a_pr_github_will_not_describe_is_logged_with_what_gh_said(caplog):
    gh = ScriptedGh().always(PULL, Failure("gh: Bad credentials (HTTP 401)"))

    with caplog.at_level(logging.WARNING):
        closed = real_github(gh=gh).is_closed(a_pr(7, REPO))

    assert closed is None
    assert f"{REPO}#7" in caplog.text
    assert "Bad credentials" in caplog.text


def test_login_and_access_without_gh_installed_say_gh_is_not_on_path():
    gh = ScriptedGh()
    gh.installed = False
    github = real_github(gh=gh)

    assert "gh is not on PATH" in github.check_login(ME)
    assert "gh is not on PATH" in github.check_access(ME, Repo.parse(REPO))
