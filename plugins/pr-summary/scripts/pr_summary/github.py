import json
import re
import subprocess
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from pr_summary.earlier import chosen, earlier_from, most_changed
from pr_summary.inputs import ChangedFile, Contents, EarlierPr
from pr_summary.pull_request import PullRequest, pull_request_from
from pr_summary.settings import Settings

Gh = Callable[[list[str]], bytes]
PR_URL = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")

REMARKS = """
  comments(first: 100) { nodes { author { login __typename } body url } }
  reviews(first: 100) { nodes { author { login __typename } body url } }
  reviewThreads(first: 100) { nodes { comments(first: 100) { nodes { author { login __typename } body url } } } }
"""
PULL_REQUEST = (
    """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number url title body createdAt headRefName baseRefOid headRefOid
      author { login __typename ... on User { name } }
      commits(last: 100) { nodes { commit { message authors(first: 10) { nodes { name user { login } } } } } }
"""
    + REMARKS
    + "    }\n  }\n}\n"
)
EARLIER_PULL_REQUEST = (
    """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number url title body mergedAt
      author { login __typename }
"""
    + REMARKS
    + "    }\n  }\n}\n"
)


class GhFailed(Exception):
    pass


def gh_cli(args: list[str]) -> bytes:
    result = subprocess.run(["gh", *args], capture_output=True)
    if result.returncode != 0:
        raise GhFailed(result.stderr.decode(errors="replace").strip())
    return result.stdout


def target(gh: Gh, given: str) -> tuple[str, str, int]:
    found = PR_URL.search(given)
    if found:
        return found.group(1), found.group(2), int(found.group(3))
    owner, repo = json.loads(gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner | split(\"/\")"]))
    return owner, repo, int(given.lstrip("#"))


def _graphql(gh: Gh, query: str, owner: str, repo: str, number: int) -> dict[str, Any]:
    response: dict[str, Any] = json.loads(gh(["api", "graphql", "-f", f"query={query}", "-F", f"owner={owner}", "-F", f"repo={repo}", "-F", f"number={number}"]))
    return response


def pull_request(gh: Gh, owner: str, repo: str, number: int) -> PullRequest:
    return pull_request_from(_graphql(gh, PULL_REQUEST, owner, repo, number))


def changed_files(gh: Gh, owner: str, repo: str, number: int) -> list[ChangedFile]:
    lines = gh(["api", "--paginate", f"repos/{owner}/{repo}/pulls/{number}/files", "--jq", ".[] | {filename, previous_filename, status, changes}"])
    files = [json.loads(line) for line in lines.decode().splitlines() if line.strip()]
    return [ChangedFile(path=found["filename"], previous=found.get("previous_filename"), status=found["status"], changes=found["changes"]) for found in files]


def contents(gh: Gh, owner: str, repo: str) -> Contents:
    def at(sha: str, path: str) -> bytes | None:
        try:
            return gh(["api", "-H", "Accept: application/vnd.github.raw+json", f"repos/{owner}/{repo}/contents/{quote(path)}?ref={sha}"])
        except GhFailed:
            return None

    return at


def earlier_prs(gh: Gh, owner: str, repo: str, pr: PullRequest, ticket: str | None, files: list[ChangedFile], settings: Settings) -> list[EarlierPr]:
    numbers: list[int] = []
    if ticket:
        found = gh(["api", "-X", "GET", "search/issues", "-f", f"q=repo:{owner}/{repo} is:pr is:merged {ticket}", "--jq", ".items[].number"])
        numbers.extend(int(line) for line in found.decode().split())
    for path in most_changed(files, settings):
        shas = gh(["api", f"repos/{owner}/{repo}/commits?path={quote(path)}&sha={pr.base_sha}&per_page=5", "--jq", ".[].sha"]).decode().split()
        for sha in shas:
            merged = gh(["api", f"repos/{owner}/{repo}/commits/{sha}/pulls", "--jq", ".[] | select(.merged_at != null) | .number"])
            numbers.extend(int(line) for line in merged.decode().split())
    earlier = []
    for number in chosen(numbers, this=pr.number):
        node = _graphql(gh, EARLIER_PULL_REQUEST, owner, repo, number)["data"]["repository"]["pullRequest"]
        found_pr = earlier_from(node, opened=pr.created_at)
        if found_pr is not None:
            earlier.append(found_pr)
    return earlier
