import datetime
import sys

from github_orchestrator.agent_runs import History
from github_orchestrator.cli._config import CliConfig, Run, print_agents_disabled_notice
from github_orchestrator.cli._service import Service
from github_orchestrator.cli._tail import follow, print_tail, tail_command
from github_orchestrator.settings import ConfigFile, Logs, Process

LOGS = {"watcher": Process.WATCHER, "agent": Process.PR_MANAGER}


def logs(files: Logs, service: Service, run: Run, which: str | None, lines: int | None,
         *, following: bool = False) -> None:
    which = which or "watcher"
    n = lines or 20
    if following and which == "all":
        print("logs -f follows one log at a time: watcher, agent or service.", file=sys.stderr)
        sys.exit(2)
    if following:
        if which == "service":
            service.show_log(n, following=True)
        else:
            follow(run, tail_command(files.path(LOGS[which]), n))
        return
    targets = [*LOGS, "service"] if which == "all" else [which]
    for i, target in enumerate(targets):
        if i:
            print()
        if target == "service":
            service.show_log(n)
        else:
            print_tail(files.path(LOGS[target]), n)


def _duration(seconds: float) -> str:
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def runs(config: CliConfig, config_file: ConfigFile, now: datetime.datetime, *,
         history: History) -> None:
    today = now.date()
    day = history.finished_today(now)
    finished = day.finished

    total = sum(run.elapsed_seconds for run in finished)
    cost = day.cost_usd
    money = "" if cost is None else f", ~${cost:.2f} API-equivalent"
    print(f"Runs today ({today}): {len(finished)} runs, {_duration(total)} total{money}")
    if cost is not None:
        print("  runs bill against the subscription, not the API — this is what "
              "the same work would have cost")
    unpriced = day.unpriced
    if cost is not None and unpriced:
        plural = "" if unpriced == 1 else "s"
        print(f"  {unpriced} run{plural} ended without reporting a cost — the total is a floor")
    if finished:
        longest = max(finished, key=lambda run: run.elapsed_seconds)
        print(
            f"  longest: {longest.event} on {'?' if longest.pr is None else longest.pr} "
            f"— {_duration(longest.elapsed_seconds)}"
        )
    print_agents_disabled_notice(config, config_file)
