import logging

import pytest

from github_orchestrator.github import ThreadComment
from github_orchestrator.github.fake import GhError
from tests.builders import a_pr
from tests.github.scripted_gh import Failure, ScriptedGh
from tests.github.support import real_github

PAGES_ALLOWED = 5


def _pull(threads=None, issue_comments=None, reviews=None,
          threads_next=None, comments_next=None):
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "pageInfo": threads_next or {"hasNextPage": False, "endCursor": None},
                        "nodes": threads or [],
                    },
                    "comments": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": issue_comments or [],
                    },
                    "reviews": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": reviews or [],
                    },
                }
            }
        }
    }


def _thread(key="PRRT_one", comments=None, resolved=False, outdated=False,
            line=12, original_line=12, next_page=None, start_line=None,
            original_start_line=None, resolved_by=None, start_side="RIGHT"):
    return {
        "id": key,
        "isResolved": resolved,
        "resolvedBy": None if resolved_by is None else {"login": resolved_by},
        "isOutdated": outdated,
        "path": "src/app.py",
        "line": line,
        "startLine": line if start_line is None else start_line,
        "startDiffSide": start_side,
        "originalLine": original_line,
        "originalStartLine": original_start_line,
        "diffSide": "RIGHT",
        "subjectType": "LINE",
        "comments": {
            "pageInfo": next_page or {"hasNextPage": False, "endCursor": None},
            "nodes": comments or [_comment()],
        },
    }


def _author(login, name):
    if login is None:
        return None
    return {"login": login} if name is None else {"login": login, "name": name}


def _comment(database_id=1, author="reviewer", body="please fix",
             created="2026-09-01T10:00:00Z", name="Robin Reviewer",
             review_state="COMMENTED", start_line=None, original_start_line=None):
    return {
        "databaseId": database_id,
        "startLine": start_line,
        "originalStartLine": original_start_line,
        "author": _author(author, name),
        "body": body,
        "createdAt": created,
        "updatedAt": created,
        "originalCommit": {"oid": "3f6f22a66aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        "pullRequestReview": (None if review_state is None
                              else {"state": review_state}),
    }


def _threads_answering(*answers):
    return real_github(gh=ScriptedGh().answer("graphql", *answers)).threads(a_pr(5, "owner/name"))


def _budgeted(reply, budget):
    gh = ScriptedGh()
    count = []

    def answer(request):
        count.append(1)
        if len(count) > budget:
            raise AssertionError(f"the threads were asked for {len(count)} times; "
                                 f"it is not going to stop")
        return reply(len(count) - 1, request.variables)

    gh.always("graphql", answer)
    return gh


def test_a_comment_from_a_deleted_account_is_a_ghost_with_no_display_name():
    [thread] = _threads_answering(_pull(threads=[_thread(comments=[_comment(1, author=None)])]))

    assert (thread.comments[0].author, thread.comments[0].author_name) == ("ghost", "")


def test_a_single_line_thread_ignores_the_start_line_github_puts_on_the_thread():
    [thread] = _threads_answering(_pull(threads=[_thread(line=35, start_line=59, comments=[
        _comment(start_line=None, original_start_line=None)])]))

    assert (thread.anchor.start_line, thread.anchor.original_start_line) == (None, None)


def test_a_multi_line_thread_starts_where_its_comment_does():
    [thread] = _threads_answering(_pull(threads=[_thread(line=161, comments=[
        _comment(start_line=156, original_start_line=155)])]))

    assert (thread.anchor.start_line, thread.anchor.original_start_line) == (156, 155)


def test_an_author_that_is_no_user_has_no_display_name():
    [thread] = _threads_answering(_pull(threads=[_thread(comments=[
        _comment(1, author="dependabot", name=None)])]))

    assert (thread.comments[0].author, thread.comments[0].author_name) == ("dependabot", "")


def test_a_comment_with_no_body_and_no_edit_time_reads_as_empty_and_unedited():
    raw = {"databaseId": 5, "author": {"login": "reviewer"}, "body": None,
           "createdAt": "2026-04-20T10:00:00Z"}

    [thread] = _threads_answering(_pull(threads=[_thread(comments=[raw])]))

    assert thread.comments[0].body == ""
    assert thread.comments[0].updated_at == "2026-04-20T10:00:00Z"


def test_a_comment_that_belongs_to_no_review_names_no_review_state():
    [thread] = _threads_answering(_pull(issue_comments=[{
        "id": "IC_node", "databaseId": 900,
        "author": {"login": "anna", "name": "Anna Example"},
        "body": "general point", "createdAt": "2026-09-02T10:00:00Z",
        "updatedAt": "2026-09-02T10:00:00Z",
    }]))

    assert thread.comments[0].author_name == "Anna Example"
    assert thread.comments[0].review_state is None


def test_the_threads_on_the_next_page_are_asked_for_by_its_cursor():
    def pages(n, variables):
        if variables.get("threadCursor") == "CURSOR1":
            return _pull(threads=[_thread(key="PRRT_two")])
        return _pull(threads=[_thread(key="PRRT_one")],
                     threads_next={"hasNextPage": True, "endCursor": "CURSOR1"})

    github = real_github(gh=_budgeted(pages, budget=2))

    assert [t.key for t in github.threads(a_pr(5, "owner/name"))] == ["PRRT_one", "PRRT_two"]


def test_the_comments_on_a_threads_next_page_are_read_too():
    page = _pull(threads=[_thread(comments=[_comment(1)],
                                  next_page={"hasNextPage": True, "endCursor": "CCUR"})])
    more = {"data": {"node": {"comments": {
        "pageInfo": {"hasNextPage": False, "endCursor": None},
        "nodes": [_comment(2, author="author")],
    }}}}

    [thread] = _threads_answering(page, more)

    assert [c.id for c in thread.comments] == [1, 2]


def test_an_answer_carrying_errors_and_no_data_is_a_failed_fetch():
    with pytest.raises(GhError, match="rate limit"):
        _threads_answering({"data": None, "errors": [
            {"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]})


def test_a_notice_beside_a_page_it_could_read_is_logged_and_the_page_used(caplog):
    payload = _pull(threads=[_thread()])
    payload["errors"] = [{"type": "DEPRECATION", "message": "subjectType is deprecated"}]

    with caplog.at_level(logging.WARNING):
        threads = _threads_answering(payload)

    assert [t.key for t in threads] == ["PRRT_one"]
    assert "subjectType is deprecated" in caplog.text


def test_a_reason_github_answers_as_a_mapping_still_reaches_the_message():
    with pytest.raises(GhError, match="upstream connect error"):
        _threads_answering({"data": None, "errors": {"message": "upstream connect error"}})


@pytest.mark.parametrize("connection", ["reviewThreads"])
@pytest.mark.parametrize("broken", ["the-connection", "its-nodes"])
def test_a_connection_github_nulled_is_a_failed_fetch(connection, broken):
    payload = _pull(threads=[_thread()])
    pull = payload["data"]["repository"]["pullRequest"]
    if broken == "the-connection":
        pull[connection] = None
    else:
        pull[connection]["nodes"] = None

    with pytest.raises(GhError, match=connection):
        _threads_answering(payload)


@pytest.mark.parametrize("payload", [
    {"data": {"repository": {"pullRequest": None}}},
])
def test_a_pull_request_github_will_not_show_is_a_failure(payload):
    with pytest.raises(GhError, match="no pull request"):
        _threads_answering(payload)


def test_a_connection_that_never_runs_out_of_fresh_cursors_is_given_up_on(monkeypatch):
    monkeypatch.setattr("github_orchestrator.github._threads.MAX_PAGES", PAGES_ALLOWED)

    def always_more(n, _variables):
        return _pull(threads=[_thread(key=f"PRRT_{n}")],
                     threads_next={"hasNextPage": True, "endCursor": f"C{n}"})

    github = real_github(gh=_budgeted(always_more, budget=PAGES_ALLOWED + 1))

    with pytest.raises(GhError, match="pages"):
        github.threads(a_pr(5, "owner/name"))


def test_a_cursor_that_never_moves_is_refused():
    gh = _budgeted(lambda _n, _v: _pull(
        threads=[_thread()], threads_next={"hasNextPage": True, "endCursor": "SAME"}),
        budget=2)

    with pytest.raises(GhError, match="cursor it was given"):
        real_github(gh=gh).threads(a_pr(5, "owner/name"))


def test_a_page_that_claims_more_and_names_no_cursor_is_refused():
    gh = _budgeted(lambda _n, _v: _pull(
        threads=[_thread()], threads_next={"hasNextPage": True, "endCursor": None}),
        budget=1)

    with pytest.raises(GhError, match="named no cursor"):
        real_github(gh=gh).threads(a_pr(5, "owner/name"))


def test_an_empty_page_that_claims_more_is_refused():
    gh = _budgeted(lambda _n, _v: _pull(
        threads=[], threads_next={"hasNextPage": True, "endCursor": "NEXT"}),
        budget=1)

    with pytest.raises(GhError, match="empty page"):
        real_github(gh=gh).threads(a_pr(5, "owner/name"))


def test_a_threads_own_comment_pages_refuse_a_cursor_that_never_moves():
    def stuck_comments(n, _variables):
        if n == 0:
            return _pull(threads=[_thread(comments=[_comment(1)],
                                          next_page={"hasNextPage": True, "endCursor": "CC"})])
        return {"data": {"node": {"comments": {
            "pageInfo": {"hasNextPage": True, "endCursor": "CC"},
            "nodes": [_comment(2)],
        }}}}

    with pytest.raises(GhError, match="cursor it was given"):
        real_github(gh=_budgeted(stuck_comments, budget=2)).threads(a_pr(5, "owner/name"))


def test_a_comment_page_github_refuses_fails_the_whole_fetch():
    page = _pull(threads=[_thread(comments=[_comment(1)],
                                  next_page={"hasNextPage": True, "endCursor": "CCUR"})])
    refused = {"data": {"node": None},
               "errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]}

    with pytest.raises(GhError, match="rate limit"):
        _threads_answering(page, refused)


def test_a_cursor_gh_would_read_as_a_file_is_refused_before_gh_runs():
    gh = ScriptedGh().answer("graphql", _pull(
        threads=[_thread()],
        threads_next={"hasNextPage": True, "endCursor": "@/etc/passwd"}))

    with pytest.raises(ValueError, match="@"):
        real_github(gh=gh).threads(a_pr(5, "owner/name"))

    assert len(gh.calls) == 1


def test_the_reply_github_posted_is_read_back_whole():
    gh = ScriptedGh().answer("graphql", {"data": {"addPullRequestReviewThreadReply": {
        "comment": {"databaseId": 9001, "author": {"login": "orchestrator-bot"},
                    "body": "on it", "createdAt": "2026-09-07T12:00:00Z",
                    "updatedAt": "2026-09-07T12:00:00Z", "commit": {"oid": "f" * 40}}}}})

    posted = real_github(gh=gh).reply_to_thread("PRRT_one", "on it")

    assert posted == ThreadComment(id=9001, author="orchestrator-bot", body="on it",
                                   created_at="2026-09-07T12:00:00Z",
                                   updated_at="2026-09-07T12:00:00Z")


@pytest.mark.parametrize("write", ["reply_to_thread"])
def test_a_thread_write_github_refuses_reaches_the_caller(write):
    gh = ScriptedGh().answer("graphql", Failure("gh: viewer cannot resolve"))
    github = real_github(gh=gh)
    call = {"reply_to_thread": lambda: github.reply_to_thread("PRRT_one", "on it"),
            "resolve_thread": lambda: github.resolve_thread("PRRT_one"),
            "unresolve_thread": lambda: github.unresolve_thread("PRRT_one")}[write]

    with pytest.raises(GhError, match="viewer cannot resolve"):
        call()
