import sys
from datetime import datetime, timedelta

from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.cli._config import CliConfig, print_agents_disabled_notice
from github_orchestrator.cli._hub import HealthBody, HubHealth
from github_orchestrator.cli._update import UPDATE, newer_release
from github_orchestrator.domain import HubState, Pr
from github_orchestrator.pr_event_queue import Queues
from github_orchestrator.settings import ConfigFile, Dismissals, Holds
from github_orchestrator.watcher import Health, Releases, WatcherHealth


def _pr_marks(holds: Holds, dismissals: Dismissals, pr: Pr) -> str:
    marks = []
    if holds.on_hold(pr):
        marks.append("[ON HOLD]")
    dismissal = dismissals.dismissal(pr)
    if dismissal is not None:
        marks.append(f"[DISMISSED {dismissal.value}]")
    return "".join(f"  {mark}" for mark in marks)


def _queue_stall_note(holds: Holds, dismissals: Dismissals, pr: Pr) -> str:
    if holds.on_hold(pr):
        return "  (on hold - nothing will run)"
    if dismissals.is_dismissed_forever(pr):
        return "  (dismissed - nothing will run)"
    return ""


def ago(elapsed: timedelta) -> str:
    total = int(elapsed.total_seconds())
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m"
    return f"{total // 3600}h"


def _health_line(health: Health, alive: bool) -> str:
    since = health.since_last_poll
    if health.last_error is not None:
        succeeded = ("no cycle has ever succeeded" if since is None
                     else f"last good poll {ago(since)} ago")
        state = "failing" if alive else "not running"
        return (f"Watcher: {state} — {succeeded}; "
                f"last error: {' '.join(health.last_error.split())}")
    every = ago(health.polls_every)
    if since is None:
        return ("Watcher: running but no cycle has ever succeeded — no poll recorded yet"
                if alive else "Watcher: not running, no poll recorded yet")
    if not alive:
        return f"Watcher: not running — last polled {ago(since)} ago"
    if health.overdue:
        return f"Watcher: running but has not polled for {ago(since)} (expected every {every})"
    return f"Watcher: alive, last polled {ago(since)} ago"


def _version_line(config: CliConfig, answer: HealthBody | None) -> str:
    version = config.version if answer is None else answer.get("version")
    instance = "default instance" if config.instance is None else f"instance {config.instance}"
    return f"github-orchestrator {version or '(version unknown)'} ({instance})"


def _repos(count: int) -> str:
    return "1 repo" if count == 1 else f"{count} repos"


def _hub_line(config: CliConfig, config_file: ConfigFile, answer: HealthBody | None,
              health: Health) -> str:
    hub_url = config.hub_url
    if answer is None:
        if not health.alive:
            return f"Hub: {hub_url} — down while the watcher is not running"
        return f"Hub: {hub_url} — not answering"
    match answer.get("state"):
        case HubState.SETUP:
            return f"Hub: {hub_url}, in setup — {config_file.check()}"
        case HubState.BROKEN:
            return f"Hub: {hub_url}, config broken — {config_file.check()}"
    return f"Hub: {hub_url}, watching {_repos(len(config.repos))}"


def status(config: CliConfig, config_file: ConfigFile, *, queues: Queues, change_detection: ChangeDetection,
           watcher_health: WatcherHealth, hub_health: HubHealth, holds: Holds,
           dismissals: Dismissals, releases: Releases) -> None:
    health = watcher_health.health()
    answer = hub_health(config.hub_url)
    print(_version_line(config, answer))
    newer = newer_release(config, answer, releases)
    if newer is not None:
        print(f"Update available: {newer}. Run {UPDATE}.")
    print(_hub_line(config, config_file, answer, health))
    watching = answer is not None and answer.get("state") == HubState.WATCHING
    if answer is not None and not watching:
        print("Watcher: running, polling nothing until the config is complete")
    else:
        print(_health_line(health, alive=answer is not None or health.alive))
    print_agents_disabled_notice(config, config_file)
    if config.font_problem is not None:
        print(f"Font: {config.font_problem}")
    print()

    stored = change_detection.stored()
    print(f"Tracked PRs: {len(stored)}")
    for entry in stored:
        facts = entry.facts
        if facts is None:
            print(f"  {entry.pr}  [corrupt state file: {entry.problem}]")
            continue
        marks = _pr_marks(holds, dismissals, entry.pr)
        ci = "?" if facts.ci_status is None else facts.ci_status.value
        mergeable = "?" if facts.mergeable is None else facts.mergeable
        review = None if facts.review_decision is None else facts.review_decision.value
        print(f"  {entry.pr}  ci={ci}  mergeable={mergeable}  "
              f"review={review}{marks}")

    tracked = {entry.pr for entry in stored}
    untracked = []
    for pr in sorted((holds.on_hold_prs() | dismissals.dismissed_prs()) - tracked):
        marks = _pr_marks(holds, dismissals, pr)
        if marks:
            untracked.append(f"    {pr}{marks}")
    if untracked:
        print()
        print("  On hold or dismissed, not tracked (no state file):")
        for line in untracked:
            print(line)
        print()

    total_pending = 0
    for queued in queues.queues():
        count = len(queued.pending) + len(queued.in_flight)
        if count > 0:
            total_pending += count
            note = _queue_stall_note(holds, dismissals, queued.pr)
            print(
                f"  Queue {queued.pr}: {len(queued.pending)} pending, "
                f"{len(queued.in_flight)} processing{note}"
            )
    if total_pending == 0:
        print("  Queues: empty")
    healthy = (health.last_error is None and health.since_last_poll is not None
               and not health.overdue)
    if not (watching and healthy):
        sys.exit(1)


def _when(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def queue(number: int, *, queues: Queues) -> None:
    matches = [queued for queued in queues.queues() if queued.pr.number == number]

    if not matches:
        print(f"No queue found for a PR numbered {number}")
        return

    for queued in matches:
        print(f"Queue: {queued.pr}")

        for entry in queued.in_flight:
            if entry.event is None:
                print(f"  [PROCESSING] [corrupt: {entry.problem}]")
                continue
            print(f"  [PROCESSING] {entry.event.kind}")

        if queued.pending:
            for entry in queued.pending:
                if entry.event is None:
                    print(f"  [corrupt: {entry.problem}]  queued {_when(entry.queued_at)}")
                    continue
                print(f"  [{entry.event.kind}]  queued {_when(entry.queued_at)}")
        elif not queued.in_flight:
            print("  (empty)")


def undismiss(pr: Pr, *, change_detection: ChangeDetection, dismissals: Dismissals) -> None:
    if dismissals.undismiss(pr):
        print(
            f"Cleared dismissal for {pr}; "
            "the window reopens on the next poll cycle (~1 min)."
        )
        return
    print(f"{pr} was not dismissed — nothing to do.")
    if pr not in change_detection.tracked():
        print(
            f"The watcher is not tracking {pr} yet — "
            "no window opens until it discovers that PR.",
            file=sys.stderr,
        )
