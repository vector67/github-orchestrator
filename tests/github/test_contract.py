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
    FAKE_NOW,
    Check,
    FakeGitHub,
    GhError,
    PushEvent,
    Relevance,
    Review,
    ThreadAnchor,
)
from tests.builders import a_pr
from tests.github.support import real_github

REPO = "acme/widgets"
ME = "octocat"


@pytest.fixture(params=["fake", "gh"])
def world_and_github(request):
    world = FakeGitHub(account=ME)
    if request.param == "fake":
        return world, world
    return world, real_github(world)


@pytest.fixture
def world(world_and_github):
    return world_and_github[0]


@pytest.fixture
def github(world_and_github):
    return world_and_github[1]


def _state(**fields):
    defaults = {"title": "Widgets", "url": f"https://github.com/{REPO}/pull/7",
                "author": ME, "branch": "PROJ-1-widgets", "base_branch": "main",
                "head_sha": "a" * 40}
    return PullRequestState(**{**defaults, **fields})


def _comment(comment_id, author="reviewer", body="please fix", **fields):
    return ThreadComment(id=comment_id, author=author, body=body,
                         created_at="2026-09-01T10:00:00Z",
                         updated_at="2026-09-01T10:00:00Z", **fields)


def _review_thread(key="PRRT_one", *comments, **fields):
    defaults = {
        "anchor": ThreadAnchor(side=Side.AFTER, start_line=12, original_line=12,
                               original_commit="3f6f22a6" * 5),
        "path": "src/app.py", "line": 12, "is_resolved": False,
    }
    return Thread(key=key, kind=CommentKind.REVIEW,
                  comments=comments or (_comment(1),),
                  **{**defaults, **fields})


def _thread(github, key):
    return next((thread for thread in github.threads(a_pr(7, REPO))
                 if thread.key == key), None)


def test_my_open_prs_and_the_ones_i_am_asked_to_review_are_found_apart(world, github):
    world.add_pr(a_pr(1, REPO), _state(title="mine"))
    world.add_pr(a_pr(2, REPO), _state(title="theirs", author="anna"), review_requested=True)
    world.add_pr(a_pr(3, REPO), _state(title="closed"), status="CLOSED")

    assert github.search([Repo.parse(REPO)], "author") == [a_pr(1, REPO)]
    assert github.search([Repo.parse(REPO)], "review-requested") == [a_pr(2, REPO)]


def test_the_open_prs_that_mention_me_are_found_by_their_own_search(world, github):
    world.add_pr(a_pr(1, REPO), _state(title="mine"))
    world.add_pr(a_pr(2, REPO), _state(title="theirs", author="anna"), mentioned=True)
    world.add_pr(a_pr(3, REPO), _state(author="anna"), status="MERGED", mentioned=True)

    assert github.search([Repo.parse(REPO)], "mentions") == [a_pr(2, REPO)]


def test_a_search_kept_to_one_repo_finds_nothing_in_another(world, github):
    world.add_pr(a_pr(1, "acme/other"), _state())
    world.repos.add(Repo.parse(REPO))

    assert github.search([Repo.parse(REPO)], "author") == []


def test_one_search_finds_the_prs_of_every_repo_it_names(world, github):
    world.add_pr(a_pr(1, REPO), _state(title="widgets"))
    world.add_pr(a_pr(2, "acme/gadgets"), _state(title="gadgets"))
    world.add_pr(a_pr(3, "acme/other"), _state(title="other"))

    found = github.search([Repo.parse(REPO), Repo.parse("acme/gadgets")], "author")

    assert sorted(found) == [a_pr(2, "acme/gadgets"), a_pr(1, REPO)]


def test_a_search_naming_a_repo_github_cannot_see_still_finds_the_others(world, github):
    world.add_pr(a_pr(1, REPO), _state())

    assert github.search([Repo.parse(REPO), Repo.parse("acme/typo")], "author") == [
        a_pr(1, REPO)]


def test_a_search_in_a_repo_github_cannot_see_is_an_error(world, github):
    with pytest.raises(GhError, match="cannot be searched"):
        github.search([Repo.parse("acme/typo")], "author")


def test_a_prs_state_is_its_title_branches_head_and_mergeability(world, github):
    world.add_pr(a_pr(7, REPO), _state(body="Detailed reviewer: @anna", changed_files=3,
                                 additions=10, deletions=2, mergeable=True,
                                 mergeable_state="clean"))

    state = github.pr_state(a_pr(7, REPO))

    assert (state.title, state.author, state.branch, state.base_branch) == (
        "Widgets", ME, "PROJ-1-widgets", "main")
    assert state.head_sha == "a" * 40
    assert state.body == "Detailed reviewer: @anna"
    assert (state.changed_files, state.additions, state.deletions) == (3, 10, 2)
    assert (state.mergeable, state.mergeable_state) == (True, "clean")


def test_mergeability_github_has_not_worked_out_yet_is_unknown(world, github):
    world.add_pr(a_pr(7, REPO), _state())

    state = github.pr_state(a_pr(7, REPO))

    assert (state.mergeable, state.mergeable_state) == (False, "unknown")


def test_a_prs_checks_reviews_and_requested_reviewers_come_back(world, github):
    world.add_pr(a_pr(7, REPO), _state(
        checks=(Check("unit-tests", "completed", "failure",
                      "https://ci/1", "2 failed"),
                Check("lint", "in_progress")),
        reviews=(Review("anna", ReviewState.APPROVED, "2026-09-01T10:00:00Z", "b" * 40),),
        review_decision="APPROVED",
        pending_reviewers=("bob", "@platform"),
    ))

    state = github.pr_state(a_pr(7, REPO))

    assert state.checks == (
        Check("unit-tests", "completed", "failure", "https://ci/1", "2 failed"),
        Check("lint", "in_progress"),
    )
    assert state.reviews == (Review("anna", ReviewState.APPROVED, "2026-09-01T10:00:00Z",
                                    "b" * 40),)
    assert state.approved
    assert state.pending_reviewers == ("bob", "@platform")


def test_a_draft_has_not_been_made_ready_for_review(world, github):
    world.add_pr(a_pr(7, REPO), _state(draft=True, ready_for_review_at="2026-09-02T00:00:00Z"),
                 created_at="2026-09-01T00:00:00Z")

    state = github.pr_state(a_pr(7, REPO))

    assert state.draft is True
    assert state.ready_for_review_at is None


def test_a_pr_made_ready_says_when_and_one_opened_ready_says_when_it_opened(world, github):
    world.add_pr(a_pr(7, REPO), _state(ready_for_review_at="2026-09-02T00:00:00Z"),
                 created_at="2026-09-01T00:00:00Z")
    world.add_pr(a_pr(8, REPO), _state(), created_at="2026-09-01T00:00:00Z")

    assert github.pr_state(a_pr(7, REPO)).ready_for_review_at == "2026-09-02T00:00:00Z"
    assert github.pr_state(a_pr(8, REPO)).ready_for_review_at == "2026-09-01T00:00:00Z"


def test_pushes_are_told_for_a_pr_i_review_and_not_for_my_own(world, github):
    pushes = (PushEvent("committed", "2026-09-03T00:00:00Z"),
              PushEvent("head_ref_force_pushed", "2026-09-04T00:00:00Z"))
    world.add_pr(a_pr(7, REPO), _state(author="anna", push_events=pushes))
    world.add_pr(a_pr(8, REPO), _state(push_events=pushes))

    assert github.pr_state(a_pr(7, REPO)).push_events == pushes
    assert github.pr_state(a_pr(8, REPO)).push_events == ()


def test_a_pr_github_does_not_know_is_an_error(github):
    with pytest.raises(GhError):
        github.pr_state(a_pr(40, REPO))


def test_the_head_branch_of_a_pr(world, github):
    world.add_pr(a_pr(7, REPO), _state(branch="PROJ-7-head"))

    assert github.head_branch(a_pr(7, REPO)) == "PROJ-7-head"


def test_the_head_branch_of_a_pr_github_does_not_know_is_none(github):
    assert github.head_branch(a_pr(40, REPO)) is None


def test_a_closed_or_merged_pr_is_closed_and_an_open_one_is_not(world, github):
    world.add_pr(a_pr(1, REPO), _state())
    world.add_pr(a_pr(2, REPO), _state(), status="CLOSED")
    world.add_pr(a_pr(3, REPO), _state(), status="MERGED")

    assert [github.is_closed(a_pr(n, REPO)) for n in (1, 2, 3)] == [False, True, True]


def test_whether_a_pr_github_does_not_know_is_closed_is_unknown(github):
    assert github.is_closed(a_pr(40, REPO)) is None


def test_a_pr_i_close_is_closed(world, github):
    world.add_pr(a_pr(1, REPO), _state())

    assert github.close(a_pr(1, REPO)) is None
    assert github.is_closed(a_pr(1, REPO)) is True


def test_closing_a_pr_github_does_not_know_says_why(github):
    assert "Not Found" in (github.close(a_pr(40, REPO)) or "")


def test_relevance_says_how_the_pr_stands_and_whether_i_wrote_or_reviewed_it(world, github):
    world.add_pr(a_pr(1, REPO), _state(), status="MERGED")
    world.add_pr(a_pr(2, REPO), _state(author="anna"), viewer_reviewed=True)
    world.add_pr(a_pr(3, REPO), _state(author="anna"))

    assert github.relevance(a_pr(1, REPO)) == Relevance("MERGED", True, False)
    assert github.relevance(a_pr(2, REPO)) == Relevance("OPEN", False, True)
    assert github.relevance(a_pr(3, REPO)) == Relevance("OPEN", False, False)


def test_the_relevance_of_a_pr_github_does_not_know_is_nothing(github):
    assert github.relevance(a_pr(40, REPO)) is None


def test_prs_fetched_ahead_read_what_github_holds_and_afresh_once_read(world, github):
    world.add_pr(a_pr(7, REPO), _state(checks=(Check("tests", "completed", "success"),)))
    world.add_pr(a_pr(8, REPO), _state(author="anna", title="theirs"))
    world.add_thread(a_pr(7, REPO), _review_thread("PRRT_one"))

    github.prefetch([a_pr(7, REPO), a_pr(8, REPO)])
    first = (github.pr_state(a_pr(7, REPO)), github.threads(a_pr(7, REPO)),
             github.pr_state(a_pr(8, REPO)).title)
    world.add_thread(a_pr(7, REPO), _review_thread("PRRT_two"))
    world.prs[a_pr(8, REPO)].state = _state(author="anna", title="renamed")

    assert first[0].checks == (Check("tests", "completed", "success"),)
    assert [t.key for t in first[1]] == ["PRRT_one"]
    assert first[2] == "theirs"
    assert [t.key for t in github.threads(a_pr(7, REPO))] == ["PRRT_one", "PRRT_two"]
    assert github.pr_state(a_pr(8, REPO)).title == "renamed"


def test_every_kind_of_thread_comes_back_with_its_comments_and_anchor(world, github):
    world.add_pr(a_pr(7, REPO), _state())
    review = _review_thread(
        "PRRT_one",
        _comment(1, author="anna", author_name="Anna Example",
                 review_state=ReviewState.CHANGES_REQUESTED),
        _comment(2, author=ME, body="done", review_state=ReviewState.COMMENTED),
        is_resolved=True, resolved_by="anna",
    )
    issue = Thread(key="IC_one", kind=CommentKind.ISSUE,
                   comments=(_comment(900, body="general point"),))
    summary = Thread(key="PRR_one", kind=CommentKind.REVIEW_SUMMARY,
                     comments=(_comment(700, body="overall good"),),
                     state=ReviewState.APPROVED)
    for thread in (review, issue, summary):
        world.add_thread(a_pr(7, REPO), thread)

    threads = github.threads(a_pr(7, REPO))

    assert [t.key for t in threads] == ["PRRT_one", "IC_one", "PRR_one"]
    got_review, got_issue, got_summary = threads
    assert got_review == review
    assert got_issue.comments == issue.comments
    assert got_issue.path is None
    assert got_summary.state is ReviewState.APPROVED
    assert got_summary.comments[0].review_state is ReviewState.APPROVED
    assert got_summary.comments[0].body == "overall good"


def test_an_outdated_range_keeps_what_it_was_written_against(world, github):
    world.add_pr(a_pr(7, REPO), _state())
    thread = _review_thread(
        "PRRT_old", line=None,
        anchor=ThreadAnchor(is_outdated=True, side=Side.AFTER, start_line=None,
                            original_line=44, original_start_line=42,
                            original_commit="c" * 40))
    world.add_thread(a_pr(7, REPO), thread)

    assert github.threads(a_pr(7, REPO)) == [thread]


def test_a_comment_from_a_deleted_account_is_a_ghost(world, github):
    world.add_pr(a_pr(7, REPO), _state())
    world.add_thread(a_pr(7, REPO), _review_thread("PRRT_one", _comment(1, author="")))

    assert github.threads(a_pr(7, REPO))[0].comments[0].author == "ghost"


def test_a_review_with_nothing_said_opens_no_thread(world, github):
    world.add_pr(a_pr(7, REPO), _state())
    world.add_thread(a_pr(7, REPO), Thread(key="PRR_blank", kind=CommentKind.REVIEW_SUMMARY,
                                     comments=(_comment(700, body="   "),),
                                     state=ReviewState.APPROVED))

    assert github.threads(a_pr(7, REPO)) == []


def test_the_threads_of_a_pr_github_does_not_know_are_an_error(github):
    with pytest.raises(GhError):
        github.threads(a_pr(40, REPO))


def test_a_reply_lands_on_its_thread(world, github):
    world.add_pr(a_pr(7, REPO), _state())
    world.add_thread(a_pr(7, REPO), _review_thread("PRRT_one"))

    posted = github.reply_to_thread("PRRT_one", "on it")

    assert posted is not None
    assert (posted.author, posted.body) == (ME, "on it")
    assert _thread(github, "PRRT_one").comments[-1] == posted


def test_a_reply_opening_with_a_mention_is_posted_as_written(world, github):
    world.add_pr(a_pr(7, REPO), _state())
    world.add_thread(a_pr(7, REPO), _review_thread("PRRT_one"))

    github.reply_to_thread("PRRT_one", "@anna see the tables")
    posted = github.comment_on_pr(a_pr(7, REPO), "@anna\n\n> quoted\n\nagreed")

    assert _thread(github, "PRRT_one").comments[-1].body == "@anna see the tables"
    assert posted.comment.body == "@anna\n\n> quoted\n\nagreed"


def test_a_reply_to_a_thread_github_does_not_know_is_an_error(github):
    with pytest.raises(GhError):
        github.reply_to_thread("PRRT_gone", "on it")


def test_a_comment_on_the_pr_opens_a_thread_of_one_named_by_its_key(world, github):
    world.add_pr(a_pr(7, REPO), _state())

    posted = github.comment_on_pr(a_pr(7, REPO), "done")

    assert (posted.comment.author, posted.comment.body) == (ME, "done")
    assert posted.key is not None
    assert _thread(github, posted.key).kind == CommentKind.ISSUE
    assert _thread(github, posted.key).comments == (posted.comment,)


def test_a_thread_is_resolved_by_me_and_unresolved_again(world, github):
    world.add_pr(a_pr(7, REPO), _state())
    world.add_thread(a_pr(7, REPO), _review_thread("PRRT_one"))

    github.resolve_thread("PRRT_one")
    resolved = _thread(github, "PRRT_one")
    github.unresolve_thread("PRRT_one")
    unresolved = _thread(github, "PRRT_one")

    assert (resolved.is_resolved, resolved.resolved_by) == (True, ME)
    assert (unresolved.is_resolved, unresolved.resolved_by) == (False, None)


def test_resolving_a_thread_github_does_not_know_is_an_error(github):
    with pytest.raises(GhError):
        github.resolve_thread("PRRT_gone")
    with pytest.raises(GhError):
        github.unresolve_thread("PRRT_gone")


def test_a_thumbs_up_lands_on_the_comment_it_is_given(world, github):
    world.add_pr(a_pr(7, REPO), _state())
    world.add_thread(a_pr(7, REPO), _review_thread("PRRT_one", _comment(101), _comment(404)))

    github.react(Repo.parse(REPO), 404)

    assert world.reactions == {404: ["+1"]}


def test_a_thumbs_up_on_a_comment_github_does_not_know_is_an_error(world, github):
    world.add_pr(a_pr(7, REPO), _state())

    with pytest.raises(GhError):
        github.react(Repo.parse(REPO), 404)


def test_a_review_comment_opens_a_thread_on_its_line(world, github):
    world.add_pr(a_pr(7, REPO), _state())

    posted = github.post_review_comment(a_pr(7, REPO), "a" * 40,
                                        Location("src/app.py", 12, Side.AFTER), "please fix")

    assert (posted.author, posted.body) == (ME, "please fix")
    [thread] = github.threads(a_pr(7, REPO))
    assert (thread.kind, thread.path, thread.line) == (CommentKind.REVIEW, "src/app.py", 12)
    assert (thread.anchor.side, thread.anchor.start_line) == (Side.AFTER, 12)
    assert thread.comments == (posted,)


def test_a_review_comment_over_several_lines_starts_where_it_says(world, github):
    world.add_pr(a_pr(7, REPO), _state())

    github.post_review_comment(a_pr(7, REPO), "a" * 40,
                               Location("src/app.py", 12, Side.AFTER, 10, Side.BEFORE), "gone")

    [thread] = github.threads(a_pr(7, REPO))
    assert (thread.anchor.start_side, thread.anchor.start_line,
            thread.anchor.side, thread.line) == (Side.BEFORE, 10, Side.AFTER, 12)


def test_a_review_carries_every_comment_and_lists_them_by_path(world, github):
    world.add_pr(a_pr(7, REPO), _state(author="anna"))

    sent = github.post_review(a_pr(7, REPO), "a" * 40, Verdict.REQUEST_CHANGES, "a few things", [
        (Location("src/app.py", 12, Side.AFTER), "rename"),
        (Location("src/app.py", 30, Side.BEFORE, 28, Side.BEFORE), "gone"),
    ])

    assert sent.id is not None
    assert [(one.path, one.comment.body, one.comment.author) for one in sent.comments] == [
        ("src/app.py", "rename", ME), ("src/app.py", "gone", ME)]
    kinds = [(t.kind, t.comments[0].body) for t in github.threads(a_pr(7, REPO))]
    assert kinds == [(CommentKind.REVIEW, "rename"), (CommentKind.REVIEW, "gone"),
                     (CommentKind.REVIEW_SUMMARY, "a few things")]
    assert github.pr_state(a_pr(7, REPO)).reviews[-1].requests_changes


def test_a_review_goes_out_in_the_pending_review_github_already_holds(world, github):
    world.add_pr(a_pr(7, REPO), _state(author="anna"))
    pending = world.start_pending_review(a_pr(7, REPO), [
        (Location("src/app.py", 3, Side.AFTER), "drafted on github")])

    sent = github.post_review(a_pr(7, REPO), "a" * 40, Verdict.REQUEST_CHANGES, "a few things", [
        (Location("src/app.py", 30, Side.BEFORE, 28, Side.BEFORE), "@anna gone"),
    ])

    assert sent.id == pending
    assert [(one.path, one.comment.body) for one in sent.comments] == [
        ("src/app.py", "drafted on github"), ("src/app.py", "@anna gone")]
    threads = {t.comments[0].body: t for t in github.threads(a_pr(7, REPO))}
    assert threads["drafted on github"].comments[0].review_state == ReviewState.CHANGES_REQUESTED
    gone = threads["@anna gone"]
    assert (gone.anchor.start_side, gone.anchor.start_line, gone.anchor.side, gone.line) == (
        Side.BEFORE, 28, Side.BEFORE, 30)
    assert threads["a few things"].kind == CommentKind.REVIEW_SUMMARY
    assert github.pr_state(a_pr(7, REPO)).reviews[-1].requests_changes


def test_a_review_after_the_pending_one_went_out_is_a_new_review(world, github):
    world.add_pr(a_pr(7, REPO), _state(author="anna"))
    pending = world.start_pending_review(a_pr(7, REPO), [
        (Location("src/app.py", 3, Side.AFTER), "drafted on github")])
    github.post_review(a_pr(7, REPO), "a" * 40, Verdict.COMMENT, "first", [])

    sent = github.post_review(a_pr(7, REPO), "a" * 40, Verdict.COMMENT, "second", [
        (Location("src/app.py", 12, Side.AFTER), "rename")])

    assert sent.id != pending
    assert [one.comment.body for one in sent.comments] == ["rename"]


def test_an_approval_with_nothing_to_say_opens_no_summary(world, github):
    world.add_pr(a_pr(7, REPO), _state(author="anna"))

    sent = github.post_review(a_pr(7, REPO), "a" * 40, Verdict.APPROVE, None, [])

    assert sent.id is not None
    assert sent.comments == ()
    assert github.threads(a_pr(7, REPO)) == []
    assert github.pr_state(a_pr(7, REPO)).reviews[-1].approves


@pytest.mark.parametrize("kind,key", [
    (CommentKind.REVIEW, "PRRT_one"), (CommentKind.ISSUE, "IC_one"), (CommentKind.REVIEW_SUMMARY, "PRR_one"),
])
def test_a_deleted_comment_is_gone(world, github, kind, key):
    world.add_pr(a_pr(7, REPO), _state())
    world.add_thread(a_pr(7, REPO), Thread(key=key, kind=kind, comments=(_comment(55),),
                                     state=ReviewState.COMMENTED))

    assert github.comment_exists(a_pr(7, REPO), kind, 55) is True
    github.delete_comment(a_pr(7, REPO), kind, 55)

    assert github.comment_exists(a_pr(7, REPO), kind, 55) is False
    assert github.threads(a_pr(7, REPO)) == []


def test_deleting_a_comment_already_gone_is_done(world, github):
    world.add_pr(a_pr(7, REPO), _state())

    github.delete_comment(a_pr(7, REPO), CommentKind.REVIEW, 55)

    assert github.comment_exists(a_pr(7, REPO), CommentKind.REVIEW, 55) is False


def test_deleting_one_reply_keeps_the_rest_of_its_thread(world, github):
    world.add_pr(a_pr(7, REPO), _state())
    world.add_thread(a_pr(7, REPO), _review_thread("PRRT_one", _comment(1), _comment(2)))

    github.delete_comment(a_pr(7, REPO), CommentKind.REVIEW, 2)

    assert [c.id for c in _thread(github, "PRRT_one").comments] == [1]


def test_access_is_checked_for_the_account_and_repo_it_is_given(world, github):
    world.add_pr(a_pr(7, REPO), _state())
    world.tokens["anna"] = "gho_anna"

    assert github.check_access("anna", Repo.parse(REPO)) is None
    assert "gh auth login" in github.check_access("nobody", Repo.parse(REPO))
    assert "acme/typo" in github.check_access(ME, Repo.parse("acme/typo"))


def test_a_login_is_checked_for_the_account_it_is_given(world, github):
    world.tokens["anna"] = "gho_anna"

    assert github.check_login("anna") is None
    assert "gh auth login" in github.check_login("nobody")


def test_the_active_account_is_the_one_gh_is_logged_in_as(world, github):
    assert github.active_account() == ME


def test_a_token_s_scopes_are_listed_for_the_account_given(world, github):
    world.tokens["anna"] = "gho_anna"
    world.granted["anna"] = ("read:org", "repo")

    assert github.scopes("anna") == ("read:org", "repo")


def test_the_repos_an_account_lists_come_newest_push_first_with_what_it_may_do_there(
        world, github):
    world.listed = [Repo.parse("acme/gadgets"), Repo.parse(REPO), Repo.parse("octocat/spoon-knife")]
    world.read_only.add(Repo.parse("octocat/spoon-knife"))
    world.add_pr(a_pr(1, REPO), _state(title="mine"))
    world.add_pr(a_pr(2, "acme/gadgets"), _state(author="anna"), review_requested=True)
    world.add_pr(a_pr(3, "octocat/spoon-knife"), _state(author="anna"))

    listed = github.repos_of(ME)

    assert [(str(one.repo), one.can_push, one.has_my_prs, one.default_branch)
            for one in listed] == [("acme/gadgets", True, True, "main"),
                                   (REPO, True, True, "main"),
                                   ("octocat/spoon-knife", False, False, "main")]


def test_listing_repos_for_an_account_gh_holds_no_token_for_says_why(world, github):
    refused = github.repos_of("nobody")

    assert isinstance(refused, str) and "gh auth login" in refused


def test_a_repo_named_by_hand_is_looked_up_with_what_the_account_may_do_there(world, github):
    world.repos.add(Repo.parse("octocat/hello-world"))
    world.read_only.add(Repo.parse("octocat/hello-world"))

    found = github.repo_of(ME, Repo.parse("octocat/hello-world"))

    assert not isinstance(found, str)
    assert (str(found.repo), found.can_push, found.has_my_prs, found.default_branch) == (
        "octocat/hello-world", False, False, "main")


def test_a_repo_named_by_hand_that_the_account_cannot_see_says_so(world, github):
    refused = github.repo_of(ME, Repo.parse("acme/typo"))

    assert isinstance(refused, str) and "acme/typo" in refused


def test_a_repo_the_account_can_see_is_cloned_into_the_folder_given(world, github, tmp_path):
    world.repos.add(Repo.parse(REPO))

    assert github.clone(Repo.parse(REPO), tmp_path / "widgets") is None

    assert (tmp_path / "widgets").is_dir()


def test_a_repo_gh_cannot_reach_is_not_cloned_and_says_why(world, github, tmp_path):
    refused = github.clone(Repo.parse("acme/typo"), tmp_path / "typo")

    assert refused is not None and "acme/typo" in refused
    assert not (tmp_path / "typo").exists()


def test_what_i_post_is_stamped_with_when(world, github):
    world.add_pr(a_pr(7, REPO), _state())

    posted = github.comment_on_pr(a_pr(7, REPO), "done")

    assert posted.comment.created_at == posted.comment.updated_at == FAKE_NOW


@pytest.mark.parametrize("world_and_github", ["fake"], indirect=True)
def test_a_prs_page_its_commits_and_each_kind_of_comment_live_on_github_dot_com(github):
    pr = a_pr(7, REPO)

    assert github.url(pr) == f"https://github.com/{REPO}/pull/7"
    assert github.commit_url(pr.repo, "c" * 40) == f"https://github.com/{REPO}/commit/{'c' * 40}"
    assert [github.comment_url(pr, kind, 55) for kind in CommentKind] == [
        f"https://github.com/{REPO}/pull/7#discussion_r55",
        f"https://github.com/{REPO}/pull/7#issuecomment-55",
        f"https://github.com/{REPO}/pull/7#pullrequestreview-55",
    ]


@pytest.mark.parametrize("world_and_github", ["fake"], indirect=True)
def test_a_body_is_too_long_past_the_bytes_github_takes(github):
    assert github.too_long("é" * 32768) is None
    assert github.too_long("é" * 32768 + "x") == "GitHub takes at most 65536 bytes"


def test_github_takes_an_approval_on_its_own_and_nothing_else_without_words():
    assert Verdict.APPROVE.takes(None)
    assert not Verdict.REQUEST_CHANGES.takes("  ")
    assert not Verdict.COMMENT.takes(None)
    assert Verdict.COMMENT.takes("a few things")
