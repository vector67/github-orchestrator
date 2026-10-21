import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

DENYLIST = Path.home() / ".config" / "push-properly" / "denylist.txt"
SAFE_EMAIL_DOMAINS = ("users.noreply.github.com", "example.com", "example.org")
PATTERNS = {
    "home path": re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+"),
    "temp path": re.compile(r"/private/(?:var|tmp)/\S+"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})"),
    "token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_\w{40,}|sk-ant-[\w-]{20,}|xox[abpr]-[\w-]{10,}|AKIA[0-9A-Z]{16})"),
    "claude.ai link": re.compile(r"claude\.ai/(?:code/)?artifact/\S+|claude\.ai/chat/\S+"),
}


@dataclass(frozen=True)
class Finding:
    kind: str
    where: str
    text: str


def _kinds(text: str, denylist: list[str]) -> list[str]:
    kinds = []
    for kind, pattern in PATTERNS.items():
        matches = list(pattern.finditer(text))
        if kind == "email":
            matches = [match for match in matches if not match.group(1).lower().endswith(SAFE_EMAIL_DOMAINS)]
        if matches:
            kinds.append(kind)
    kinds += [f"denylisted: {term}" for term in denylist if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE)]
    return kinds


def _added_lines(diff: str) -> Iterable[tuple[str, str]]:
    path = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line.removeprefix("+++ ").removeprefix("b/")
        elif line.startswith("+"):
            yield path, line[1:]


def findings(messages: dict[str, str], diff: str, denylist: Iterable[str]) -> list[Finding]:
    terms = [term for term in denylist if term.strip()]
    lines = [(f"commit {sha}", line) for sha, body in messages.items() for line in body.splitlines()]
    lines += list(_added_lines(diff))
    return [Finding(kind, where, text) for where, text in lines for kind in _kinds(text, terms)]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main(revisions: str) -> int:
    terms = DENYLIST.read_text().splitlines() if DENYLIST.exists() else []
    log = _git("log", "--format=%h%x00%B%x1e", revisions)
    messages = dict(entry.strip("\n").split("\0", 1) for entry in log.split("\x1e") if "\0" in entry)
    found = findings(messages, _git("diff", revisions), terms)
    for finding in found:
        print(f"{finding.kind}\t{finding.where}\t{finding.text.strip()}")
    print(f"{len(found)} finding(s) in {len(messages)} commit(s); denylist: {DENYLIST if terms else 'none found at ' + str(DENYLIST)}", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "@{upstream}..HEAD"))
