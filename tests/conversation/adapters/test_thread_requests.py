from dataclasses import replace
from pathlib import Path

from github_orchestrator.agent_runs import FixComment, PointedAt
from github_orchestrator.agent_runs.fake import (
    FixingThread,
    RebasingFix,
    Reworking,
    Session,
)
from github_orchestrator.conversation import Classification
from github_orchestrator.settings.fake import Tracker
from tests.builders import a_pr
from tests.conversation.support import (
    PR,
    REPO,
    WORKTREE,
    drain,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    world,
)

THE_PR = a_pr(PR, REPO)

KEY = "PRRT_1"
ROOT = said(1, "rename this", created_at="2026-08-28T10:00:00Z")


def _heard(settings, *replies):
    here = world(settings)
    repo_at(here.working_copies, WORKTREE, {"src/foo.py": "old\n"})
    threads = here.threads()
    on_github(here.github, KEY, ROOT, *replies, path="src/foo.py", line=4)
    hear(threads)
    return here, threads


def _reply_arrives(here, threads, comment):
    thread = here.github.thread(KEY)
    here.github.prs[THE_PR].threads = []
    here.github.add_thread(THE_PR, replace(thread, comments=(*thread.comments, comment)))
    hear(threads)


def _started(here, threads):
    drain(threads)
    return here.agent_runs.started[-1].work


def _proposed(settings, *replies):
    here, threads = _heard(settings, *replies)
    propose(here, threads, KEY, {"src/foo.py": "new\n"})
    return here, threads


def _session(here, threads, steer: str = "") -> Session:
    here.pr_processes.open(THE_PR, Path(WORKTREE))
    with threads.editing(KEY) as editable:
        editable.start_session(steer=steer)
    drain(threads)

    [session] = here.agent_runs.sessions
    return session


def _declined(settings):
    here, threads = _heard(settings)
    start_run(here, threads)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.NEEDS_HUMAN, "two plausible readings")
    return here, threads


def test_a_queued_thread_asks_for_its_fix_with_the_whole_thread(settings):
    here, threads = _heard(settings, said(2, "which one?", author=settings.config.gh_account,
                                          author_name="Octo Cat",
                                          created_at="2026-08-28T11:00:00Z"))

    work = _started(here, threads)

    assert isinstance(work, FixingThread)
    fix = work.fix
    assert (fix.pr, fix.key, fix.worktree) == (
        THE_PR, KEY, f"/fake/thread-worktrees/{THE_PR.repo.owner}/{THE_PR.repo.name}/{THE_PR.number}/{KEY}")
    assert (fix.author, fix.path, fix.line, fix.body) == ("reviewer", "src/foo.py", 4,
                                                          "rename this")
    assert fix.comments == (
        FixComment("reviewer", "rename this", "2026-08-28T10:00:00Z", "", False),
        FixComment(settings.config.gh_account, "which one?", "2026-08-28T11:00:00Z",
                   "Octo Cat", True),
    )
    assert fix.confidence_levels == ("low", "medium", "high")


def test_a_thread_says_how_it_had_ended_up_before_the_newest_reply(settings):
    here, threads = _proposed(settings)
    with threads.editing(KEY) as editable:
        editable.reject(reply="not this one")
    drain(threads)
    _reply_arrives(here, threads, said(2, "please reconsider"))

    fix = _started(here, threads).fix

    assert (fix.before_reply, fix.withdraws_proposal) == ("rejected: not this one", False)


def test_a_thread_whose_fix_was_proposed_says_a_skip_withdraws_the_proposal(settings):
    here, threads = _proposed(settings)
    _reply_arrives(here, threads, said(2, "and the other one"))

    fix = _started(here, threads).fix

    assert fix.withdraws_proposal is True


def test_a_queued_rebase_asks_for_the_fix_rebased_onto_the_pr_s_head(settings):
    here, threads = _proposed(settings)
    onto = here.working_copies.commit(WORKTREE, {"src/foo.py": "theirs\n"}, "someone else")
    with threads.editing(KEY) as editable:
        editable.approve()
    drain(threads)

    work = _started(here, threads)

    assert isinstance(work, RebasingFix)
    assert (work.onto, work.fix.conflict) == (
        onto, "CONFLICT (content): Merge conflict in src/foo.py")


def test_a_queued_rework_carries_the_operator_s_brief(settings):
    here, threads = _proposed(settings,
                              said(2, "and drop the cache while you are there", author="mira",
                                   author_name="Mira Sample", created_at=None),
                              said(3, "unrelated aside", author="jo"))
    with threads.editing(KEY) as editable:
        editable.rework(note="Use the enum instead.",
                        pointed=[("billing/invoice_writer.py", 142,
                                  "    return sorted(line_items)")],
                        include=["mira"])

    work = _started(here, threads)

    assert isinstance(work, Reworking)
    fix = work.fix
    assert fix.note == "Use the enum instead."
    assert fix.pointed == (PointedAt("billing/invoice_writer.py", 142,
                                     "    return sorted(line_items)"),)
    assert fix.replies == (FixComment("mira", "and drop the cache while you are there",
                                      None, "Mira Sample", False),)


def test_a_queued_rework_of_a_skipped_fix_says_why_it_was_skipped(settings):
    here, threads = _declined(settings)
    with threads.editing(KEY) as editable:
        editable.rework(note="pick the first reading")

    fix = _started(here, threads).fix

    assert (fix.classification, fix.skipped_because) == ("needs-human", "two plausible readings")


def test_a_queued_rework_of_a_proposed_reply_carries_the_reply(settings):
    here, threads = _heard(settings)
    start_run(here, threads)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.QUESTION, "It runs once per poll.")
    with threads.editing(KEY) as editable:
        editable.rework(note="say why it runs once")

    fix = _started(here, threads).fix

    assert (fix.reply, fix.note, fix.skipped_because) == (
        "It runs once per poll.", "say why it runs once", None)


def test_a_queued_rework_of_a_proposed_commit_carries_no_reply(settings):
    here, threads = _proposed(settings)
    with threads.editing(KEY) as editable:
        editable.rework(note="Use the enum instead.")

    assert _started(here, threads).fix.reply is None


def test_a_queued_rework_of_a_proposed_ticket_carries_the_ticket_and_its_reply(settings):
    here, threads = _heard(settings)
    start_run(here, threads)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.OUT_OF_SCOPE, "I've proposed a ticket.",
                           ticket_project="PROJ", ticket_title="Cache models",
                           ticket_body="Each export reads its model again.")
    with threads.editing(KEY) as editable:
        editable.rework(note="it belongs in WEB")

    fix = _started(here, threads).fix

    assert (fix.ticket_project, fix.ticket_title, fix.ticket_body, fix.reply) == (
        "PROJ", "Cache models", "Each export reads its model again.", "I've proposed a ticket.")


def test_a_queued_rework_of_a_proposed_reply_carries_no_ticket(settings):
    here, threads = _heard(settings)
    start_run(here, threads)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.QUESTION, "It runs once per poll.")
    with threads.editing(KEY) as editable:
        editable.rework(note="say why it runs once")

    fix = _started(here, threads).fix

    assert (fix.ticket_project, fix.ticket_title, fix.ticket_body) == (None, None, None)


def _tracking(settings, **config):
    return replace(settings, config=replace(settings.config, **config))


def test_a_thread_asks_for_its_fix_with_the_tracker_and_the_branch_s_ticket(settings):
    here, threads = _heard(_tracking(settings, tracker=Tracker.JIRA, tracker_project="PROJ"))
    here.polled(branch="PROJ-21-cache-tax-rates")

    fix = _started(here, threads).fix

    assert (fix.tracker, fix.tracker_project, fix.branch_ticket) == ("jira", "PROJ", "PROJ-21")


def test_a_thread_on_github_issues_names_no_project(settings):
    here, threads = _heard(_tracking(settings, tracker=Tracker.GITHUB))

    fix = _started(here, threads).fix

    assert (fix.tracker, fix.tracker_project) == ("github", None)


def test_a_thread_with_no_tracker_and_no_ticket_in_its_branch_is_told_of_neither(settings):
    here, threads = _heard(settings)
    here.polled(branch="tidy-the-reader")

    fix = _started(here, threads).fix

    assert (fix.tracker, fix.tracker_project, fix.branch_ticket) == (None, None, None)


def test_a_rework_briefed_with_a_note_alone_carries_no_lines_or_replies(settings):
    here, threads = _proposed(settings)
    with threads.editing(KEY) as editable:
        editable.rework(note="Use the enum instead.")

    work = _started(here, threads)

    assert isinstance(work, Reworking)
    assert (work.fix.pointed, work.fix.replies, work.fix.skipped_because) == ((), (), None)


def test_a_session_is_steered_by_what_the_operator_asked_for(settings):
    here, threads = _proposed(settings)

    session = _session(here, threads, steer="Keep the old name.")

    assert session.steer == "Keep the old name."


def test_a_session_on_a_skipped_fix_says_why_it_was_skipped(settings):
    session = _session(*_declined(settings))

    assert (session.fix.classification, session.fix.skipped_because) == (
        "needs-human", "two plausible readings")


def test_a_failure_after_a_skip_is_never_read_back_as_the_skip_s_reason(settings):
    here, threads = _declined(settings)
    with threads.editing(KEY) as editable:
        editable.retry()
    for _ in range(threads.get(KEY).run_holder.attempts_allowed):
        start_run(here, threads)
        with threads.editing(KEY) as editable:
            editable.fail("tests failed")
    assert threads.get(KEY).fix.has_failed

    session = _session(here, threads)

    assert session.fix.skipped_because is None
