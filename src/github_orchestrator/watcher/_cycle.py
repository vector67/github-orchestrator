import fcntl
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import IO, Protocol

from github_orchestrator.board_api import Hub
from github_orchestrator.change_detection import ChangeDetection, PrClosed, PrEvent
from github_orchestrator.conversation import ConversationManagerFactory, ThreadActivity
from github_orchestrator.domain import HubState, Pr, Sleep, UtcClock
from github_orchestrator.github import PullRequests
from github_orchestrator.notifications import Courier
from github_orchestrator.pr_event_queue import Intake, Worklist
from github_orchestrator.pr_processes import ManagerPane, PrProcesses
from github_orchestrator.settings import Dismissals
from github_orchestrator.watcher._config import WatcherConfig
from github_orchestrator.watcher._failures import clear_failures
from github_orchestrator.watcher._holdings import WatchedHoldings
from github_orchestrator.watcher._leaving import Leaving
from github_orchestrator.watcher._placing import Placement
from github_orchestrator.watcher._poll import Fetched, fetch_pr_state
from github_orchestrator.watcher._saving import Saving
from github_orchestrator.watcher._teardown import Reason, Teardown
from github_orchestrator.watcher.interface import Releases

log = logging.getLogger(__name__)

DELIVERY_INTERVAL = 2
CONFIG_CHECK_SECONDS = 2
WAKE_GAP = timedelta(seconds=30)
MENTIONS_EVERY = timedelta(seconds=60)


class PrSearchError(RuntimeError):
    pass


class Say(Protocol):
    def __call__(self, line: str, /) -> None: ...


def said_to_the_log(line: str) -> None:
    log.debug(line)


class PollingWatcher:
    def __init__(self, config: WatcherConfig, clock: UtcClock,
                 sleep: Sleep, *, pull_requests: PullRequests,
                 courier: Courier, intake: Intake, worklist: Worklist,
                 pr_processes: PrProcesses, conversation_managers: ConversationManagerFactory,
                 change_detection: ChangeDetection, dismissals: Dismissals, hub: Hub,
                 holdings: WatchedHoldings, placement: Placement,
                 teardown: Teardown, saving: Saving, say: Say, leaving: Leaving,
                 releases: Releases) -> None:
        self._config = config
        self._clock = clock
        self._sleep = sleep
        self._pull_requests = pull_requests
        self._courier = courier
        self._woke_at = clock()
        self._polled_at: datetime | None = None
        self._mentions_searched_at: datetime | None = None
        self._mentioned: list[Pr] = []
        self._intake = intake
        self._worklist = worklist
        self._pr_processes = pr_processes
        self._conversation_managers = conversation_managers
        self._change_detection = change_detection
        self._dismissals = dismissals
        self._lock: IO[str] | None = None
        self._hub = hub
        self._hub_url: str | None = None
        self._hub_refused: str | None = None
        self._holdings = holdings
        self._placement = placement
        self._teardown = teardown
        self._saving = saving
        self._say = say
        self._leaving = leaving
        self._releases = releases

    def run_cycle(self) -> None:
        try:
            print(self._polled())
        except Exception as exc:
            log.exception("Watcher failed")
            self._saving.failed(exc)
            raise
        finally:
            self._deliver()

    def take_lock(self) -> bool:
        self._config.lock.parent.mkdir(parents=True, exist_ok=True)
        lock = open(self._config.lock, "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            return False
        self._lock = lock
        return True

    def run_forever(self) -> None:
        log.info("--- watcher daemon started (interval=%ss) ---", self._config.poll_interval)
        while not self._leaving.asked():
            self._serve_hub(HubState.WATCHING)
            self._releases.check_if_due()
            try:
                self._polled()
            except Exception as exc:
                log.exception("Watcher cycle failed; continuing")
                self._saving.failed(exc)
            self._rest()
        log.info("setup changed the config; stopping so the service starts the watcher again")
        self._hub.stop()

    def wait_in(self, state: HubState, current: Callable[[], HubState]) -> None:
        log.info("--- watcher serving the hub alone, in %s ---", state)
        try:
            clear_failures(self._config.failures)
        except OSError as exc:
            log.warning("Could not clear %s: %s", self._config.failures, exc)
        while (now := current()) is state and not self._leaving.asked():
            self._serve_hub(state)
            self._releases.check_if_due()
            self._sleep(CONFIG_CHECK_SECONDS)
        log.info("the config is %s now; stopping so the service starts the watcher again", now)
        self._hub.stop()

    def _serve_hub(self, state: HubState) -> None:
        if self._hub_url is not None:
            return
        port = self._config.hub_port
        try:
            self._hub_url = self._hub.start(port, self._holdings, state)
        except OSError as exc:
            if str(exc) != self._hub_refused:
                log.error("the hub will not start on %s (%s); trying again until it does",
                          port, exc)
                self._hub_refused = str(exc)
            return
        log.info("hub at %s", self._hub_url)

    def _polled(self) -> str:
        started = self._clock()
        summary = self._cycle()
        self._polled_at = started
        return summary

    def _rest(self) -> None:
        for _ in range(self._config.poll_interval // DELIVERY_INTERVAL):
            if self._leaving.asked():
                return
            self._deliver()
            before = self._clock()
            self._sleep(DELIVERY_INTERVAL)
            after = self._clock()
            if after - before > WAKE_GAP:
                log.info("woke after %s asleep; batches due meanwhile wait for the next poll",
                         after - before)
                self._woke_at = after

    def _deliver(self) -> None:
        try:
            self._courier.deliver(self._woke_at, self._polled_at)
        except Exception:
            log.exception("Could not deliver the notifications")

    def _enqueue_unless_dismissed_forever(self, pr: Pr, item: PrEvent | ThreadActivity) -> bool:
        if self._dismissals.is_dismissed_forever(pr):
            log.debug("Dropping %s for %s — dismissed forever", item.kind, pr)
            return False
        if isinstance(item, ThreadActivity):
            self._intake.add_thread_activity(pr, item)
        else:
            self._intake.add(pr, item)
        return True

    def _enqueue_events(self, items: list[PrEvent | ThreadActivity], pr: Pr) -> int:
        count = 0
        for item in items:
            if not self._enqueue_unless_dismissed_forever(pr, item):
                continue
            log.info("Event: %s for %s", item.kind, pr)
            count += 1
        return count

    def _fetch(self, pr: Pr, review_requested: bool) -> Fetched:
        log.debug("Polling %s (review_requested=%s)", pr, review_requested)
        return fetch_pr_state(self._pull_requests, self._conversation_managers, pr,
                              review_requested=review_requested,
                              mentioned=pr in self._mentioned)

    def _advance(self, pr: Pr, fetched: Fetched) -> tuple[int, bool]:
        pending_ci_checks = set(self._worklist.waiting(pr).failed_checks)
        events = self._change_detection.advance(pr, fetched.poll, pending_ci_checks)
        queued: list[PrEvent | ThreadActivity] = list(events)
        if fetched.activity is not None:
            queued.append(fetched.activity)
        events_queued = self._enqueue_events(queued, pr)
        self._saving.threads_seen(pr, fetched)
        log.debug("Poll complete for %s: %d events queued", pr, events_queued)
        return events_queued, any(event.moves_head for event in events)

    def _mentions_due(self, now: datetime) -> bool:
        searched = self._mentions_searched_at
        return searched is None or now - searched >= MENTIONS_EVERY

    def _watched(self) -> str:
        return ", ".join(sorted(str(repo) for repo in self._config.repos))

    def _discover_prs(self) -> tuple[list[Pr], list[Pr]]:
        config = self._config
        repos = list(config.repos)
        now = self._clock()
        with ThreadPoolExecutor(max_workers=3) as pool:
            my_future = pool.submit(self._pull_requests.search, repos, "author")
            review_future = pool.submit(self._pull_requests.search, repos, "review-requested")
            mentions_future = (pool.submit(self._pull_requests.search, repos, "mentions")
                               if self._mentions_due(now) else None)
            try:
                found = my_future.result(), review_future.result()
                if mentions_future is not None:
                    self._mentioned = mentions_future.result()
                    self._mentions_searched_at = now
                return found
            except Exception as exc:
                raise PrSearchError(
                    f"watcher cannot search {self._watched()} as {config.gh_account} — check "
                    f"[[repos]] and gh_account in {config.config_location}; {exc}"
                ) from exc

    def _tracked_in_watched_repos(self) -> list[Pr]:
        return [pr for pr in self._change_detection.tracked() if pr.repo in self._config.repos]

    def _left_the_search(self, searched: set[Pr]) -> tuple[list[Pr], dict[Pr, PrClosed]]:
        engaged: list[Pr] = []
        ended: dict[Pr, PrClosed] = {}
        for pr in self._tracked_in_watched_repos():
            if pr in searched or self._change_detection.closing(pr):
                continue
            try:
                relevance = self._pull_requests.relevance(pr)
            except Exception:
                log.exception("Failed to verify state for %s; skipping", pr)
                continue
            if relevance is None:
                log.warning("GraphQL returned no PR data for %s; skipping", pr)
                continue
            if relevance.is_open and (relevance.viewer_did_author or relevance.viewer_reviewed
                                      or self._mentioned_before(pr)):
                engaged.append(pr)
            else:
                ended[pr] = self._change_detection.ended(still_open=relevance.is_open,
                                                         merged=relevance.merged)
        return engaged, ended

    def _mentioned_before(self, pr: Pr) -> bool:
        facts = self._change_detection.facts(pr)
        return facts is not None and facts.mentioned

    def _held(self, my_prs: list[Pr], review_prs: list[Pr],
              engaged: list[Pr]) -> dict[Pr, bool]:
        held: dict[Pr, bool] = {}
        for pr in review_prs:
            if not self._dismissals.is_dismissed_forever(pr):
                held[pr] = True
        for pr in my_prs + self._mentioned + engaged:
            if not self._dismissals.is_dismissed_forever(pr) and pr not in held:
                held[pr] = False
        return held

    def _poll_all_prs(self, to_poll: dict[Pr, bool]) -> int:
        total_events = 0
        self._pull_requests.prefetch(list(to_poll))

        moved_heads: set[Pr] = set()
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(self._fetch, pr, review_requested): pr
                for pr, review_requested in to_poll.items()
            }
            for future in as_completed(futures):
                pr = futures[future]
                try:
                    count, head_moved = self._advance(pr, future.result())
                except Exception:
                    log.exception("Failed to poll %s", pr)
                    continue
                total_events += count
                if head_moved:
                    moved_heads.add(pr)

        for pr in to_poll:
            try:
                self._placement.ensure(pr, fetch=pr in moved_heads)
            except Exception:
                log.exception("Failed to ensure window for %s", pr)

        return total_events

    def _detect_closed_prs(self, found: set[Pr], ended: dict[Pr, PrClosed]) -> int:
        closed = 0
        for pr in self._tracked_in_watched_repos():
            if pr in found or not self._change_detection.closing(pr):
                continue
            try:
                if self._teardown.reap(pr, Reason.CLOSED):
                    closed += 1
            except Exception:
                log.exception("Failed to reap %s; will retry next cycle", pr)

        for pr, ending in ended.items():
            try:
                if ending.no_longer_relevant:
                    log.info("PR no longer relevant: %s", pr)
                else:
                    log.info("PR closed: %s", pr)

                if self._enqueue_unless_dismissed_forever(pr, ending):
                    self._change_detection.close(pr)
                elif not self._teardown.reap(pr, Reason.CLOSED):
                    continue
                closed += 1
            except Exception:
                log.exception("Failed to handle closed PR %s; continuing", pr)
                continue
        return closed

    def _tear_down_dismissed(self, prs: list[Pr]) -> int:
        torn_down = 0
        for pr in dict.fromkeys(prs):
            if not self._dismissals.is_dismissed_forever(pr):
                continue
            if self._pr_processes.manager(pr) is ManagerPane.NO_WINDOW:
                continue
            try:
                if self._teardown.reap(pr, Reason.DISMISSED):
                    torn_down += 1
            except Exception:
                log.exception("Failed to tear down dismissed %s; will retry next cycle", pr)
        return torn_down

    def _cycle(self) -> str:
        config = self._config
        log.debug("--- watcher start ---")
        self._say(f"searching {self._watched()} for PRs by and for {config.gh_account}…")
        my_prs, review_prs = self._discover_prs()
        self._say(f"found {len(my_prs)} authored, {len(review_prs)} to review, "
                  f"{len(self._mentioned)} mentioning you")
        engaged, endings = self._left_the_search(set(my_prs + review_prs + self._mentioned))
        found = my_prs + review_prs + self._mentioned + engaged
        held = self._held(my_prs, review_prs, engaged)
        total_events = self._poll_all_prs(held)
        torn_down = (self._detect_closed_prs(set(found), endings)
                     + self._tear_down_dismissed(found))
        self._hub.show(list(held))
        self._placement.revive_pending()
        self._saving.polled()
        log.debug("--- watcher end ---")

        summary = (f"Polled {len(set(found))} PRs, {total_events} events queued, "
                   f"{torn_down} torn down")
        log.info(summary)
        return summary
