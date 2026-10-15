import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pr_summary.settings import Settings

SUGGESTION = re.compile(r"```suggestion.*?```\n?", re.DOTALL)


@dataclass(frozen=True)
class Remark:
    author: str
    bot: bool
    body: str
    url: str


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str
    title: str
    body: str
    created_at: str
    branch: str
    base_sha: str
    head_sha: str
    author: str
    authors: frozenset[str]
    author_names: frozenset[str]
    commit_messages: tuple[str, ...]
    remarks: tuple[Remark, ...]
    changed_file_count: int


def _remark(node: dict[str, Any]) -> Remark:
    author = node.get("author") or {"login": "ghost", "__typename": "User"}
    return Remark(author=author["login"], bot=author["__typename"] == "Bot", body=node["body"], url=node["url"])


def remarks_from(pr: dict[str, Any]) -> tuple[Remark, ...]:
    nodes = [
        *pr["comments"]["nodes"],
        *pr["reviews"]["nodes"],
        *(comment for thread in pr["reviewThreads"]["nodes"] for comment in thread["comments"]["nodes"]),
    ]
    return tuple(_remark(node) for node in nodes if node["body"].strip())


def pull_request_from(graphql: dict[str, Any]) -> PullRequest:
    pr = graphql["data"]["repository"]["pullRequest"]
    commits = [node["commit"] for node in pr["commits"]["nodes"]]
    commit_authors = {author["user"]["login"] for commit in commits for author in commit["authors"]["nodes"] if author["user"]}
    commit_names = {author["name"] for commit in commits for author in commit["authors"]["nodes"] if author.get("name")}
    return PullRequest(
        number=pr["number"],
        url=pr["url"],
        title=pr["title"],
        body=pr["body"] or "",
        created_at=pr["createdAt"],
        branch=pr["headRefName"],
        base_sha=pr["baseRefOid"],
        head_sha=pr["headRefOid"],
        author=pr["author"]["login"],
        authors=frozenset({pr["author"]["login"], *commit_authors}),
        author_names=frozenset({*([pr["author"]["name"]] if pr["author"].get("name") else []), *commit_names}),
        commit_messages=tuple(commit["message"] for commit in commits),
        remarks=remarks_from(pr),
        changed_file_count=pr["changedFiles"],
    )


def is_bot(remark: Remark, settings: Settings) -> bool:
    return remark.bot or remark.author.endswith(("[bot]", "-bot")) or remark.author in settings.bots


def voices(remarks: Iterable[Remark], authors: frozenset[str], settings: Settings) -> tuple[list[Remark], list[Remark]]:
    humans = [remark for remark in remarks if not is_bot(remark, settings)]
    return [remark for remark in humans if remark.author in authors], [remark for remark in humans if remark.author not in authors]


def cleaned(body: str) -> str:
    without_suggestions = SUGGESTION.sub("", body)
    return "\n".join(line for line in without_suggestions.splitlines() if not line.lstrip().startswith(">"))
