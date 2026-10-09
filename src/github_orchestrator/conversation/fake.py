import time
from collections.abc import Callable
from datetime import datetime, timezone

from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.change_detection import Poll
from github_orchestrator.change_detection.fake import FakeChangeDetection
from github_orchestrator.conversation._application.settings import ThreadsConfig
from github_orchestrator.conversation._threads import GitHubConversationManagerFactory
from github_orchestrator.conversation.interface import ConversationManager
from github_orchestrator.domain import Monotonic, Pr, UtcClock
from github_orchestrator.github import PullRequestState
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.thread_records.fake import FakeThreadRecords
from github_orchestrator.working_copies.fake import FakeWorkingCopies


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FakeConversationManagerFactory:
    def __init__(self, agent_runs: FakeAgentRuns, config: ThreadsConfig, *,
                 github: FakeGitHub | None = None,
                 working_copies: FakeWorkingCopies | None = None,
                 clock: Callable[[], datetime] = _now,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.github = github or FakeGitHub(config.gh_account)
        self.working_copies = working_copies or FakeWorkingCopies(self.github)
        self.agent_runs = agent_runs
        self.thread_records = FakeThreadRecords()
        self._clock = clock
        self._change_detection = FakeChangeDetection(config.gh_account, config.poll_interval,
                                                     clock)
        self._threads = GitHubConversationManagerFactory(
            self.github, self.github, self.github, self.working_copies, agent_runs,
            agent_runs, agent_runs, self.thread_records, self._change_detection, config,
            UtcClock(clock), Monotonic(monotonic))

    def of(self, pr: Pr) -> ConversationManager:
        return self._threads.of(pr)

    def watch(self, pr: Pr, *, is_author: bool, title: str | None = None,
              base_branch: str | None = "main", head_sha: str | None = None,
              branch: str | None = None) -> None:
        author = self.github.account if is_author else f"not-{self.github.account}"
        state = PullRequestState(title=title, author=author, base_branch=base_branch,
                                 head_sha=head_sha, branch=branch)
        record = self.github.prs.get(pr)
        if record is None:
            self.github.add_pr(pr, state)
        else:
            record.state = state
        self._change_detection.advance(
            pr, Poll(state=self.github.pr_state(pr), polled_at=self._clock().isoformat()),
            set())

    def hear(self, pr: Pr) -> None:
        state = self.github.pr_state(pr)
        threads = self.of(pr)
        polled = threads.poll(state)
        polled.commit()
        if polled.activity is not None:
            threads.absorb(polled.activity)
        self._change_detection.advance(
            pr, Poll(state=state, polled_at=self._clock().isoformat(), mentions=polled.mentions),
            set())
