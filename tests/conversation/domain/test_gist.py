from collections.abc import Callable
from dataclasses import dataclass, field

from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import fake_settings
from tests.conversation.support import (
    WORKTREE,
    hear,
    on_github,
    repo_at,
    said,
    world,
)

KEY = "PRRT_one"
GIST_CAP = 60


@dataclass
class LaterSummaries(FakeAgentRuns):
    pending: list[Callable[[], None]] = field(default_factory=list)

    def summarize_comment(self, key, path, line, body, done, *, chars):
        self.pending.append(lambda: FakeAgentRuns.summarize_comment(
            self, key, path, line, body, done, chars=chars))

    def summarize_thread(self, key, path, line, comments, done, *, chars):
        self.pending.append(lambda: FakeAgentRuns.summarize_thread(
            self, key, path, line, comments, done, chars=chars))

    def settle(self) -> None:
        while self.pending:
            self.pending.pop(0)()


def _heard(here, body, *, is_author=None):
    on_github(here.github, KEY, said(5001, body), path="src/app.py", line=12)
    hear(here.threads(is_author=is_author))


def _summary(settings, body, *answers):
    agent_runs = LaterSummaries(FakePrProcesses())
    here = world(settings, agent_runs=agent_runs)
    repo_at(here.working_copies, WORKTREE)
    agent_runs.answer(*answers)
    _heard(here, body)
    agent_runs.settle()
    return here.load(KEY).gist


def test_the_summary_is_the_first_non_empty_line_until_claude_answers(settings):
    assert _summary(settings, "\n\nplease rename this\nand that") == "please rename this"


def test_the_summary_skips_a_leading_code_fence_block(settings):
    assert _summary(settings, "```python\nx = 1\n```\nthe real point") == "the real point"


def test_the_summary_clips_to_the_cap_with_an_ellipsis(settings):
    summary = _summary(settings, "a" * 100)

    assert len(summary) == GIST_CAP
    assert summary.endswith("…")


def test_the_summary_of_an_empty_body_is_empty(settings, tmp_path):
    assert _summary(settings, "") == ""
    assert _summary(fake_settings(tmp_path / "fenced"), "```\n```") == ""


def test_claudes_answer_replaces_the_first_line(settings):
    assert _summary(settings, "rename this\nplease", "rename the reference") == "rename the reference"


def test_claudes_answer_is_clipped_to_the_cap_too(settings):
    summary = _summary(settings, "rename this", "b" * 100)

    assert len(summary) == GIST_CAP
    assert summary.endswith("…")


def test_with_claude_disabled_nothing_is_asked_and_the_first_line_stays(tmp_path):
    agent_runs = LaterSummaries(FakePrProcesses())
    here = world(fake_settings(tmp_path, agents_enabled=False), agent_runs=agent_runs)
    repo_at(here.working_copies, WORKTREE)
    agent_runs.answer("rename the reference")

    _heard(here, "rename this\nplease", is_author=False)
    agent_runs.settle()

    assert agent_runs.asked == []
    assert here.load(KEY).gist == "rename this"
