import base64
import json
import os
import re
import subprocess
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from pr_summary.earlier import chosen, earlier_from, most_changed
from pr_summary.inputs import ChangedFile, Contents, EarlierPr, Unreadable
from pr_summary.pull_request import PullRequest, pull_request_from
from pr_summary.settings import Settings

Gh = Callable[[list[str]], bytes]
History = Callable[[str], list[str]]
HISTORY_DEPTH = 5
PR_URL = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")
CUT_OFF = b"unexpected end of JSON input"

AUTHOR = "author { login __typename }"
REMARK_NODES = f"nodes {{ {AUTHOR} body url }}"
REMARKS = f"""
  comments(first: 100) {{ {REMARK_NODES} }}
  reviews(first: 100) {{ {REMARK_NODES} }}
  reviewThreads(first: 100) {{ nodes {{ comments(first: 100) {{ {REMARK_NODES} }} }} }}
"""
PULL_REQUEST = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number url title body createdAt headRefName baseRefOid headRefOid changedFiles
      author { login __typename ... on User { name } }
    }
  }
}
"""
PAGED = {
    "commits": "nodes { commit { message authors(first: 10) { nodes { name user { login } } } } }",
    "comments": REMARK_NODES,
    "reviews": REMARK_NODES,
    "reviewThreads": f"nodes {{ comments(first: 100) {{ {REMARK_NODES} }} }}",
}
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


def _paged_query(connection: str) -> str:
    return f"""
query($owner: String!, $repo: String!, $number: Int!, $endCursor: String) {{
  repository(owner: $owner, name: $repo) {{
    pullRequest(number: $number) {{
      {connection}(first: 100, after: $endCursor) {{ pageInfo {{ hasNextPage endCursor }} {PAGED[connection]} }}
    }}
  }}
}}
"""


class GhFailed(Exception):
    pass


def gh_cli(args: list[str], env: dict[str, str] | None = None) -> bytes:
    result = subprocess.run(["gh", *args], capture_output=True, env=env)
    if result.returncode != 0 and CUT_OFF in result.stderr:
        result = subprocess.run(["gh", *args], capture_output=True, env=env)
    if result.returncode != 0:
        raise GhFailed(result.stderr.decode(errors="replace").strip())
    return result.stdout


def gh_as(account: str) -> Gh:
    try:
        token = gh_cli(["auth", "token", "--user", account]).decode().strip()
    except GhFailed as failure:
        raise GhFailed(f"gh auth token --user {account} failed: {failure}") from None
    env = {**os.environ, "GH_TOKEN": token}
    return lambda args: gh_cli(args, env)


def target(gh: Gh, given: str) -> tuple[str, str, int]:
    found = PR_URL.search(given)
    if found:
        return found.group(1), found.group(2), int(found.group(3))
    owner, repo = json.loads(gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner | split(\"/\")"]))
    return owner, repo, int(given.lstrip("#"))


def _variables(query: str, owner: str, repo: str, number: int) -> list[str]:
    return ["-f", f"query={query}", "-F", f"owner={owner}", "-F", f"repo={repo}", "-F", f"number={number}"]


def _graphql(gh: Gh, query: str, owner: str, repo: str, number: int) -> dict[str, Any]:
    response: dict[str, Any] = json.loads(gh(["api", "graphql", *_variables(query, owner, repo, number)]))
    return response


def pull_request(gh: Gh, owner: str, repo: str, number: int) -> PullRequest:
    response = _graphql(gh, PULL_REQUEST, owner, repo, number)
    pr = response["data"]["repository"]["pullRequest"]
    for connection in PAGED:
        pages = json.loads(gh(["api", "graphql", "--paginate", "--slurp", *_variables(_paged_query(connection), owner, repo, number)]))
        pr[connection] = {"nodes": [node for page in pages for node in page["data"]["repository"]["pullRequest"][connection]["nodes"]]}
    return pull_request_from(response)


def changed_files(gh: Gh, owner: str, repo: str, number: int) -> list[ChangedFile]:
    lines = gh(["api", "--paginate", f"repos/{owner}/{repo}/pulls/{number}/files", "--jq", ".[] | {filename, previous_filename, status, changes}"])
    files = [json.loads(line) for line in lines.decode().splitlines() if line.strip()]
    return [ChangedFile(path=found["filename"], previous=found.get("previous_filename"), status=found["status"], changes=found["changes"]) for found in files]


def contents(gh: Gh, owner: str, repo: str) -> Contents:
    def at(sha: str, path: str) -> bytes | None:
        try:
            found = json.loads(gh(["api", f"repos/{owner}/{repo}/contents/{quote(path)}?ref={sha}"]))
        except GhFailed as failure:
            if "HTTP 404" in str(failure):
                return None
            raise
        if not isinstance(found, dict) or found.get("type") != "file":
            raise Unreadable(path)
        if found.get("encoding") != "base64":
            found = json.loads(gh(["api", f"repos/{owner}/{repo}/git/blobs/{found['sha']}"]))
        return base64.b64decode(found["content"])

    return at


def merge_base(gh: Gh, owner: str, repo: str, base: str, head: str) -> str:
    return gh(["api", f"repos/{owner}/{repo}/compare/{base}...{head}", "--jq", ".merge_base_commit.sha"]).decode().strip()


def history(gh: Gh, owner: str, repo: str, sha: str) -> History:
    def of(path: str) -> list[str]:
        return gh(["api", f"repos/{owner}/{repo}/commits?path={quote(path)}&sha={sha}&per_page={HISTORY_DEPTH}", "--jq", ".[].sha"]).decode().split()

    return of


def earlier_prs(gh: Gh, owner: str, repo: str, pr: PullRequest, ticket: str | None, files: list[ChangedFile], settings: Settings, history_of: History) -> list[EarlierPr]:
    numbers: list[int] = []
    if ticket:
        found = gh(["api", "-X", "GET", "search/issues", "-f", f"q=repo:{owner}/{repo} is:pr is:merged {ticket}", "--jq", ".items[].number"])
        numbers.extend(int(line) for line in found.decode().split())
    for path in most_changed(files, settings):
        for sha in history_of(path):
            merged = gh(["api", f"repos/{owner}/{repo}/commits/{sha}/pulls", "--jq", f'.[] | select(.merged_at != null and .base.repo.full_name == "{owner}/{repo}") | .number'])
            numbers.extend(int(line) for line in merged.decode().split())
    earlier = []
    for number in chosen(numbers, this=pr.number):
        node = _graphql(gh, EARLIER_PULL_REQUEST, owner, repo, number)["data"]["repository"]["pullRequest"]
        found_pr = earlier_from(node, opened=pr.created_at)
        if found_pr is not None:
            earlier.append(found_pr)
    return earlier
