from collections.abc import Callable

from github_orchestrator.agent_runs import Summaries
from github_orchestrator.conversation._domain.conversation import (
    Conversation,
    ThreadVerdict,
)
from github_orchestrator.conversation._domain.effects import GIST_ROOT, GIST_THREAD
from github_orchestrator.conversation._domain.gist import GIST_MAX_CHARS, clip
from github_orchestrator.conversation._domain.verdict import MEANINGS, facts_of

ANSWERS = {verdict.value: MEANINGS[verdict] for verdict in ThreadVerdict}


class Gists:
    def __init__(self, summaries: Summaries, enabled: bool, viewer: str,
                 pr_author: Callable[[], str | None]) -> None:
        self.summaries = summaries
        self.enabled = enabled
        self.viewer = viewer
        self.pr_author = pr_author

    def ask_verdict(self, conversation: Conversation,
                    done: Callable[[ThreadVerdict], None]) -> None:
        if not self.enabled:
            return
        facts = facts_of(conversation, self.viewer, self.pr_author())
        self.summaries.judge_thread(
            conversation.key, facts.comments, viewer=facts.viewer, pr_author=facts.pr_author,
            spoke_last=facts.spoke_last, viewer_commented=facts.viewer_commented,
            mentions_viewer=facts.mentions_viewer, kind=facts.kind, answers=ANSWERS,
            done=lambda word: done(ThreadVerdict(word)))

    def write_gist(self, conversation: Conversation, source: str,
                   done: Callable[[str], None]) -> None:
        if not self.enabled:
            return
        if source == GIST_ROOT:
            self.summaries.summarize_comment(
                conversation.key, conversation.path, conversation.line, conversation.body,
                lambda gist: done(clip(gist)), chars=GIST_MAX_CHARS)
            return
        if source == GIST_THREAD:
            self.summaries.summarize_thread(
                conversation.key, conversation.path, conversation.line,
                [(comment.author, comment.body) for comment in conversation.comments],
                lambda gist: done(clip(gist)), chars=GIST_MAX_CHARS)
            return
        raise NotImplementedError(source)
