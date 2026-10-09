import argparse

from github_orchestrator.cli._threads import add_thread_parsers, parse_repo

_PROG = "github-orchestrator"

_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("everyday", ("open", "status", "logs", "runs")),
    ("service", ("start", "stop", "restart", "restart-all")),
    ("maintenance", ("update", "doctor", "config", "uninstall", "setup", "skill")),
    ("learning", ("tutorial",)),
)

_DEBUGGING: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("debugging", ("queue", "undismiss")),
)

_ABOUT = (
    "Run and inspect github-orchestrator: set it up, restart and stop the watcher\n"
    "and agent managers, and read their state, queues, runs and logs."
)


class Commands:
    def __init__(self, version: str | None = None) -> None:
        self.parser = argparse.ArgumentParser(
            prog=_PROG,
            usage=f"{_PROG} <command> [options]\n       {_PROG} help [<command>]",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            add_help=False,
        )
        self.parser.add_argument("-h", "--help", action="help", help=argparse.SUPPRESS)
        self.parser.add_argument("--instance", metavar="NAME", help=argparse.SUPPRESS)
        self.parser.add_argument("--version", action="version", help=argparse.SUPPRESS,
                                 version=f"{_PROG} {version or '(version unknown)'}")
        instance = argparse.ArgumentParser(add_help=False)
        instance.add_argument(
            "--instance", metavar="NAME", default=argparse.SUPPRESS,
            help="Act on the instance whose config is ~/.config/github-orchestrator/NAME.toml "
                 "(default: the default instance, or $GITHUB_ORCHESTRATOR_INSTANCE).")
        self._lines: dict[str, str] = {}
        sub = self.parser.add_subparsers(dest="command", metavar="<command>", help=argparse.SUPPRESS)

        def command(name: str, line: str, example: str, more: str = "") -> argparse.ArgumentParser:
            self._lines[name] = line
            return sub.add_parser(
                name, description=f"{line} {more}".strip(), epilog=f"Example: {_PROG} {example}",
                parents=[instance])

        help_parser = command("help", "List the commands, or show one command's help.", "help logs")
        help_parser.add_argument("topic", nargs="?", metavar="<command>", help="The command to explain")

        command(
            "open", "Open this instance's board in the browser.", "open",
            "Starts the watcher first if it is not running, waits for its hub, and always "
            "prints the board's address in case no browser opens.")

        command("status", "Show overall system status.", "status")

        logs_parser = command(
            "logs", "Tail the watcher's, the agent managers' or the service's log.", "logs agent -n 50",
            "The service's log is launchd's log file on macOS, or the unit's journal on Linux.")
        logs_parser.add_argument(
            "which", nargs="?", default="watcher",
            choices=("watcher", "agent", "service", "all"),
            help="Which log to tail (default: watcher)",
        )
        logs_parser.add_argument("-n", "--lines", type=int, default=20, help="Number of lines")
        logs_parser.add_argument("-f", "--follow", action="store_true",
                                 help="Keep printing the log as it grows, until Ctrl-C")

        command("runs", "Summarise today's agent runs: count, total time, longest.", "runs")

        start_parser = command(
            "start", "Start this instance's watcher as a service and wait for its hub.", "start",
            "Writes this instance's LaunchAgent (macOS) or systemd user unit (Linux), loads and "
            "starts it, and waits up to 30s for its hub to answer. Says so when the watcher is "
            "already running.")
        start_parser.add_argument(
            "--foreground", action="store_true",
            help="Run the watcher in this terminal instead, for a Linux without a user manager.")
        start_parser.add_argument("--from-installer", action="store_true", help=argparse.SUPPRESS)

        stop_parser = command(
            "stop", "Stop this instance's watcher and agent managers.", "stop --all",
            "For this instance (--all: every instance): stop the watcher's service, "
            "then stop the agent managers. start brings them back.")
        stop_parser.add_argument(
            "--all", action="store_true", help="Stop every instance, not only this one.")
        stop_parser.add_argument(
            "-f", "--force", action="store_true",
            help="Close the terminal sessions too, without asking.")

        command(
            "restart", "Restart this instance's watcher and agent managers.", "restart",
            "Holding the restart lock: for this instance, stop the agent managers, rewrite "
            "and reload the watcher's service and confirm the managers came back.")

        command(
            "restart-all", "Restart every instance's watcher and agent managers.", "restart-all",
            "Holding the restart lock, and first waiting for any other restart-all "
            "to finish: for this instance and every other one, stop the agent managers, "
            "rewrite and reload the watcher's service and confirm the managers came back.")

        update_parser = command(
            "update", "Install the newest release and restart every instance on it.", "update",
            "Says which version is installed and which is newest, installs the newest with "
            "uv tool install, then rewrites and restarts every instance's service.")
        update_parser.add_argument("--check", action="store_true",
                                   help="Only say whether a newer release exists.")
        update_parser.add_argument("--version", metavar="X",
                                   help="Install release X instead, even an older one.")

        command(
            "doctor", "Check the install, the service, GitHub and each repo, and say how to fix "
            "what fails.", "doctor",
            "Prints ok, warn or FAIL with a reason for each check, and the command that fixes "
            "anything not ok. Changes nothing, so it is safe to run anywhere and paste into an "
            "issue. Exits 1 when any check fails.")

        command("config", "Print every setting's effective value and where it came from.", "config")

        uninstall_parser = command(
            "uninstall", "Stop every instance, remove their services and the command.",
            "uninstall",
            "Asks before removing the config, the data and the notification apps too. Never "
            "touches your clones, and leaves uv, gh and the agent installed.")
        uninstall_parser.add_argument(
            "-y", "--yes", action="store_true",
            help="Remove the config, the data and the notification apps too, without asking.")

        skill_parser = command(
            "skill", "Install the rebase-on-main skill where this instance's agent reads its skills.",
            "skill",
            "The agents use it to rebase pull requests on their base branch.")
        skill_parser.add_argument(
            "--status", action="store_true",
            help="Only print missing, current or different: how the skill there compares "
                 "with this version's.")
        skill_parser.add_argument(
            "--replace", action="store_true",
            help="Put this version's skill in place of a different one already there.")

        command(
            "setup", "Open the board's setup page, where the account, the repos and the "
            "options are chosen.", "setup",
            "Prints the page's address and opens it in the browser. Repos are added and "
            "removed there too; a removed repo's state is archived and its worktrees are left "
            "where they are.")

        tutorial_parser = command(
            "tutorial", "Open the board's tour of the wall and a pull request's page.",
            "tutorial",
            "Starts the watcher first if it is not running. The board shows the tour by itself the first time the wall has pull requests; this shows it again.")
        tutorial_parser.add_argument(
            "--terminal", action="store_true",
            help="Print what the installer set up on this machine instead.")

        queue_parser = command("queue", "Show pending events for a PR.", "queue 88")
        queue_parser.add_argument("pr", type=int, help="PR number")

        undismiss_parser = command(
            "undismiss", "Clear a PR's dismissal so the watcher reopens its window.",
            "undismiss --repo acme/widgets 88")
        undismiss_parser.add_argument("--repo", type=parse_repo, required=True,
                                      help="The PR's repo, as owner/name")
        undismiss_parser.add_argument("pr", type=int, help="PR number")

        self.thread_parser = add_thread_parsers(sub)
        self.parser.description = self._listing(_GROUPS + _DEBUGGING)

    def help(self, topic: str | None) -> None:
        if topic is None:
            print(self._listing(_GROUPS))
        else:
            self.parser.parse_args([topic, "--help"])

    def _listing(self, groups: tuple[tuple[str, tuple[str, ...]], ...]) -> str:
        width = max(len(name) for _, names in groups for name in names)
        sections = [
            "\n".join([f"{title}:", *(f"  {name.ljust(width)}  {self._lines[name]}" for name in names)])
            for title, names in groups
        ]
        return "\n\n".join([_ABOUT, *sections])
