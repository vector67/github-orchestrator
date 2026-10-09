import logging
import threading

from github_orchestrator.conversation._application.ports import Ports
from github_orchestrator.conversation._application.runner import run
from github_orchestrator.conversation._domain.conversation import (
    REMOVED,
    Conversation,
)
from github_orchestrator.conversation._domain.events import RootGone
from github_orchestrator.domain import Pr

log = logging.getLogger(__name__)

PRESENCE_TTL_SECONDS = 60

Entry = tuple[Pr, str, int | None]


def _worth_checking(conversation: Conversation) -> bool:
    return (bool(conversation.comment_type)
            and conversation.state != REMOVED
            and not conversation.comment_deleted)


def _entry(pr: Pr, conversation: Conversation) -> Entry:
    return (pr, conversation.comment_type, conversation.comment_id)


class Presence:
    def __init__(self) -> None:
        self.memo: dict[Entry, tuple[float, bool]] = {}
        self.asking: dict[Entry, threading.Thread] = {}
        self.lock = threading.Lock()

    def check_later(self, pr: Pr, key: str, ports: Ports) -> None:
        """Run `check` off the caller's thread; nothing waits for the answer.

        The panel's GET is an interactive request and `gh api` is a second on
        the wire. A comment GitHub has lost lands on the record here, and the
        board's next poll is what draws it.
        """
        conversation = ports.records.load(key)
        if conversation is None or not _worth_checking(conversation):
            return
        entry = _entry(pr, conversation)
        thread = threading.Thread(target=self._asked, name="presence",
                                  args=(entry, pr, key, ports),
                                  daemon=True)
        with self.lock:
            if entry in self.asking:
                return
            self.asking[entry] = thread
        thread.start()

    def _asked(self, entry: Entry, pr: Pr, key: str,
               ports: Ports) -> None:
        try:
            self.check(pr, key, ports)
        except Exception:
            log.exception("could not check %s comment %s on GitHub",
                          pr, key)
        finally:
            with self.lock:
                self.asking.pop(entry, None)

    def check(self, pr: Pr, key: str,
              ports: Ports) -> Conversation | None:
        conversation = ports.records.load(key)
        if conversation is None or not _worth_checking(conversation):
            return conversation
        if self._exists(pr, conversation, ports) is not False:
            return conversation
        with ports.records.update(key) as update:
            stored = update.conversation
            if stored is None:
                return conversation
            outcome = run(ports, stored, RootGone())
            if outcome.conversation != stored:
                update.conversation = outcome.conversation
            return outcome.conversation

    def _exists(self, pr: Pr, conversation: Conversation,
                ports: Ports) -> bool | None:
        entry = _entry(pr, conversation)
        now = ports.clock.monotonic()
        with self.lock:
            hit = self.memo.get(entry)
        if hit is not None and now - hit[0] < PRESENCE_TTL_SECONDS:
            return hit[1]
        present = ports.github.comment_exists(conversation)
        if present is None:
            return None
        with self.lock:
            for stale in [key for key, (stamp, _) in list(self.memo.items())
                          if now - stamp >= PRESENCE_TTL_SECONDS]:
                self.memo.pop(stale, None)
            self.memo[entry] = (now, present)
        return present
