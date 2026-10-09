import json
import re
import subprocess
from datetime import datetime
from types import SimpleNamespace

import pytest

from github_orchestrator.agent_runs.fake import Outcome
from github_orchestrator.conversation import (
    Classification,
    ConfidenceLevel,
    ConversationState,
    ReviewState,
)
from github_orchestrator.domain import Sha, Side
from github_orchestrator.github import PullRequestState, ThreadComment
from github_orchestrator.github import ReviewState as GitHubReviewState
from github_orchestrator.github.fake import ThreadAnchor
from github_orchestrator.notifications.fake import FakeNotifications
from tests.builders import a_pr
from tests.change_detection.support import disk_change_detection, polled_on_disk, seen
from tests.cli.support import ACCOUNT
from tests.conversation.support import (
    conversation_managers_over,
    hear,
    lost,
    on_github,
    said,
)
from tests.disk_layout import (
    thread_dir,
    thread_file,
    thread_worktree,
)
from tests.thread_records.support import disk_thread_records
from tests.working_copies.support import clone_of, real_working_copies

REPO = "acme/widgets"
PR = 7
THE_PR = a_pr(PR, REPO)
COMMENT_ID = 101
THREAD_KEY = f"PRRT_{COMMENT_ID}"

CREATED_AT_RE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z"


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True
    )


def _build_pr_worktree(root):
    repo = root / "prwork"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    (repo / "f").write_text("1")
    _git(repo, "add", "f")
    commit = _git(repo, "commit", "-q", "-m", "first")
    assert commit.returncode == 0, commit.stderr


@pytest.fixture
def pr_worktree(tmp_path, git_template):
    git_template(_build_pr_worktree)
    return tmp_path / "prwork"


def test_open_in_a_repo_this_hub_does_not_watch_says_so(pr_worktree, body_file, machine,
                                                         run_cli, settings):
    elsewhere = a_pr(PR, "acme/elsewhere")
    polled_on_disk(settings.state_dir, elsewhere, seen(settings.config.gh_account))
    machine.github.add_pr(elsewhere, PullRequestState(branch="main"))

    ran = run_cli(*_open_argv(body_file, repo="acme/elsewhere"))

    assert ran.code != 0
    assert "acme/elsewhere is not one of the watched repos" in ran.err


def _watching_the_pr(tmp_path, extra=""):
    return f'{ACCOUNT}{extra}[[repos]]\nrepo = "{REPO}"\nlocal_path = "{tmp_path / "prwork"}"\n'


@pytest.fixture(autouse=True)
def yours(settings, machine, tmp_path):
    polled_on_disk(settings.state_dir, THE_PR, seen(settings.config.gh_account))
    machine.config_path.write_text(_watching_the_pr(tmp_path))
    machine.github.add_pr(THE_PR, PullRequestState(branch="main"))


@pytest.fixture
def store(settings):
    return SimpleNamespace(
        threads=settings.threads_dir,
        worktrees=settings.thread_worktrees_dir,
    )


def _threads_of(settings, machine, pr=THE_PR):
    return conversation_managers_over(
        settings, github=machine.github,
        working_copies=real_working_copies(settings, machine.github,
                                           clones=clone_of(THE_PR, settings.data_dir / "prwork")),
        agent_runs=machine.runs(), thread_records=disk_thread_records(settings.threads_dir),
    ).of(pr)


@pytest.fixture
def threads(settings, machine):
    return _threads_of(settings, machine)


@pytest.fixture
def body_file(tmp_path):
    body = tmp_path / "body.md"
    body.write_text("Please rename this helper.\nIt shadows a builtin.")
    return body


def _open_argv(body_file, **overrides):
    fields = dict(
        repo=REPO, pr=PR, thread_id=THREAD_KEY, comment_id=COMMENT_ID, author="reviewer",
        path="src/foo.py", line=3, comment_type="review",
        body_file=body_file,
    )
    fields.update(overrides)
    argv = ["thread", "open"]
    for name, value in fields.items():
        if value is not None:
            argv.append(f"--{name.replace('_', '-')}={value}")
    return argv


def _report_argv(verb, **fields):
    argv = ["thread", verb, f"--repo={REPO}", f"--pr={PR}"]
    for name, value in fields.items():
        flag = f"--{name.replace('_', '-')}"
        for one in value if isinstance(value, list) else [value]:
            argv.append(f"{flag}={one}")
    return argv


def _skip_argv(thread_id=THREAD_KEY, classification="risky", reason="touches auth"):
    return _report_argv("skip", thread_id=thread_id, classification=classification,
                        reason=reason)


def _ready_argv(sha, **fields):
    return _report_argv("ready", thread_id=THREAD_KEY, sha=sha, tests="passed", **fields)


def _plan_argv(step=("Raise instead of continue",), file=("billing/invoice_writer.py",)):
    fields = {"thread_id": THREAD_KEY, "step": list(step)}
    if file is not None:
        fields["file"] = list(file)
    return _report_argv("plan", **fields)


def _stored(threads, key=THREAD_KEY):
    return threads.get(key)


def _plan(threads):
    return [(step.text, step.file, step.done) for step in _stored(threads).fix.plan]


def _running(machine, threads):
    machine.runs().script(Outcome())
    threads.tick(FakeNotifications(), on_hold=False)
    assert _stored(threads).standing is ConversationState.WORKING


@pytest.fixture
def opened(pr_worktree, body_file, run_cli):
    run_cli(*_open_argv(body_file))


@pytest.fixture
def running(opened, machine, threads):
    _running(machine, threads)


@pytest.fixture
def fixed(running, store):
    return _committed(thread_worktree(store.worktrees, THE_PR, THREAD_KEY), "the fix")


def _declined(threads):
    with threads.editing(THREAD_KEY) as editable:
        declined = editable.not_a_fix(Classification.RISKY, "touches auth")
    assert declined.fix.is_declined


def test_open_creates_worktree_branch_and_record(pr_worktree, store, threads,
                                                 body_file, run_cli):
    head = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()

    ran = run_cli(*_open_argv(body_file))

    wt = thread_worktree(store.worktrees, THE_PR, THREAD_KEY)
    assert wt.is_dir()
    assert (wt / "f").read_text() == "1"
    branch = f"orchestrator/thread/{PR}/{THREAD_KEY}"
    verify = _git(pr_worktree, "rev-parse", "--verify", branch)
    assert verify.returncode == 0
    assert verify.stdout.strip() == head

    stored = _stored(threads)
    assert stored.standing is ConversationState.QUEUED
    assert stored.fix.base_sha == Sha(head)
    assert stored.author == "reviewer"
    assert stored.path == "src/foo.py"
    assert stored.line == 3
    assert stored.comment_type == "review"
    assert stored.comment_id == COMMENT_ID
    assert stored.body == "Please rename this helper.\nIt shadows a builtin."
    assert re.fullmatch(CREATED_AT_RE, stored.created_at)

    assert ran.out == f"{wt}\n"


def test_open_on_a_thread_that_already_has_a_record_reopens_it(
    pr_worktree, store, threads, body_file, run_cli
):
    run_cli(*_open_argv(body_file))
    wt = thread_worktree(store.worktrees, THE_PR, THREAD_KEY)
    (wt / "half-done").write_text("work in progress")

    body_file.write_text("edited comment text")
    ran = run_cli(*_open_argv(body_file))

    assert wt.is_dir()
    assert ran.out == f"{wt}\n"
    assert (wt / "half-done").read_text() == "work in progress", (
        "an intact checkout is the one the agent is working in"
    )
    assert [p.name for p in thread_dir(store.threads, THE_PR).glob("*.json")] == [
        f"{THREAD_KEY}.json"
    ]
    assert _stored(threads).body == "edited comment text"
    listing = _git(pr_worktree, "worktree", "list", "--porcelain").stdout
    assert listing.count(str(wt)) == 1


def test_a_subagent_opening_a_polled_thread_keeps_what_the_poller_learned(
    pr_worktree, machine, threads, body_file, run_cli,
):
    on_github(
        machine.github, THREAD_KEY,
        ThreadComment(id=COMMENT_ID, author="anna", author_name="Anna Example",
                      review_state=GitHubReviewState.CHANGES_REQUESTED,
                      body="Please rename this helper.",
                      created_at="2026-08-28T10:00:00Z", updated_at="2026-08-28T10:00:00Z"),
        ThreadComment(id=COMMENT_ID + 1, author="bob", author_name="Bob Bee",
                      review_state=GitHubReviewState.COMMENTED, body="agreed",
                      created_at="2026-08-28T11:00:00Z", updated_at="2026-08-28T11:00:00Z"),
        pr=THE_PR, path="src/foo.py", line=None, is_resolved=False,
        anchor=ThreadAnchor(is_outdated=True, original_line=44, original_start_line=42,
                            original_commit="cafe1"))
    hear(threads)

    run_cli(*_open_argv(body_file))

    stored = _stored(threads)
    assert stored.reviewer_name == "Anna Example"
    assert stored.review_state == ReviewState.CHANGES_REQUESTED
    assert stored.is_outdated is True
    assert (stored.original_line, stored.original_start_line) == (44, 42)
    assert stored.original_commit == "cafe1"

    assert [(c.id, c.author, c.author_name) for c in stored.comments] == [
        (COMMENT_ID, "reviewer", "")
    ], (
        "open hands the domain one comment and Reopen means the whole thread, "
        "so the transcript collapses to the root the agent was given and the "
        "per-comment twins of the facts above go with it, until the next poll"
    )


def test_open_cuts_the_workspace_again_when_the_checkout_is_gone(
    pr_worktree, store, threads, body_file, run_cli
):
    run_cli(*_open_argv(body_file))
    wt = thread_worktree(store.worktrees, THE_PR, THREAD_KEY)
    removed = _git(pr_worktree, "worktree", "remove", "--force", str(wt))
    assert removed.returncode == 0, removed.stderr
    assert not wt.exists()

    ran = run_cli(*_open_argv(body_file))

    assert ran.out == f"{wt}\n"
    assert (wt / "f").read_text() == "1", (
        "the path the skill hands a subagent has to be a checkout that is there"
    )
    assert _stored(threads).fix.base_sha == Sha(_git(pr_worktree, "rev-parse",
                                                     "HEAD").stdout.strip())


def test_open_on_a_thread_whose_comment_was_deleted_cuts_its_workspace_again(
    pr_worktree, store, machine, threads, body_file, run_cli
):
    on_github(machine.github, THREAD_KEY, said(COMMENT_ID, "Please rename this helper."),
              pr=THE_PR)
    run_cli(*_open_argv(body_file))
    machine.github.delete_comment(THE_PR, machine.github.thread(THREAD_KEY).kind, COMMENT_ID)
    lost(threads, THREAD_KEY)
    assert _stored(threads).is_removed

    ran = run_cli(*_open_argv(body_file))

    wt = thread_worktree(store.worktrees, THE_PR, THREAD_KEY)
    assert ran.out == f"{wt}\n"
    assert (wt / "f").read_text() == "1"
    assert _stored(threads).fix.base_sha == Sha(_git(pr_worktree, "rev-parse",
                                                     "HEAD").stdout.strip())


def test_open_failed_worktree_add_exits_nonzero_without_record(
    pr_worktree, store, threads, body_file, run_cli
):
    store.worktrees.mkdir(parents=True)
    (store.worktrees / "acme").write_text("in the way")

    ran = run_cli(*_open_argv(body_file))

    assert ran.code != 0
    assert ran.out == ""
    assert ran.err != ""
    assert _stored(threads) is None


def test_open_retries_after_failed_add_left_the_branch_behind(
    pr_worktree, store, threads, body_file, run_cli
):
    head = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()
    branch = f"orchestrator/thread/{PR}/{THREAD_KEY}"

    store.worktrees.mkdir(parents=True)
    blocker = store.worktrees / "acme"
    blocker.write_text("in the way")
    assert run_cli(*_open_argv(body_file)).code != 0
    assert _git(pr_worktree, "rev-parse", "--verify", branch).returncode == 0

    blocker.unlink()
    ran = run_cli(*_open_argv(body_file))

    wt = thread_worktree(store.worktrees, THE_PR, THREAD_KEY)
    assert wt.is_dir()
    assert (wt / "f").read_text() == "1"
    verify = _git(pr_worktree, "rev-parse", "--verify", branch)
    assert verify.returncode == 0
    assert verify.stdout.strip() == head
    stored = _stored(threads)
    assert stored.standing is ConversationState.QUEUED
    assert stored.fix.base_sha == Sha(head)
    assert ran.out == f"{wt}\n"


def test_open_refuses_a_body_file_nobody_wrote(pr_worktree, store, threads,
                                               tmp_path, run_cli):
    ran = run_cli(*_open_argv(tmp_path / "nope.md"))

    assert ran.code == 1
    assert "not a file" in ran.err
    assert _stored(threads) is None


@pytest.mark.parametrize("thread_id", ["."])
def test_a_report_on_a_thread_id_that_names_no_file_is_refused(
    pr_worktree, store, run_cli, thread_id,
):
    ran = run_cli(*_skip_argv(thread_id=thread_id, reason="no"))

    assert ran.code == 1
    assert "thread" in ran.err


@pytest.mark.parametrize("thread_id", ["."])
def test_open_refuses_a_thread_id_that_names_no_file_of_its_own(
    pr_worktree, store, body_file, run_cli, thread_id,
):
    ran = run_cli(*_open_argv(body_file, thread_id=thread_id))

    assert ran.code == 1
    assert "thread" in ran.err


def test_open_stamps_the_root_comment_with_the_moment_it_was_opened(
    pr_worktree, store, threads, body_file, run_cli,
):
    run_cli(*_open_argv(body_file))

    stored = _stored(threads)
    assert stored.comment_created_at is not None
    assert stored.comments[0].created_at == stored.comment_created_at
    assert re.fullmatch(CREATED_AT_RE, stored.comment_created_at)


def test_skip_transitions_working_record(pr_worktree, running, threads, run_cli):
    ran = run_cli(*_skip_argv())

    assert ran.code == 0
    stored = _stored(threads)
    assert stored.fix.is_declined
    assert stored.fix.classification is Classification.RISKY
    assert stored.fix.reason == "touches auth"
    assert stored.body == "Please rename this helper.\nIt shadows a builtin."
    assert stored.fix.base_sha == Sha(_git(pr_worktree, "rev-parse", "HEAD").stdout.strip())


@pytest.mark.parametrize("classification", ["risky", "needs-human", "acknowledgement"])
def test_skip_takes_what_needs_no_answer(pr_worktree, running, threads, run_cli,
                                         classification):
    ran = run_cli(*_skip_argv(classification=classification, reason="nothing to change"))

    assert ran.code == 0, ran.err
    assert _stored(threads).fix.is_declined
    assert _stored(threads).fix.classification == classification


@pytest.mark.parametrize("classification", ["already-done", "question", "unclear",
                                            "out-of-scope"])
def test_skip_refuses_what_wants_a_reply(pr_worktree, running, threads, run_cli,
                                         classification):
    ran = run_cli(*_skip_argv(classification=classification, reason="nothing to change"))

    assert ran.code != 0
    assert _stored(threads).standing is ConversationState.WORKING


def _reply_argv(classification="question", body="It runs once per poll."):
    return _report_argv("reply", thread_id=THREAD_KEY, classification=classification,
                        body=body)


@pytest.mark.parametrize("classification", ["already-done", "question", "unclear",
                                            "out-of-scope"])
def test_reply_proposes_the_agents_answer(pr_worktree, running, threads, run_cli,
                                          classification):
    ran = run_cli(*_reply_argv(classification=classification))

    assert ran.code == 0, ran.err
    stored = _stored(threads)
    assert stored.fix.is_proposed
    assert stored.fix.classification == classification
    assert (stored.proposal.kind, stored.proposal.reply) == ("reply", "It runs once per poll.")


@pytest.mark.parametrize("classification", ["risky", "needs-human", "acknowledgement"])
def test_reply_refuses_what_needs_no_answer(pr_worktree, running, threads, run_cli,
                                            classification):
    ran = run_cli(*_reply_argv(classification=classification))

    assert ran.code != 0
    assert _stored(threads).standing is ConversationState.WORKING


def _ticket_argv(**fields):
    return _report_argv("ticket", thread_id=THREAD_KEY, **{
        "project": "PROJ", "title": "Cache tax rates across exports",
        "body": "Each export reads its model again.",
        "reply": "That belongs outside this PR, so I've proposed a ticket.", **fields})


def test_ticket_proposes_the_agents_ticket_and_reply(pr_worktree, running, threads, run_cli):
    ran = run_cli(*_ticket_argv())

    assert ran.code == 0, ran.err
    stored = _stored(threads)
    assert stored.fix.is_proposed
    assert stored.fix.classification == "out-of-scope"
    proposal = stored.proposal
    assert (proposal.kind, proposal.reply) == (
        "ticket", "That belongs outside this PR, so I've proposed a ticket.")
    assert (proposal.ticket.project, proposal.ticket.title, proposal.ticket.body) == (
        "PROJ", "Cache tax rates across exports", "Each export reads its model again.")


def _filed_argv(**fields):
    return _report_argv("filed", thread_id=THREAD_KEY, **{
        "key": "PROJ-12", "url": "https://example.atlassian.net/browse/PROJ-12", **fields})


def test_filed_records_the_ticket_the_filing_run_filed(pr_worktree, running, threads, run_cli):
    run_cli(*_ticket_argv())
    with threads.editing(THREAD_KEY) as editable:
        editable.approve(reply="Filed it.")
    threads.tick(FakeNotifications(), on_hold=False)

    ran = run_cli(*_filed_argv())

    assert ran.code == 0, ran.err
    fix = _stored(threads).fix
    assert (fix.filed, fix.ticket_key, fix.ticket_url) == (
        True, "PROJ-12", "https://example.atlassian.net/browse/PROJ-12")


def test_filed_from_a_run_that_files_no_ticket_exits_nonzero(running, threads, run_cli):
    ran = run_cli(*_filed_argv())

    assert ran.code != 0
    assert "files no ticket" in ran.err
    assert not _stored(threads).fix.filed


def test_a_reply_after_a_ticket_leaves_no_ticket_behind(pr_worktree, running, threads, run_cli):
    run_cli(*_ticket_argv())

    ran = run_cli(*_reply_argv())

    assert ran.code == 0, ran.err
    assert (_stored(threads).proposal.kind, _stored(threads).proposal.ticket) == ("reply", None)


def test_ticket_on_a_thread_nobody_is_working_on_exits_nonzero(opened, threads, run_cli):
    ran = run_cli(*_ticket_argv())

    assert ran.code != 0
    assert "was not marked" in ran.err


def test_reply_on_a_thread_nobody_is_working_on_exits_nonzero(opened, threads, run_cli):
    ran = run_cli(*_reply_argv())

    assert ran.code != 0
    assert "was not marked" in ran.err


def test_skip_on_disallowed_status_exits_nonzero(fixed, threads, run_cli):
    run_cli(*_ready_argv(sha=fixed))

    ran = run_cli(*_skip_argv())

    assert ran.code != 0
    assert "was not marked" in ran.err
    assert _stored(threads).fix.is_proposed


def test_skip_on_missing_record_exits_nonzero(store, run_cli):
    ran = run_cli(*_skip_argv(classification="needs-human", reason="unclear"))

    assert ran.code != 0
    assert "no thread" in ran.err


def test_ready_transitions_working_record(fixed, threads, run_cli):
    run_cli(*_ready_argv(sha=fixed, note="renamed the helper"))

    fix = _stored(threads).fix
    assert fix.is_proposed
    assert fix.thread_sha == Sha(fixed)
    assert fix.tests == "passed"
    assert fix.tests_note is None
    assert fix.agent_note == "renamed the helper"


def test_ready_stamps_the_moment_the_fix_became_the_operators_to_decide(
    fixed, threads, run_cli,
):
    run_cli(*_ready_argv(sha=fixed))

    stamp = _stored(threads).decidable_at
    assert stamp, "the agent's report left no moment for the board to order on"
    assert datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.parametrize("sha", ["--output=/tmp/pwned"])
def test_ready_refuses_a_sha_that_is_not_a_commit_hash(running, threads, run_cli, sha):
    ran = run_cli(*_ready_argv(sha=sha))

    assert ran.code == 1
    assert "commit hash" in ran.err
    assert _stored(threads).fix.thread_sha is None


def _committed(cwd, message):
    (cwd / "g").write_text(message)
    _git(cwd, "add", "g")
    commit = _git(cwd, "commit", "-q", "-m", message)
    assert commit.returncode == 0, commit.stderr
    return _git(cwd, "rev-parse", "HEAD").stdout.strip()


def _fixed_on_a_rewritten_pr_branch(pr_worktree, store):
    _git(pr_worktree, "commit", "-q", "--amend", "-m", "first, rewritten")
    tip = _git(pr_worktree, "rev-parse", "HEAD").stdout.strip()
    workspace = thread_worktree(store.worktrees, THE_PR, THREAD_KEY)
    _git(workspace, "reset", "-q", "--hard", tip)
    return tip, _committed(workspace, "the fix, rebased onto the rewritten tip")


def test_ready_refuses_a_commit_the_threads_base_is_no_ancestor_of(
    running, pr_worktree, store, threads, run_cli,
):
    base = _stored(threads).fix.base_sha
    _, fix = _fixed_on_a_rewritten_pr_branch(pr_worktree, store)

    ran = run_cli(*_ready_argv(sha=fix))

    assert ran.code == 1
    assert f"{base} is not an ancestor of {fix}" in ran.err
    assert "thread base" in ran.err
    assert f"rebase your commit onto {base}" in ran.err
    assert _stored(threads).fix.thread_sha is None


def test_a_commit_rebased_onto_a_new_tip_is_ready_once_the_base_moves_there(
    running, pr_worktree, store, threads, run_cli,
):
    tip, fix = _fixed_on_a_rewritten_pr_branch(pr_worktree, store)

    moved = run_cli(*_report_argv("base", thread_id=THREAD_KEY, sha=tip))
    reported = run_cli(*_ready_argv(sha=fix))

    assert (moved.code, reported.code) == (0, 0)
    fix_record = _stored(threads).fix
    assert fix_record.base_sha == Sha(tip)
    assert fix_record.thread_sha == Sha(fix)


def test_base_refuses_a_sha_that_is_not_a_commit_hash(running, threads, run_cli):
    base = _stored(threads).fix.base_sha

    ran = run_cli(*_report_argv("base", thread_id=THREAD_KEY, sha="--output=/tmp/pwned"))

    assert ran.code == 1
    assert "commit hash" in ran.err
    assert _stored(threads).fix.base_sha == base


def test_base_refuses_a_thread_nobody_is_working_on(opened, threads, run_cli):
    base = _stored(threads).fix.base_sha

    ran = run_cli(*_report_argv("base", thread_id=THREAD_KEY, sha="a" * 40))

    assert ran.code == 1
    assert _stored(threads).fix.base_sha == base


def test_a_subagent_plans_the_moment_its_thread_is_opened(
    pr_worktree, store, threads, body_file, run_cli,
):
    run_cli(*_open_argv(body_file))

    run_cli(*_plan_argv(step=["Raise instead of continue", "Test it"],
                        file=["billing/invoice_writer.py", "tests/test_invoices.py"]))
    run_cli(*_report_argv("step", thread_id=THREAD_KEY, done=1))

    stored = _stored(threads)
    assert stored.standing is ConversationState.QUEUED, (
        "the manager's tick has not started a run yet, and the skill plans "
        "seconds after thread open"
    )
    assert [step.done for step in stored.fix.plan] == [True, False]


def test_plan_records_each_step_beside_the_file_it_touches(running, threads, run_cli):
    run_cli(*_plan_argv(step=["Raise instead of continue", "Test it"],
                        file=["billing/invoice_writer.py", "tests/test_invoices.py"]))

    assert _plan(threads) == [
        ("Raise instead of continue", "billing/invoice_writer.py", False),
        ("Test it", "tests/test_invoices.py", False),
    ]


def test_a_step_whose_file_is_left_empty_names_no_file_at_all(running, threads, run_cli):
    run_cli(*_plan_argv(step=["Raise instead", "Work out who relied on it"],
                        file=["billing/invoice_writer.py", ""]))

    assert _plan(threads) == [
        ("Raise instead", "billing/invoice_writer.py", False),
        ("Work out who relied on it", None, False),
    ], "an empty --file is the only way to say one step of several has none"


def test_plan_takes_steps_whose_files_the_agent_does_not_know(running, threads, run_cli):
    run_cli(*_plan_argv(step=["Work out where this belongs"], file=None))

    assert _plan(threads) == [("Work out where this belongs", None, False)]


@pytest.mark.parametrize("steps,files", [
    (["one", "two"], ["one.py"]),
])
def test_plan_refuses_files_that_do_not_pair_off_against_the_steps(
    running, threads, run_cli, steps, files,
):
    ran = run_cli(*_plan_argv(step=steps, file=files))

    assert ran.code == 1
    assert "--file" in ran.err
    assert _plan(threads) == []


@pytest.fixture
def planned(running, threads):
    with threads.editing(THREAD_KEY) as editable:
        editable.plan([("step 1", None), ("step 2", None)])


def test_step_marks_the_steps_the_agent_has_finished(planned, threads, run_cli):
    run_cli(*_report_argv("step", thread_id=THREAD_KEY, done=2))

    assert [step.done for step in _stored(threads).fix.plan] == [False, True]


def test_step_on_a_number_the_plan_does_not_have_exits_nonzero(planned, threads, run_cli):
    ran = run_cli(*_report_argv("step", thread_id=THREAD_KEY, done=3))

    assert ran.code != 0
    assert "was not marked" in ran.err
    assert "step 3 is outside a plan of 2" in ran.err, (
        "'open/running' is a state this verb takes, so the token alone "
        "misdirects; the refusal's own reason is the only thing that says why"
    )
    assert [step.done for step in _stored(threads).fix.plan] == [False, False]


def test_ready_records_what_the_fix_does_and_how_sure_the_agent_is(fixed, threads, run_cli):
    run_cli(*_ready_argv(sha=fixed, summary="Raise instead of skipping, and test it.",
                         confidence="medium",
                         confidence_note="Callers may rely on the silent skip."))

    fix = _stored(threads).fix
    assert fix.summary == "Raise instead of skipping, and test it."
    assert fix.confidence is ConfidenceLevel.MEDIUM
    assert fix.confidence_note == "Callers may rely on the silent skip."


def test_fail_records_reason_and_keeps_worktree(opened, store, machine, threads, run_cli):
    attempts = _stored(threads).run_holder.attempts_allowed

    for attempt in range(1, attempts + 1):
        _running(machine, threads)
        run_cli(*_report_argv("fail", thread_id=THREAD_KEY, reason="tests failed"))
        stored = _stored(threads)
        assert stored.fix.reason == "tests failed"
        assert stored.fix.has_failed is (attempt == attempts), attempt

    assert thread_worktree(store.worktrees, THE_PR, THREAD_KEY).is_dir()


def test_ready_prints_the_record_it_saved(fixed, threads, run_cli):
    ran = run_cli(*_ready_argv(sha=fixed, note="renamed the helper"))

    shown = json.loads(ran.out)
    assert shown["state"] == _stored(threads).standing.value
    assert shown["sha"] == fixed
    assert shown["tests"] == "passed"
    assert shown["note"] == "renamed the helper"


def test_show_prints_the_saved_record_of_one_thread(fixed, threads, run_cli):
    run_cli(*_ready_argv(sha=fixed, summary="Rename the helper.", confidence="high"))

    shown = json.loads(run_cli("thread", "show", f"--repo={REPO}", f"--pr={PR}",
                               f"--thread-id={THREAD_KEY}").out)

    assert shown == {
        "key": THREAD_KEY, "state": _stored(threads).standing.value,
        "path": "src/foo.py", "line": 3, "gist": "Please rename this helper.",
        "sha": fixed, "tests": "passed", "tests_note": None, "note": None,
        "summary": "Rename the helper.", "confidence": "high", "confidence_note": None,
    }


def test_show_on_a_thread_with_no_record_exits_nonzero(store, run_cli):
    ran = run_cli("thread", "show", f"--repo={REPO}", f"--pr={PR}",
                  f"--thread-id={THREAD_KEY}")

    assert ran.code == 1
    assert "no thread" in ran.err


def test_list_prints_a_line_per_thread_in_the_order_they_were_opened(
        pr_worktree, body_file, run_cli):
    run_cli(*_open_argv(body_file))
    run_cli(*_open_argv(body_file, thread_id="PRRT_202", comment_id=202))

    listed = run_cli("thread", "list", f"--repo={REPO}", f"--pr={PR}").out

    assert listed == (f"{THREAD_KEY}  queued  src/foo.py:3  Please rename this helper.\n"
                      f"PRRT_202  queued  src/foo.py:3  Please rename this helper.\n")


def test_list_says_a_record_that_will_not_parse_is_unreadable(store, run_cli):
    path = thread_file(store.threads, THE_PR, THREAD_KEY)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")

    listed = run_cli("thread", "list", f"--repo={REPO}", f"--pr={PR}").out

    assert listed == f"{THREAD_KEY}  unreadable\n"


@pytest.mark.parametrize("verb", ["open", "list"])
def test_a_thread_command_names_its_repo_since_a_hub_watches_more_than_one(
        pr_worktree, body_file, run_cli, verb):
    argv = _open_argv(body_file, repo=None) if verb == "open" else ["thread", "list", f"--pr={PR}"]

    ran = run_cli(*argv)

    assert ran.code == 2
    assert "--repo" in ran.err


def test_a_review_finding_becomes_a_draft_on_the_line_it_is_about(
        store, threads, body_file, run_cli):
    ran = run_cli(
        "thread", "draft",
        "--repo", REPO, "--pr", str(PR), "--path", "src/foo.py",
        "--line", "12", "--start-line", "10", "--side", "before",
        "--body-file", str(body_file),
    )

    drafted = _stored(threads, ran.out.strip())
    assert drafted.standing is ConversationState.DRAFT
    assert drafted.github_node_id is None
    assert drafted.body == "Please rename this helper.\nIt shadows a builtin."
    assert (drafted.path, drafted.start_line, drafted.start_side, drafted.line,
            drafted.side) == ("src/foo.py", 10, Side.BEFORE, 12, Side.BEFORE)


def test_a_finding_over_lines_may_start_on_the_other_side(
        store, threads, body_file, run_cli):
    ran = run_cli(
        "thread", "draft",
        "--repo", REPO, "--pr", str(PR), "--path", "src/foo.py",
        "--line", "12", "--start-line", "10", "--start-side", "before",
        "--side", "after", "--body-file", str(body_file),
    )

    drafted = _stored(threads, ran.out.strip())
    assert (drafted.start_line, drafted.start_side, drafted.line, drafted.side) == (
        10, Side.BEFORE, 12, Side.AFTER)


def test_a_finding_on_one_line_has_no_start_side(store, threads, body_file, run_cli):
    ran = run_cli(
        "thread", "draft",
        "--repo", REPO, "--pr", str(PR), "--path", "src/foo.py",
        "--line", "12", "--start-side", "before", "--body-file", str(body_file),
    )

    assert _stored(threads, ran.out.strip()).start_side is None


def test_a_finding_on_a_pr_whose_role_is_not_known_yet_makes_no_draft(
        store, threads, body_file, run_cli, settings):
    disk_change_detection(settings.state_dir).forget(THE_PR)

    ran = run_cli(
        "thread", "draft", "--repo", REPO, "--pr", str(PR), "--path", "src/foo.py",
        "--line", "12", "--body-file", str(body_file),
    )

    assert ran.code != 0
    assert "whether this PR is yours is not known" in ran.err
    assert threads.all() == []


def test_a_finding_with_nothing_in_it_makes_no_draft(store, threads, tmp_path, run_cli):
    empty = tmp_path / "empty.md"
    empty.write_text("  \n")
    ran = run_cli(
        "thread", "draft", "--repo", REPO,
        "--pr", str(PR), "--path", "src/foo.py", "--line", "12",
        "--body-file", str(empty),
    )

    assert ran.code == 1
    assert threads.all() == []


def test_thread_open_says_it_is_waiting_for_the_model(
    pr_worktree, store, body_file, machine, run_cli
):
    ran = run_cli(*_open_argv(body_file, path=None, line=None))

    assert len(machine.runs().asked) == 1
    assert "waiting for haiku" in ran.err
    assert ran.out.strip() == str(thread_worktree(store.worktrees, THE_PR,
                                                  THREAD_KEY))


def test_thread_open_asks_for_no_gist_while_claude_is_disabled(
    pr_worktree, store, body_file, machine, run_cli, tmp_path,
):
    machine.config_path.write_text(_watching_the_pr(tmp_path, "agents_enabled = false\n"))

    ran = run_cli(*_open_argv(body_file, path=None, line=None))

    assert machine.runs().asked == []
    assert "waiting" not in ran.err


def test_thread_without_subcommand_prints_help_and_exits_1(run_cli):
    ran = run_cli("thread")
    assert ran.code == 1
    assert "open" in ran.out
