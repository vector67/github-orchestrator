from github_orchestrator.domain import Pr, Repo
from github_orchestrator.github.interface import CommentKind

MAX_BODY_BYTES = 64 * 1024

_ANCHORS = {
    CommentKind.REVIEW: "discussion_r",
    CommentKind.ISSUE: "issuecomment-",
    CommentKind.REVIEW_SUMMARY: "pullrequestreview-",
}


def pr_url(pr: Pr) -> str:
    return f"https://github.com/{pr.repo}/pull/{pr.number}"


def commit_url(repo: Repo, sha: str) -> str:
    return f"https://github.com/{repo}/commit/{sha}"


def comment_url(pr: Pr, kind: CommentKind, comment_id: int) -> str:
    return f"{pr_url(pr)}#{_ANCHORS[kind]}{comment_id}"


def too_long(body: str) -> str | None:
    if len(body.encode()) <= MAX_BODY_BYTES:
        return None
    return f"GitHub takes at most {MAX_BODY_BYTES} bytes"
