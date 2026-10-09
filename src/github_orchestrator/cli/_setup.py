import sys
from collections.abc import Callable

from github_orchestrator.cli._command_lines import setup_line
from github_orchestrator.settings import ConfigFile

ReadLine = Callable[[str], str]


def show_config(config_file: ConfigFile) -> None:
    described = config_file.describe()
    if described.problem is not None:
        print(described.problem, file=sys.stderr)
        sys.exit(2)
    rows = described.rows
    if described.exists:
        print(f"{config_file.location()}\n")
    else:
        print(f"{config_file.location()} (no file there yet)\n")
    width = max(len(row.key) for row in rows)
    for row in rows:
        print(f"{row.key:<{width}}  {row.value}  {row.source}")

    unset = [row.key for row in rows if row.unset]
    if unset:
        sys.stdout.flush()
        print(
            f"\n{', '.join(unset)} still show the placeholder they ship with, "
            f"which is why every other command exits 2 — run `{setup_line()}` to set "
            f"them on the board's setup page.",
            file=sys.stderr,
        )
        sys.exit(2)


def setup(hub_url: str, opened: Callable[[str], None]) -> None:
    print(f"Setup is on the board now: {hub_url}/setup", flush=True)
    opened("/setup")
