import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COOL_C = 65.0
MAX_REST_SECONDS = 240
MIN_REST_SECONDS = 60


def cpu_temp() -> float | None:
    try:
        out = subprocess.run(["macmon", "pipe", "-s", "1"], capture_output=True, text=True, timeout=10).stdout
        return float(json.loads(out.strip().splitlines()[-1])["temp"]["cpu_temp_avg"])
    except (OSError, ValueError, KeyError, IndexError, subprocess.TimeoutExpired):
        return None


def load1() -> float:
    return float(subprocess.run(["sysctl", "-n", "vm.loadavg"], capture_output=True, text=True).stdout.split()[1])


def rest() -> None:
    started = time.time()
    while time.time() - started < MAX_REST_SECONDS:
        temp = cpu_temp()
        if time.time() - started >= MIN_REST_SECONDS and (temp is None or temp <= COOL_C):
            return
        time.sleep(10)


def run(kind: str) -> dict[str, object]:
    load, temp = load1(), cpu_temp()
    started = time.time()
    done = subprocess.run(["make", "test"], cwd=REPO, capture_output=True, text=True)
    wall = time.time() - started
    summary = next((line for line in reversed(done.stdout.splitlines()) if line.startswith("python:")), "")
    python = re.search(r"(\d+) passed", summary)
    ember = re.search(r"ember: (\d+) pass", summary)
    row: dict[str, object] = {
        "kind": kind, "wall_s": round(wall, 2), "passed": done.returncode == 0,
        "load1": round(load, 1), "cpu_c": None if temp is None else round(temp),
        "python_tests": int(python.group(1)) if python else None,
        "ember_tests": int(ember.group(1)) if ember else None, "summary": summary,
    }
    print(json.dumps(row), flush=True)
    return row


def main() -> None:
    cold_runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    warm_runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    run("prime")
    rows = []
    for _ in range(cold_runs):
        rest()
        rows.append(run("cold"))
    rest()
    rows.extend(run("warm") for _ in range(warm_runs))
    for kind in ("cold", "warm"):
        walls = [float(str(r["wall_s"])) for r in rows if r["kind"] == kind and r["passed"]]
        if walls:
            print(f"{kind}: median {statistics.median(walls):.1f} s, range {min(walls):.1f}-{max(walls):.1f} s, {len(walls)} passing runs")


if __name__ == "__main__":
    main()
