from collections.abc import Callable
from dataclasses import dataclass

from github_orchestrator.change_detection import Poll
from github_orchestrator.conversation import ConversationManagerFactory, ThreadActivity
from github_orchestrator.domain import Pr
from github_orchestrator.github import PullRequests
from github_orchestrator.notifications import ThreadNews


@dataclass(frozen=True)
class Fetched:
    poll: Poll
    activity: ThreadActivity | None
    announce: Callable[[ThreadNews], None]
    commit: Callable[[], None]


def fetch_pr_state(github: PullRequests, conversation_managers: ConversationManagerFactory, pr: Pr, *,
                   review_requested: bool, mentioned: bool) -> Fetched:
    state = github.pr_state(pr)
    polled = conversation_managers.of(pr).poll(state)
    return Fetched(
        poll=Poll(
            state=state,
            polled_at=polled.polled_at,
            my_last_comment_at=polled.my_last_comment_at,
            comments_by_others=polled.comments_by_others,
            unresolved_thread_count=polled.unresolved_count,
            mentions=polled.mentions,
            review_requested=review_requested,
            mentioned=mentioned,
        ),
        activity=polled.activity,
        announce=polled.announce,
        commit=polled.commit,
    )
