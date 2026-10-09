import logging

from github_orchestrator.conversation._application.ports import (
    Ports,
    thread_workspace,
)
from github_orchestrator.conversation._application.runner import run
from github_orchestrator.conversation._domain.change import Change
from github_orchestrator.conversation._domain.conversation import (
    DEFERRED,
    OPEN,
    PROPOSED,
    QUEUED,
    RUNNING,
    WAKE_CI,
    WAKE_MANUAL,
    WAKE_PR_PREFIX,
    WAKE_PUSH_PREFIX,
    Conversation,
)
from github_orchestrator.conversation._domain.events import (
    RunExited,
    RunLost,
    RunStarted,
    RunTimedOut,
    Wake,
)
from github_orchestrator.domain import Pr

log = logging.getLogger(__name__)


class Runs:
    def __init__(self) -> None:
        self._published_actions: dict[str, str] = {}
        self._closed_answers: dict[int, tuple[float, bool | None]] = {}

    def live_count(self, ports: Ports) -> int:
        return len(ports.agents.live_keys())

    def proposed_count(self, ports: Ports) -> int:
        return sum(1 for conversation in ports.records.list()
                   if conversation.state == OPEN and conversation.fix.state == PROPOSED)

    def queued_count(self, ports: Ports) -> int:
        return sum(1 for conversation in ports.records.list()
                   if _is_queued(conversation))

    def pump_and_schedule(self, pr: Pr, ports: Ports,
                          schedule: bool = True) -> list[Conversation]:
        settled: list[Conversation] = []
        try:
            self._reconcile(pr, ports)
            self._wake(pr, ports)
            settled = self._pump(pr, ports)
            if schedule:
                self._schedule(pr, ports)
        except Exception:
            log.exception("thread runs %s: tick failed", pr)
        return settled

    def _reconcile(self, pr: Pr, ports: Ports) -> None:
        live = ports.agents.live_keys()
        for conversation in ports.records.list():
            if conversation.state != OPEN:
                continue
            if conversation.fix.state != RUNNING or conversation.key in live:
                continue
            try:
                self._apply(ports, conversation.key, RunLost())
            except Exception:
                log.exception("thread runs %s: requeueing stranded %s "
                              "failed", pr, conversation.key)
                continue
            log.warning("thread runs %s: %s was running with no live run "
                        "(manager restart?); requeued", pr,
                        conversation.key)

    def _wake(self, pr: Pr, ports: Ports) -> None:
        wanted = [c for c in ports.records.list()
                 if c.state == DEFERRED and c.wake_on
                 and c.wake_on != WAKE_MANUAL]
        if not wanted:
            return
        for conversation in wanted:
            reason = self._wake_reason(pr, conversation.wake_on, ports)
            if reason is not None:
                self._apply(ports, conversation.key,
                            Wake(reason=reason, at=ports.clock.now()))

    def _pump(self, pr: Pr, ports: Ports) -> list[Conversation]:
        settled: list[Conversation] = []
        for key in sorted(ports.agents.live_keys()):
            try:
                conversation = self._pump_one(pr, key, ports)
            except Exception:
                log.exception("thread runs %s: pumping or settling %s "
                              "failed; abandoning its run", pr, key)
                try:
                    ports.agents.stop_run(key)
                except Exception:
                    log.exception("thread runs %s: stopping %s after a "
                                  "failure also raised", pr, key)
                continue
            if conversation is not None:
                settled.append(conversation)
        return settled

    def _pump_one(self, pr: Pr, key: str,
                  ports: Ports) -> Conversation | None:
        progress = ports.agents.pump(key)
        self._publish_action(pr, key, progress.last_action, ports)
        timeout = ports.config.agent_timeout
        if progress.alive:
            if progress.elapsed > timeout:
                log.warning("thread runs %s: %s exceeded agent_timeout "
                            "(%ds); terminating", pr, key, timeout)
                self._apply(ports, key, RunTimedOut(
                    reason=f"run exceeded agent_timeout ({timeout}s) and was "
                           "terminated", at=ports.clock.now()))
                ports.agents.stop_run(key)
            return None
        return self._settle(pr, key, ports)

    def _publish_action(self, pr: Pr, key: str, line: str | None,
                        ports: Ports) -> None:
        if not line or self._published_actions.get(key) == line:
            return
        try:
            ports.records.write_action(key, line)
        except Exception:
            log.exception("thread runs %s: could not publish %s's action",
                          pr, key)
            return
        self._published_actions[key] = line

    def _settle(self, pr: Pr, key: str,
                ports: Ports) -> Conversation | None:
        with ports.records.update(key) as update:
            conversation = update.conversation
            if conversation is None:
                log.warning("thread runs %s: %s's run exited but its "
                            "record is gone", pr, key)
                return None
            if conversation.state != OPEN or conversation.fix.state != RUNNING:
                return conversation
            fix = conversation.fix
            workspace = thread_workspace(ports, conversation)
            head = workspace.head_sha() if fix.base_sha else None
            descends = bool(
                fix.run.is_rebase and fix.run.onto and head
                and head != fix.run.onto
                and workspace.descends(fix.run.onto, head)
            )
            outcome = run(ports, conversation,
                          RunExited(at=ports.clock.now(), head=head,
                                    descends=descends))
            if outcome.conversation != conversation:
                update.conversation = outcome.conversation
            return outcome.conversation

    def _schedule(self, pr: Pr, ports: Ports) -> None:
        if not ports.config.agents_enabled:
            return
        cap = ports.config.max_thread_runs
        live = ports.agents.live_keys()
        if len(live) >= cap:
            return
        for conversation in ports.records.list():
            if not _is_queued(conversation) or conversation.key in live:
                continue
            if self.live_count(ports) >= cap:
                return
            try:
                self._apply(ports, conversation.key,
                            RunStarted(at=ports.clock.now()))
            except Exception:
                log.exception("thread runs %s: starting a run for %s "
                              "failed", pr, conversation.key)

    def _wake_reason(self, pr: Pr, wake_on: str | None,
                     ports: Ports) -> str | None:
        if wake_on is None:
            return None
        if wake_on == WAKE_CI:
            return "this PR's CI passed" if ports.pull_requests.ci_green() else None
        if wake_on.startswith(WAKE_PUSH_PREFIX):
            head = ports.pull_requests.head_sha()
            if head is None or head == wake_on[len(WAKE_PUSH_PREFIX):]:
                return None
            return "a new push landed"
        if wake_on.startswith(WAKE_PR_PREFIX):
            number = wake_on[len(WAKE_PR_PREFIX):]
            if not number.isdigit():
                return None
            awaited = Pr(pr.repo, int(number))
            closed = self._remembered_closed(awaited.number, ports)
            return f"PR {awaited.in_repo} closed" if closed else None
        return None

    def _remembered_closed(self, number: int, ports: Ports) -> bool | None:
        now = ports.clock.monotonic()
        remembered = self._closed_answers.get(number)
        if (remembered is not None
                and now - remembered[0] < ports.config.poll_interval):
            return remembered[1]
        answer = ports.pull_requests.is_closed(number)
        self._closed_answers[number] = (now, answer)
        return answer

    def _apply(self, ports: Ports, key: str, command: Change) -> None:
        with ports.records.update(key) as update:
            conversation = update.conversation
            if conversation is None:
                return
            outcome = run(ports, conversation, command)
            if outcome.conversation != conversation:
                update.conversation = outcome.conversation


def _is_queued(conversation: Conversation) -> bool:
    return conversation.state == OPEN and conversation.fix.state == QUEUED
