from github_orchestrator.agent_runs.fake import (
    CommentAsked,
    FakeAgentRuns,
    ThreadAsked,
    VerdictAsked,
)
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    Thread,
    ThreadComment,
)
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.builders import a_pr
from tests.conversation.support import PR, REPO, hear, world

THE_PR = a_pr(PR, REPO)

GIST_MAX_CHARS = 60


def _comment(comment_id, author, body):
    return ThreadComment(id=comment_id, author=author, body=body,
                         created_at="2026-09-01T10:00:00Z",
                         updated_at="2026-09-01T10:00:00Z")


def _root_only(path="src/foo.py", line=4):
    kind = CommentKind.REVIEW if path else CommentKind.ISSUE
    return Thread(key="PRRT_1", kind=kind, path=path, line=line,
                  comments=(_comment(1, "reviewer", "rename this"),))


def _answered(thread):
    return Thread(key=thread.key, kind=thread.kind, path=thread.path, line=thread.line,
                  comments=(*thread.comments, _comment(2, "me", "which one?")))


class _AnsweringLater(FakeAgentRuns):
    def __init__(self):
        super().__init__(FakePrProcesses())
        self.pending = []

    def summarize_comment(self, key, path, line, body, done, *, chars):
        super().summarize_comment(key, path, line, body,
                                  lambda gist: self.pending.append((done, gist)), chars=chars)

    def summarize_thread(self, key, path, line, comments, done, *, chars):
        super().summarize_thread(key, path, line, comments,
                                 lambda gist: self.pending.append((done, gist)), chars=chars)

    def deliver(self):
        while self.pending:
            done, gist = self.pending.pop(0)
            done(gist)


def _world(settings, *answers):
    github = FakeGitHub(account="me")
    github.add_pr(THE_PR, PullRequestState(author="me"))
    built = world(settings, github=github, agent_runs=_AnsweringLater())
    built.agent_runs.answer(*answers)
    return built


def _materialised(built, thread, agents_enabled=None):
    built.github.prs[(THE_PR)].threads = []
    threads = built.threads(is_author=False, agents_enabled=agents_enabled)
    hear(threads)
    built.github.add_thread(THE_PR, thread)
    hear(threads)
    built.agent_runs.deliver()
    return threads.get("PRRT_1")


def _gists_asked(built):
    return [asked for asked in built.agent_runs.asked if not isinstance(asked, VerdictAsked)]


def test_a_root_gist_summarises_the_root_comment_alone(settings):
    built = _world(settings, "rename the helper")

    stored = _materialised(built, _root_only())

    assert _gists_asked(built) == [
        CommentAsked("PRRT_1", "src/foo.py", 4, "rename this", GIST_MAX_CHARS)]
    assert stored.gist == "rename the helper"


def test_a_comment_on_no_line_is_summarised_with_no_place(settings):
    built = _world(settings)

    _materialised(built, _root_only(path=None, line=None))

    assert _gists_asked(built) == [
        CommentAsked("PRRT_1", None, None, "rename this", GIST_MAX_CHARS)]


def test_a_thread_gist_summarises_every_comment_in_order(settings):
    built = _world(settings, None, None, "say which helper")
    thread = _root_only()
    _materialised(built, thread)

    stored = _materialised(built, _answered(thread))

    assert _gists_asked(built)[1] == ThreadAsked(
        "PRRT_1", "src/foo.py", 4, (("reviewer", "rename this"), ("me", "which one?")),
        GIST_MAX_CHARS)
    assert stored.gist == "say which helper"


def test_a_long_gist_is_clipped(settings):
    built = _world(settings, "b" * 90)

    stored = _materialised(built, _root_only())

    assert len(stored.gist) == GIST_MAX_CHARS and stored.gist.endswith("…")


def test_a_gist_the_model_would_not_write_leaves_the_fallback(settings):
    built = _world(settings, None)

    stored = _materialised(built, _root_only())

    assert len(_gists_asked(built)) == 1
    assert stored.gist == "rename this"


def test_while_claude_is_disabled_nothing_is_asked_and_no_gist_written(settings):
    built = _world(settings, "rename the helper")

    stored = _materialised(built, _root_only(), agents_enabled=False)

    assert _gists_asked(built) == []
    assert stored.gist == "rename this"
