from github_orchestrator.agent_runs.fake import FixingThread
from github_orchestrator.conversation import (
    ConversationState,
    Denied,
    ErrorCode,
    OperationKind,
)
from github_orchestrator.domain import Location, Side
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.conversation.support import (
    PR,
    REPO,
    WORKTREE,
    at,
    commit_fix,
    drain,
    first_poll,
    repo_at,
    start_run,
    world,
)

THE_PR = a_pr(PR, REPO)

NOW = "2026-11-12T10:00:00Z"

ASKED = "make this loop stop at the first match"

HERE = Location(path="f.py", line=4, side=Side.AFTER)


class Requesting:
    def __init__(self, settings):
        self.github = FakeGitHub()
        self.here = world(settings, github=self.github,
                          working_copies=FakeWorkingCopies(self.github), clock=at(NOW))
        self.working_copies = self.here.working_copies
        repo_at(self.working_copies, WORKTREE, {"f.py": "old\n"})
        self.threads = self.here.threads(agents_enabled=True)
        first_poll(self.github, self.threads)

    def request(self, *, visible=False):
        made = self.threads.open_request(ASKED, HERE, visible=visible)
        assert not isinstance(made, Denied), made
        if visible:
            drain(self.threads)
        self.key = made.key
        return self.threads.get(made.key)

    def stored(self):
        return self.threads.get(self.key)

    def propose(self):
        start_run(self.here, self.threads)
        sha = commit_fix(self.here, self.key, {"f.py": "new\n"})
        with self.threads.editing(self.key) as editable:
            assert not isinstance(editable.ready(sha), Denied)
        drain(self.threads)

    def asked(self, verb):
        with self.threads.editing(self.key) as editable:
            answer = verb(editable)
        drain(self.threads)
        return answer

    def on_github(self):
        record = self.github.prs[THE_PR]
        return record.threads, record.review_comments

    def pr_tree(self):
        return self.working_copies.commits[self.working_copies.branches["main"]].tree


def test_a_requested_change_is_a_thread_on_the_board_alone_with_your_words_as_its_comment(
        settings):
    requesting = Requesting(settings)

    requested = requesting.request()

    assert requested.comment_type == "request"
    assert requested.github_node_id is None and requested.comment_id is None
    assert [(one.author, one.body) for one in requested.comments] == [("octocat", ASKED)]
    assert (requested.path, requested.line, requested.side) == ("f.py", 4, Side.AFTER)
    assert requesting.on_github() == ([], {})


def test_a_requested_change_gets_a_first_run_like_a_comment_that_just_arrived(settings):
    requesting = Requesting(settings)
    requesting.request()

    start_run(requesting.here, requesting.threads, finishes=False)

    assert requesting.stored().fix.run.kind is OperationKind.FIRST
    [started] = requesting.here.agent_runs.started
    assert isinstance(started.work, FixingThread)
    assert started.work.fix.body == ASKED


def test_a_visible_request_runs_its_first_fix_in_a_session_you_can_watch(settings):
    requesting = Requesting(settings)

    requested = requesting.request(visible=True)

    assert requested.standing is ConversationState.IN_SESSION
    [opened] = requesting.here.agent_runs.sessions
    assert opened.first
    assert opened.fix.body == ASKED
    assert requesting.here.agent_runs.started == []


def test_a_visible_request_whose_session_ends_without_reporting_is_left_to_fix_again(
        settings):
    requesting = Requesting(settings)
    requesting.request(visible=True)

    requesting.asked(lambda editable: editable.session_gone())

    stored = requesting.stored()
    assert stored.standing is not ConversationState.IN_SESSION
    assert not isinstance(requesting.asked(lambda editable: editable.retry()), Denied)


def test_accepting_a_requested_change_lands_it_and_resolves_it_on_the_board_alone(settings):
    requesting = Requesting(settings)
    requesting.request()
    requesting.propose()

    accepted = requesting.asked(lambda editable: editable.approve(reply="done"))

    assert not isinstance(accepted, Denied), accepted
    assert requesting.pr_tree()["f.py"] == "new\n"
    assert requesting.stored().standing is ConversationState.DONE
    assert requesting.on_github() == ([], {})


def test_rejecting_a_requested_change_posts_nothing(settings):
    requesting = Requesting(settings)
    requesting.request()
    requesting.propose()

    rejected = requesting.asked(lambda editable: editable.reject(reply="never mind"))

    assert not isinstance(rejected, Denied), rejected
    assert requesting.stored().standing is ConversationState.DONE
    assert requesting.on_github() == ([], {})


def test_a_requested_change_has_no_github_thread_to_reply_in(settings):
    requesting = Requesting(settings)
    requesting.request()
    requesting.propose()

    replied = requesting.asked(lambda editable: editable.reply("and the other loop"))

    assert isinstance(replied, Denied)
    assert replied.code == ErrorCode.MALFORMED_REQUEST
    assert requesting.on_github() == ([], {})


def test_a_change_is_requested_only_on_your_own_pull_request(settings):
    requesting = Requesting(settings)
    requesting.threads = requesting.here.threads(is_author=False, agents_enabled=True)

    refused = requesting.threads.open_request(ASKED, HERE, visible=False)

    assert isinstance(refused, Denied)
    assert refused.code == ErrorCode.MALFORMED_REQUEST


def test_no_change_is_requested_while_agents_are_disabled(settings):
    requesting = Requesting(settings)
    requesting.threads = requesting.here.threads(agents_enabled=False)

    refused = requesting.threads.open_request(ASKED, HERE, visible=True)

    assert isinstance(refused, Denied)
    assert refused.code == ErrorCode.AGENTS_DISABLED
    assert requesting.threads.all() == []
