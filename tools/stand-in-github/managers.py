import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

MANAGER = "-m github_orchestrator.pr_manager --repo acme/widgets --pr 1"
WAIT = 180


def managers() -> dict[int, float]:
    listed = subprocess.run(["ps", "-A", "-o", "pid=,lstart=,command="], capture_output=True,
                            text=True, check=True, env={**os.environ, "LC_ALL": "C"}).stdout
    running = {}
    for line in listed.splitlines():
        fields = line.split(None, 6)
        if len(fields) == 7 and MANAGER in fields[6]:
            started = time.mktime(time.strptime(" ".join(fields[1:6]), "%a %b %d %H:%M:%S %Y"))
            running[int(fields[0])] = started
    return running


def installed_at(version: str) -> float:
    tools = Path(subprocess.run(["uv", "tool", "dir"], capture_output=True, text=True,
                                check=True).stdout.strip())
    found = list(tools.glob(f"github-orchestrator/lib/*/site-packages/github_orchestrator-{version}.dist-info"))
    if not found:
        sys.exit(f"github-orchestrator {version} is not what uv installed under {tools}")
    return found[0].stat().st_mtime


def before(record: Path) -> None:
    deadline = time.monotonic() + WAIT
    while not (running := managers()):
        if time.monotonic() > deadline:
            sys.exit(f"no agent manager ran for acme/widgets#1 within {WAIT}s")
        time.sleep(2)
    record.write_text(" ".join(str(pid) for pid in running))
    print(f"the old release runs the manager as {sorted(running)}")


def after(record: Path, version: str) -> None:
    old = {int(pid) for pid in record.read_text().split()}
    since = int(installed_at(version))
    deadline = time.monotonic() + WAIT
    while True:
        running = managers()
        survivors = old & running.keys()
        new = {pid for pid, started in running.items() if pid not in old and started >= since}
        if not survivors and new and new == running.keys():
            print(f"the manager runs {version} as {sorted(new)}")
            return
        if time.monotonic() > deadline:
            sys.exit(f"after {WAIT}s the old managers {sorted(survivors)} still run, and of "
                     f"{sorted(running)} only {sorted(new)} started after {version} was installed")
        time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("moment", choices=["before", "after"])
    parser.add_argument("record", type=Path)
    parser.add_argument("version", nargs="?")
    args = parser.parse_args()
    if args.moment == "before":
        before(args.record)
    else:
        after(args.record, args.version)


main()
