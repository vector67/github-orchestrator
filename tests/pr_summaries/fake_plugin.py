import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

WITNESSES = ("claimed", "implementation", "tests", "why")

parser = argparse.ArgumentParser()
parser.add_argument("--behaviour", required=True)
parser.add_argument("pr")
parser.add_argument("--config", type=Path, required=True)
parser.add_argument("--work-dir", type=Path, required=True)
parser.add_argument("--use-github-api", action="store_true")
parser.add_argument("--gh-account")
parser.add_argument("--mcp-config")
arguments = parser.parse_args()

out = arguments.work_dir
if out.exists() and any(out.iterdir()):
    sys.exit(f"WorkDirNotEmpty: {out}")
out.mkdir(parents=True, exist_ok=True)
(out / "call.json").write_text(json.dumps({
    "pr": arguments.pr,
    "config": str(arguments.config),
    "cwd": os.getcwd(),
    "use_github_api": arguments.use_github_api,
    "gh_account": arguments.gh_account,
    "mcp_config": arguments.mcp_config,
}))


def finish(witness: str, output: object) -> None:
    (out / witness).mkdir(exist_ok=True)
    (out / witness / "output.json").write_text(json.dumps(output))


behaviour = arguments.behaviour
if behaviour == "needs-api":
    sys.stderr.write("Cannot read acme/widgets locally: the working directory is not a clone of it.\n"
                     "Confirm reading its 3 changed files over the GitHub API (about 31 API calls) by adding --use-github-api.\n")
    sys.exit(3)
if behaviour == "crash":
    sys.stderr.write("GhFailed: gh pr view failed\n")
    sys.exit(1)
if behaviour == "hang":
    finish("claimed", {"claims": []})
    time.sleep(60)
if behaviour in ("partway", "partway-then-a-witness-fails"):
    finish("claimed", {"claims": []})
    (out / "implementation").mkdir()
    while not (out / "go-on").exists():
        if (out / "die").exists():
            os.killpg(os.getpgrp(), signal.SIGKILL)
        time.sleep(0.02)
for witness in WITNESSES:
    finish(witness, {})
if behaviour == "clean":
    finish("alignment", {"mismatches": [{"rung": "requested"}, {"rung": "claimed"}]})
elif behaviour == "malformed-alignment":
    (out / "alignment").mkdir()
    (out / "alignment" / "output.json").write_text("{not json")
print("# Summary\n\nIt does what it says.")
print(f"Working files: {out}")
if behaviour == "partway-then-a-witness-fails":
    sys.exit("Witnesses failed: why: timed out")
