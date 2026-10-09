import threading

from github_orchestrator.agent_runs.fake import CommentAsked, FakeAgentRuns, ThreadAsked
from github_orchestrator.conversation import (
    ConversationState,
    Denied,
    OperationKind,
    ReviewState,
)
from github_orchestrator.domain import Location, Sha, Side
from github_orchestrator.github import CommentKind, ThreadComment
from github_orchestrator.github import ReviewState as GitHubReviewState
from github_orchestrator.github.fake import FakeGitHub, ThreadAnchor
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.thread_records.fake import FakeThreadRecords
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.conversation.support import (
    PR,
    REPO,
    WORKTREE,
    at,
    diff_over,
    drain,
    hear,
    on_github,
    propose,
    repo_at,
    world,
)
from tests.disk_layout import thread_file
from tests.thread_records.support import disk_thread_records

THE_PR = a_pr(PR, REPO)

KEY = "PRRT_101"
COMMENT_ID = 101
BODY = "Please rename this helper."
ROOT_AT = "2026-08-28T10:00:00Z"
REPLY_AT = "2026-08-29T10:00:00Z"
PATH = "src/foo.py"
LINE = 3


class AnswersLater(FakeAgentRuns):
    def __init__(self) -> None:
        super().__init__(FakePrProcesses())
        self.pending = []

    def summarize_comment(self, key, path, line, body, done, *, chars):
        self.asked.append(CommentAsked(key, path, line, body, chars))
        self.pending.append(done)

    def summarize_thread(self, key, path, line, comments, done, *, chars):
        self.asked.append(ThreadAsked(key, path, line, tuple(comments), chars))
        self.pending.append(done)

    def answer_now(self, gist):
        for done in self.pending:
            done(gist)
        self.pending = []


def refuses_to_cut(*keys):
    copies = FakeWorkingCopies()
    for key in keys:
        copies.refuse_workspace(key)
    return copies


def cuts_together(barrier):
    copies = FakeWorkingCopies()
    copies.on_cut = barrier.wait
    return copies


class LagsBehind(FakeGitHub):
    listing = True

    def threads(self, pr):
        return [thread for thread in super().threads(pr)
                if self.listing or thread.comments[0].author != self.account]


def _world(settings, **fakes):
    here = world(settings, **fakes)
    repo_at(here.working_copies, WORKTREE)
    return here


def _pr_head(here):
    return here.working_copies.head_of(WORKTREE)


def root(**overrides) -> ThreadComment:
    return ThreadComment(**{"id": COMMENT_ID, "author": "reviewer", "body": BODY,
                            "created_at": ROOT_AT, "updated_at": ROOT_AT, **overrides})


def reply(body: str = "and this one too", **overrides) -> ThreadComment:
    return ThreadComment(**{"id": 202, "author": "reviewer", "body": body,
                            "created_at": REPLY_AT, **overrides})


def _on_github(github, key: str = KEY, comments=None, **fields) -> None:
    if THE_PR in github.prs:
        github.prs[THE_PR].threads = [one for one in github.prs[THE_PR].threads
                                      if one.key != key]
    fields.setdefault("anchor", ThreadAnchor(original_line=LINE, original_commit="cafe"))
    fields.setdefault("path", PATH)
    fields.setdefault("line", LINE)
    on_github(github, key, *(comments or (root(),)), pr=THE_PR, **fields)


def _replied(github, key: str = KEY, **fields) -> None:
    _on_github(github, key, (root(), reply()), **fields)


def _reply_edited(github, key: str = KEY, first=None, **fields) -> None:
    _on_github(github, key, (first or root(), reply("and this one, too")), **fields)


def _heard(here, threads, key: str = KEY, **fields):
    _on_github(here.github, key, **fields)
    return hear(threads)


def _checkout(here):
    return here.working_copies.thread_checkout(THE_PR, KEY)


def test_a_thread_with_no_record_is_opened_as_a_queued_fix(settings):
    here = _world(settings)
    threads = here.threads()

    [opened] = _heard(here, threads).created

    assert opened.key == KEY
    assert opened.standing is ConversationState.QUEUED
    assert opened.comment_id == COMMENT_ID
    assert opened.comment_type == "review"
    assert opened.author == "reviewer"
    assert opened.path == PATH
    assert opened.line == LINE
    assert opened.body == BODY
    assert opened.comment_created_at == ROOT_AT
    assert threads.get(KEY) == opened


def test_a_thread_carries_the_reviewer_the_review_and_the_range_to_the_record(settings):
    here = _world(settings)
    threads = here.threads()

    [opened] = _heard(here, threads, comments=(root(
        author="anna", author_name="Anna Example",
        review_state=GitHubReviewState.CHANGES_REQUESTED),),
        anchor=ThreadAnchor(start_line=8, original_line=9, original_start_line=5,
                            original_commit="cafe")).created

    assert opened.reviewer_name == "Anna Example"
    assert opened.review_state == ReviewState.CHANGES_REQUESTED
    assert (opened.start_line, opened.original_start_line) == (8, 5)
    assert opened.comments[0].author_name == "Anna Example"
    assert opened.comments[0].review_state == ReviewState.CHANGES_REQUESTED
    assert threads.get(KEY) == opened


def test_a_thread_keeps_the_side_of_the_diff_github_says_it_is_on(settings):
    here = _world(settings)

    [opened] = _heard(here, here.threads(), anchor=ThreadAnchor(
        side=Side.BEFORE, original_line=LINE, original_commit="cafe")).created

    assert opened.side is Side.BEFORE


def test_a_refresh_brings_the_side_back_in_step(settings):
    here = _world(settings)
    threads = here.threads()
    _replied(here.github, anchor=ThreadAnchor(side=Side.AFTER, original_line=LINE))
    hear(threads)
    _reply_edited(here.github, anchor=ThreadAnchor(side=Side.BEFORE, original_line=LINE))

    assert hear(threads).refreshed == (KEY,)

    assert threads.get(KEY).side is Side.BEFORE


def test_a_thread_with_no_record_keeps_the_node_id_it_came_from(settings):
    here = _world(settings)

    [opened] = _heard(here, here.threads()).created

    assert (opened.key, opened.github_node_id) == (KEY, KEY)


def _reviewing(settings, github=None):
    here = world(settings, github=github or FakeGitHub())
    here.github.add_pr(THE_PR)
    diff_over(here, "f")
    threads = here.threads()
    hear(threads)
    return here, threads


def _posted_draft(threads):
    drafted = threads.open_draft("rename it", Location(path="f", line=1, side=Side.AFTER))
    assert not isinstance(drafted, Denied), drafted
    with threads.editing(drafted.key) as editable:
        editable.post_now()
    drain(threads)
    return threads.get(drafted.key)


def _answered_on_github(github, key: str, *comments: ThreadComment) -> None:
    thread = github.thread(key)
    github.prs[THE_PR].threads = [one for one in github.prs[THE_PR].threads if one.key != key]
    on_github(github, key, *thread.comments, *comments, pr=THE_PR, path=thread.path,
              line=thread.line, anchor=thread.anchor, is_resolved=thread.is_resolved)


def _others_reply(comment_id: int = 202) -> ThreadComment:
    return reply(id=comment_id, author="anna", created_at=REPLY_AT)


def test_a_thread_finds_the_record_that_carries_its_node_id_under_another_key(settings):
    here, threads = _reviewing(settings)
    draft = _posted_draft(threads)
    _answered_on_github(here.github, draft.github_node_id, _others_reply())

    [opened] = hear(threads).created

    assert opened.key == draft.key
    assert threads.get(draft.github_node_id) is None


def test_a_refresh_finds_the_record_that_carries_the_node_id_too(settings):
    here, threads = _reviewing(settings)
    draft = _posted_draft(threads)
    hear(threads)
    here.github.resolve_thread(draft.github_node_id)

    assert hear(threads).refreshed == (draft.github_node_id,)

    assert threads.get(draft.key).github_resolved is True
    assert threads.get(draft.github_node_id) is None


def _posted_before_github_listed_it(settings):
    github = LagsBehind()
    github.listing = False
    here, threads = _reviewing(settings, github)
    draft = _posted_draft(threads)
    assert draft.github_node_id is None
    github.listing = True
    [node] = [thread.key for thread in github.threads(THE_PR)
              if thread.comments[0].id == draft.comment_id]
    return here, threads, draft, node


def test_a_thread_finds_the_posted_draft_github_had_not_listed_by_its_comment(settings):
    here, threads, draft, node = _posted_before_github_listed_it(settings)
    _answered_on_github(here.github, node, _others_reply())

    [opened] = hear(threads).created

    assert (opened.key, opened.github_node_id) == (draft.key, node)
    assert threads.get(node) is None


def test_a_refresh_finds_the_posted_draft_by_its_comment_too(settings):
    here, threads, draft, node = _posted_before_github_listed_it(settings)
    hear(threads)
    here.github.resolve_thread(node)

    hear(threads)

    assert threads.get(draft.key).github_node_id == node
    assert threads.get(node) is None


def test_a_comment_of_another_kind_with_the_same_id_is_another_thread(settings):
    here, threads, draft, _ = _posted_before_github_listed_it(settings)
    on_github(here.github, "IC_one", root(id=draft.comment_id), pr=THE_PR,
              kind=CommentKind.ISSUE, path=None, line=None)

    [opened] = hear(threads).created

    assert opened.key == "IC_one"
    assert threads.get(draft.key).github_node_id is None


def test_a_refresh_brings_the_reviewer_the_review_and_the_range_back_in_step(settings):
    here = _world(settings)
    threads = here.threads()
    _replied(here.github)
    hear(threads)
    _reply_edited(here.github, first=root(author="anna", author_name="Anna Example",
                                          review_state=GitHubReviewState.APPROVED),
                  anchor=ThreadAnchor(start_line=8, original_line=LINE,
                                      original_start_line=5, original_commit="cafe"))

    assert hear(threads).refreshed == (KEY,)

    stored = threads.get(KEY)
    assert stored.reviewer_name == "Anna Example"
    assert stored.review_state == ReviewState.APPROVED
    assert (stored.start_line, stored.original_start_line) == (8, 5)


def test_an_opened_thread_names_a_workspace_cut_off_the_pr_head(settings):
    here = _world(settings)
    threads = here.threads()

    [opened] = _heard(here, threads).created

    assert here.working_copies.holds_thread(THE_PR, KEY)
    assert here.working_copies.branches[f"orchestrator/thread/{THE_PR.number}/{KEY}"] == (
        _pr_head(here))
    assert opened.fix.base_sha == Sha(_pr_head(here))
    assert threads.get(KEY).fix.base_sha == opened.fix.base_sha


def test_a_thread_first_seen_resolved_is_created_done_with_no_fix(settings):
    agent_runs = AnswersLater()
    here = _world(settings, agent_runs=agent_runs)
    threads = here.threads()
    hear(threads)

    [opened] = _heard(here, threads, is_resolved=True).created

    assert opened.standing is ConversationState.DONE
    assert opened.github_resolved is True
    assert opened.fix.base_sha is None
    assert list(here.working_copies.branches) == ["main"]
    assert agent_runs.asked == []
    assert threads.get(KEY) == opened


def test_a_poll_carries_what_github_said_about_the_thread_and_when_it_said_it(settings):
    here = _world(settings, clock=at("2026-08-30T10:00:10Z"))
    threads = here.threads()
    _heard(here, threads)
    here.github.resolve_thread(KEY)

    hear(threads)

    stored = threads.get(KEY)
    assert stored.standing is ConversationState.DONE
    assert stored.github_resolved_at == "2026-08-30T10:00:05Z"


def _proposed(here, threads):
    _heard(here, threads)
    propose(here, threads, KEY, {"README": "renamed"})
    return threads.get(KEY)


def _landed(here, threads):
    _proposed(here, threads)
    with threads.editing(KEY) as editable:
        editable.approve()
    drain(threads)
    landed = threads.get(KEY)
    assert landed.standing is ConversationState.DONE
    return landed


def test_a_thread_that_already_has_a_record_is_reopened_not_opened_again(settings):
    here = _world(settings)
    threads = here.threads()
    proposed = _proposed(here, threads)
    _replied(here.github)

    [reopened] = hear(threads).created

    assert reopened.standing is ConversationState.QUEUED
    assert reopened.fix.attempts == 0
    assert not (reopened.fix.picked or reopened.fix.pushed or reopened.fix.answered)
    assert [c.body for c in reopened.comments] == [BODY, "and this one too"]
    assert reopened.fix.base_sha == proposed.fix.base_sha
    assert here.working_copies.head_of(_checkout(here)) == str(proposed.fix.thread_sha)


def test_a_comment_on_a_thread_that_has_landed_marks_it_and_queues_a_run(settings):
    here = _world(settings)
    threads = here.threads()
    landed = _landed(here, threads)
    _answered_on_github(here.github, KEY, _others_reply(303))

    [reopened] = hear(threads).created

    assert reopened.standing is ConversationState.QUEUED
    assert reopened.fix.run.kind is OperationKind.FIRST
    assert reopened.reopened is True
    assert reopened.fix.base_sha == landed.fix.landed_sha
    assert here.working_copies.head_of(_checkout(here)) == str(landed.fix.landed_sha)


def test_a_reopened_thread_whose_workspace_has_gone_is_given_a_new_one(settings):
    here = _world(settings)
    threads = here.threads()
    _proposed(here, threads)
    here.working_copies.lose_worktree(_checkout(here))
    _replied(here.github)

    [reopened] = hear(threads).created

    assert reopened.standing is ConversationState.QUEUED
    assert Sha(here.working_copies.head_of(_checkout(here))) == reopened.fix.base_sha


def test_a_reopen_is_summarised_over_the_whole_thread_an_open_over_the_root(settings):
    agent_runs = AnswersLater()
    here = _world(settings, agent_runs=agent_runs)
    threads = here.threads()
    _landed(here, threads)
    agent_runs.asked.clear()
    _answered_on_github(here.github, KEY, _others_reply(303))
    _on_github(here.github, "PRRT_2", (root(id=102),))

    hear(threads)

    posted = [comment for comment in here.github.thread(KEY).comments[1:-1]]
    assert sorted(agent_runs.asked, key=lambda asked: type(asked).__name__) == [
        CommentAsked("PRRT_2", PATH, LINE, BODY, 60),
        ThreadAsked(KEY, PATH, LINE,
                    (("reviewer", BODY),
                     *((comment.author, comment.body) for comment in posted),
                     ("anna", "and this one too")), 60),
    ]


def test_a_thread_whose_workspace_will_not_cut_does_not_stop_the_others(settings):
    here = _world(settings, working_copies=refuses_to_cut("PRRT_2"))
    threads = here.threads()
    for number in (1, 2, 3):
        _on_github(here.github, f"PRRT_{number}", (root(id=number),))

    opened = hear(threads).created

    assert [c.key for c in opened] == ["PRRT_1", "PRRT_3"]
    assert threads.get("PRRT_2") is None


def test_a_thread_whose_record_will_not_read_is_never_written_over(settings, tmp_path):
    threads_dir = tmp_path / "threads"
    here = _world(settings, thread_records=disk_thread_records(threads_dir))
    threads = here.threads()
    corrupt = thread_file(threads_dir, THE_PR, KEY)
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("[]")
    _replied(here.github)
    _on_github(here.github, "PRRT_2", (root(id=102),))

    opened = hear(threads).created

    assert [c.key for c in opened] == ["PRRT_2"]
    assert corrupt.read_text() == "[]"
    assert threads.get("PRRT_2") == opened[0]


def test_the_batch_is_stamped_in_thread_order_and_strictly_increasing(settings):
    here = _world(settings, clock=at("2026-09-07T12:00:00Z"))
    threads = here.threads()
    for number in (7, 4, 9):
        _on_github(here.github, f"PRRT_{number}", (root(id=number),))

    opened = hear(threads).created

    stamps = [c.created_at for c in opened]
    assert [c.key for c in opened] == ["PRRT_7", "PRRT_4", "PRRT_9"]
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == 3


def test_the_opens_run_in_parallel(settings):
    here = _world(settings, working_copies=cuts_together(threading.Barrier(2, timeout=5)))
    threads = here.threads()
    for number in (5, 3):
        _on_github(here.github, f"PRRT_{number}", (root(id=number),))

    opened = hear(threads).created

    assert [c.key for c in opened] == ["PRRT_5", "PRRT_3"]


def test_a_gist_for_a_conversation_that_has_gone_is_dropped(settings, tmp_path):
    agent_runs = AnswersLater()
    here = _world(settings, agent_runs=agent_runs,
                  thread_records=disk_thread_records(tmp_path / "threads"))
    threads = here.threads()
    _heard(here, threads)
    here.thread_records.forget(THE_PR)

    agent_runs.answer_now("what the reviewer wants")

    assert threads.get(KEY) is None


def test_a_refresh_moves_no_status_and_spends_no_attempt(settings):
    agent_runs = AnswersLater()
    here = _world(settings, agent_runs=agent_runs)
    threads = here.threads()
    landed = _landed(here, threads)
    agent_runs.asked.clear()
    here.github.unresolve_thread(KEY)

    assert hear(threads).refreshed == (KEY,)

    stored = threads.get(KEY)
    assert stored.standing is ConversationState.DONE
    assert stored.fix.attempts == landed.fix.attempts
    assert (stored.fix.picked, stored.fix.pushed, stored.fix.answered) == (
        landed.fix.picked, landed.fix.pushed, landed.fix.answered)
    assert agent_runs.asked == []


def test_a_refresh_opens_nothing_for_a_thread_with_no_record(settings):
    here = _world(settings, working_copies=refuses_to_cut(KEY))
    threads = here.threads()
    _replied(here.github)
    hear(threads)
    _reply_edited(here.github)

    assert hear(threads).refreshed == ()
    assert threads.get(KEY) is None
    assert list(here.working_copies.branches) == ["main"]


def test_one_thread_that_will_not_refresh_leaves_the_next_alone(settings):
    records = FakeThreadRecords()
    here = _world(settings, thread_records=records)
    threads = here.threads()
    _replied(here.github, "PRRT_1")
    _replied(here.github, "PRRT_2")
    hear(threads)
    records.refuse_lock("PRRT_1", OSError("read-only store"))
    _reply_edited(here.github, "PRRT_1")
    _reply_edited(here.github, "PRRT_2")

    refreshed = hear(threads).refreshed

    assert refreshed == ("PRRT_2",)
    assert [c.body for c in threads.get("PRRT_2").comments] == [
        BODY, "and this one, too"]
