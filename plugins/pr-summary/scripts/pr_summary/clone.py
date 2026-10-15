import re
import subprocess
from pathlib import Path

from pr_summary.inputs import ChangedFile, Unreadable

STATUSES = {"A": "added", "D": "removed", "M": "modified", "R": "renamed", "T": "modified", "C": "added"}


class CloneFailed(Exception):
    pass


def names_repo(url: str, owner: str, repo: str) -> bool:
    return re.search(rf"[:/]{re.escape(owner)}/{re.escape(repo)}(\.git)?/?$", url, re.IGNORECASE) is not None


def _git(root: Path, *args: str, stdin: bytes | None = None) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, input=stdin, capture_output=True)
    if result.returncode != 0:
        raise CloneFailed(result.stderr.decode(errors="replace").strip())
    return result.stdout


class Clone:
    def __init__(self, root: Path, remote: str) -> None:
        self.root = root
        self.remote = remote

    @staticmethod
    def find(root: Path, owner: str, repo: str) -> "Clone | None":
        try:
            remotes = _git(root, "remote", "-v").decode()
        except CloneFailed:
            return None
        for line in remotes.splitlines():
            name, url, *_ = line.split()
            if names_repo(url, owner, repo):
                return Clone(root, name)
        return None

    def fetch(self, number: int, base_sha: str) -> None:
        _git(self.root, "fetch", "--no-tags", "--quiet", self.remote, f"refs/pull/{number}/head")
        try:
            _git(self.root, "cat-file", "-e", f"{base_sha}^{{commit}}")
        except CloneFailed:
            _git(self.root, "fetch", "--no-tags", "--quiet", self.remote)

    def merge_base(self, base: str, head: str) -> str:
        return _git(self.root, "merge-base", base, head).decode().strip()

    def changed_files(self, base: str, head: str) -> list[ChangedFile]:
        statuses = _git(self.root, "diff", "-z", "-M", "--name-status", base, head).decode().split("\0")
        counts = self._counts(base, head)
        files = []
        index = 0
        while index < len(statuses) and statuses[index]:
            letter = statuses[index][0]
            if letter in "RC":
                previous, path = statuses[index + 1], statuses[index + 2]
                index += 3
            else:
                previous, path = None, statuses[index + 1]
                index += 2
            files.append(ChangedFile(path=path, previous=previous if letter == "R" else None, status=STATUSES.get(letter, "modified"), changes=counts.get(path, 0)))
        return files

    def _counts(self, base: str, head: str) -> dict[str, int]:
        fields = _git(self.root, "diff", "-z", "-M", "--numstat", base, head).decode().split("\0")
        counts = {}
        index = 0
        while index < len(fields) and fields[index]:
            added, removed, path = fields[index].split("\t")
            if path:
                index += 1
            else:
                path = fields[index + 2]
                index += 3
            counts[path] = (int(added) if added.isdigit() else 0) + (int(removed) if removed.isdigit() else 0)
        return counts

    def contents(self, sha: str, path: str) -> bytes | None:
        answer = _git(self.root, "cat-file", "--batch", stdin=f"{sha}:{path}\n".encode())
        header, _, body = answer.partition(b"\n")
        if header.endswith(b" missing"):
            return None
        _, kind, size = header.decode().split()
        if kind != "blob":
            raise Unreadable(path)
        return body[: int(size)]

    def history(self, sha: str, path: str, count: int) -> list[str]:
        return _git(self.root, "log", f"-n{count}", "--format=%H", sha, "--", path).decode().split()
