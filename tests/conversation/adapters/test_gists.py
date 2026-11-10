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
GIST_ASK_CHARS = 45
LONG = "rename this helper, since its name no longer says what it does"
LONG_FALLBACK = "rename this helper, since its name no longer says what it d…"


def _comment(comment_id, author, body):
    return ThreadComment(id=comment_id, author=author, body=body,
                         created_at="2026-09-01T10:00:00Z",
                         updated_at="2026-09-01T10:00:00Z")


def _root_only(path="src/foo.py", line=4, body=LONG):
    kind = CommentKind.REVIEW if path else CommentKind.ISSUE
    return Thread(key="PRRT_1", kind=kind, path=path, line=line,
                  comments=(_comment(1, "reviewer", body),))


def _answered(thread, reply="which one?"):
    return Thread(key=thread.key, kind=thread.kind, path=thread.path, line=thread.line,
                  comments=(*thread.comments, _comment(2, "me", reply)))


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
        CommentAsked("PRRT_1", "src/foo.py", 4, LONG, GIST_ASK_CHARS)]
    assert stored.gist == "rename the helper"


def test_a_comment_on_no_line_is_summarised_with_no_place(settings):
    built = _world(settings)

    _materialised(built, _root_only(path=None, line=None))

    assert _gists_asked(built) == [
        CommentAsked("PRRT_1", None, None, LONG, GIST_ASK_CHARS)]


def test_a_thread_gist_summarises_every_comment_in_order(settings):
    built = _world(settings, None, None, "say which helper")
    thread = _root_only()
    _materialised(built, thread)

    stored = _materialised(built, _answered(thread))

    assert _gists_asked(built)[1] == ThreadAsked(
        "PRRT_1", "src/foo.py", 4, (("reviewer", LONG), ("me", "which one?")),
        GIST_ASK_CHARS)
    assert stored.gist == "say which helper"


def test_a_long_gist_is_clipped(settings):
    built = _world(settings, "b" * 90)

    stored = _materialised(built, _root_only())

    assert len(stored.gist) == GIST_MAX_CHARS and stored.gist.endswith("…")


def test_a_gist_the_model_would_not_write_leaves_the_fallback(settings):
    built = _world(settings, None)

    stored = _materialised(built, _root_only())

    assert len(_gists_asked(built)) == 1
    assert stored.gist == LONG_FALLBACK


def test_while_claude_is_disabled_nothing_is_asked_and_no_gist_written(settings):
    built = _world(settings, "rename the helper")

    stored = _materialised(built, _root_only(), agents_enabled=False)

    assert _gists_asked(built) == []
    assert stored.gist == LONG_FALLBACK


def test_the_gist_label_and_trailing_period_are_dropped(settings):
    built = _world(settings, "gist: rename the helper.")

    stored = _materialised(built, _root_only())

    assert stored.gist == "rename the helper"


def test_a_root_comment_that_fits_on_one_line_is_its_own_gist(settings):
    built = _world(settings, "rename the helper")

    stored = _materialised(built, _root_only(body="rename this"))

    assert _gists_asked(built) == []
    assert stored.gist == "rename this"


def test_a_short_root_comment_on_two_lines_is_summarised(settings):
    built = _world(settings, "rename the helper")

    stored = _materialised(built, _root_only(body="rename this\nand that"))

    assert len(_gists_asked(built)) == 1
    assert stored.gist == "rename the helper"


def test_a_thread_that_fits_together_is_not_summarised(settings):
    built = _world(settings)
    thread = _root_only(body="rename this")
    _materialised(built, thread)

    stored = _materialised(built, _answered(thread))

    assert _gists_asked(built) == []
    assert stored.gist == "rename this"


def test_a_short_comment_with_a_long_reply_is_summarised_as_a_thread(settings):
    built = _world(settings, None, "say which helper")
    thread = _root_only(body="rename this")
    _materialised(built, thread)

    stored = _materialised(built, _answered(thread, reply=LONG))

    assert [type(asked) for asked in _gists_asked(built)] == [ThreadAsked]
    assert stored.gist == "say which helper"


def test_the_gists_first_word_is_lowercased_but_an_identifier_keeps_its_case(settings):
    lowered = _materialised(_world(settings, "gist: Rename the helper"), _root_only())
    kept = _materialised(_world(settings, "gist: WIDGET_KEYS should be reused"), _root_only())

    assert (lowered.gist, kept.gist) == ("rename the helper", "WIDGET_KEYS should be reused")
