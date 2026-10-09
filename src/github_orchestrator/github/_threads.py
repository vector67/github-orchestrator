import logging
import subprocess
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from github_orchestrator.domain import Location, Pr, Repo, Side
from github_orchestrator.github._gh_cli import Gh
from github_orchestrator.github.interface import (
    CommentKind,
    GhError,
    PostedComment,
    ReviewComment,
    SentReview,
    Thread,
    ThreadAnchor,
    ThreadComment,
    Verdict,
    review_state_of,
)

log = logging.getLogger(__name__)

PAGE_SIZE = 100

_WORDS = {Side.BEFORE: "LEFT", Side.AFTER: "RIGHT"}

_SIDES = {word: side for side, word in _WORDS.items()}

MAX_PAGES = 500

AUTHOR_FIELDS = "author { login ... on User { name } }"

COMMENT_FIELDS = """
  databaseId
  %(author)s
  body
  createdAt
  updatedAt
  startLine
  originalStartLine
  commit { oid }
  originalCommit { oid }
  pullRequestReview { state }
""" % {"author": AUTHOR_FIELDS}

CURSORS = "$threadCursor: String, $issueCursor: String, $reviewCursor: String"

CONNECTIONS = """
      reviewThreads(first: %(page)d, after: $threadCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          resolvedBy { login }
          isOutdated
          path
          line
          startDiffSide
          originalLine
          diffSide
          subjectType
          comments(first: %(page)d) {
            pageInfo { hasNextPage endCursor }
            nodes { %(comment)s }
          }
        }
      }
      comments(first: %(page)d, after: $issueCursor) {
        pageInfo { hasNextPage endCursor }
        nodes { id databaseId %(author)s body createdAt updatedAt }
      }
      reviews(first: %(page)d, after: $reviewCursor) {
        pageInfo { hasNextPage endCursor }
        nodes { id databaseId %(author)s body state createdAt }
      }
""" % {"page": PAGE_SIZE, "comment": COMMENT_FIELDS, "author": AUTHOR_FIELDS}

_QUERY = """
query($owner: String!, $name: String!, $number: Int!, %(cursors)s) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {%(connections)s    }
  }
}
""" % {"cursors": CURSORS, "connections": CONNECTIONS}

_KINDS = (("reviewThreads", "threadCursor"), ("comments", "issueCursor"),
          ("reviews", "reviewCursor"))

_THREAD_COMMENTS_QUERY = """
query($threadId: ID!, $cursor: String) {
  node(id: $threadId) {
    ... on PullRequestReviewThread {
      comments(first: %(page)d, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { %(comment)s }
      }
    }
  }
}
""" % {"page": PAGE_SIZE, "comment": COMMENT_FIELDS}

def _login(node: dict[str, Any] | None) -> str:
    author = (node or {}).get("author") or {}
    return author.get("login") or "ghost"


def _display_name(node: dict[str, Any] | None) -> str:
    author = (node or {}).get("author") or {}
    return author.get("name") or ""


def _comment(node: dict[str, Any]) -> ThreadComment:
    return ThreadComment(
        id=node.get("databaseId"),
        author=_login(node),
        author_name=_display_name(node),
        review_state=review_state_of((node.get("pullRequestReview") or {}).get("state")),
        body=node.get("body") or "",
        created_at=node.get("createdAt"),
        updated_at=node.get("updatedAt") or node.get("createdAt"),
    )


def _connection(pull: dict[str, Any], name: str,
                what: str) -> tuple[list[dict[str, Any]], bool, str | None]:
    conn = pull.get(name)
    if not isinstance(conn, dict):
        raise GhError(f"{what} answered no connection at all")
    nodes = conn.get("nodes")
    if nodes is None:
        raise GhError(f"{what} answered a page with no nodes")
    info = conn.get("pageInfo") or {}
    return nodes, bool(info.get("hasNextPage")), info.get("endCursor")


def _error_text(errors: object) -> str:
    entries = errors if isinstance(errors, list) else [errors]
    return "; ".join(
        str(error.get("message") or error) if isinstance(error, dict)
        else str(error)
        for error in entries
    )


def _at(result: dict[str, Any], *path: str) -> Any:
    found: Any = result
    for step in path:
        if not isinstance(found, dict):
            return None
        found = found.get(step)
    return found


def _answered(result: Any, what: str, wanted: str, *path: str) -> Any:
    if not isinstance(result, dict):
        raise GhError(f"{what} answered {type(result).__name__}, not an object")
    errors = result.get("errors")
    found = _at(result, *path)
    if found is None:
        reason = f": {_error_text(errors)}" if errors else ""
        raise GhError(f"{what} answered with no {wanted}{reason}")
    if errors:
        log.warning("%s carried errors beside the page it answered: %s",
                    what, _error_text(errors))
    return found


def _pull_request(result: Any, pr: Pr) -> dict[str, Any]:
    what = f"the threads query for {pr}"
    found = _answered(result, what, "pull request",
                      "data", "repository", "pullRequest")
    if not isinstance(found, dict):
        raise GhError(f"{what} answered a "
                      f"{type(found).__name__}, not a pull request")
    return found


def _next_cursor(what: str, nodes: list[Any], end: str | None,
                 seen: set[str]) -> str:
    if not end:
        raise GhError(f"{what} says it has more pages but named no cursor")
    if end in seen:
        raise GhError(f"{what} keeps answering with the cursor it was given")
    if not nodes:
        raise GhError(f"{what} answered an empty page that claims more")
    if len(seen) + 1 >= MAX_PAGES:
        raise GhError(f"{what} is still paging after {MAX_PAGES} pages")
    seen.add(end)
    return end


def _rest_of_thread_comments(gh: Gh, thread_id: str,
                             cursor: str | None) -> list[dict[str, Any]]:
    what = f"the comments of thread {thread_id}"
    if not cursor:
        raise GhError(f"{what} says it has more pages but named no cursor")
    nodes: list[dict[str, Any]] = []
    seen = {cursor}
    while True:
        result = gh.graphql(_THREAD_COMMENTS_QUERY,
                            {"threadId": thread_id, "cursor": cursor})
        node = _answered(result, what, "thread", "data", "node")
        page, has_next, end = _connection(node, "comments", what)
        nodes.extend(page)
        if not has_next:
            return nodes
        cursor = _next_cursor(what, page, end, seen)


def _review_thread(gh: Gh, node: dict[str, Any]) -> Thread:
    raw = list((node.get("comments") or {}).get("nodes") or [])
    info = (node.get("comments") or {}).get("pageInfo") or {}
    if info.get("hasNextPage"):
        raw.extend(_rest_of_thread_comments(gh, node["id"], info.get("endCursor")))

    root = raw[0] if raw else {}
    return Thread(
        key=node["id"],
        kind=CommentKind.REVIEW,
        comments=tuple(_comment(c) for c in raw),
        anchor=ThreadAnchor(
            is_outdated=bool(node.get("isOutdated")),
            side=_SIDES.get(node.get("diffSide") or ""),
            start_line=root.get("startLine"),
            start_side=_SIDES.get(node.get("startDiffSide") or ""),
            original_line=node.get("originalLine"),
            original_start_line=root.get("originalStartLine"),
            original_commit=(root.get("originalCommit") or {}).get("oid"),
        ),
        path=node.get("path"),
        line=node.get("line"),
        is_resolved=bool(node.get("isResolved")),
        resolved_by=(node.get("resolvedBy") or {}).get("login"),
    )


def _issue_thread(node: dict[str, Any]) -> Thread:
    return Thread(key=node["id"], kind=CommentKind.ISSUE,
                  comments=(_comment(node),), anchor=ThreadAnchor())


def _review_summary_thread(node: dict[str, Any]) -> Thread:
    state = review_state_of(node.get("state"))
    return Thread(
        key=node["id"], kind=CommentKind.REVIEW_SUMMARY,
        comments=(replace(_comment(node), review_state=state),),
        anchor=ThreadAnchor(), state=state,
    )


def threads(gh: Gh, pr: Pr) -> list[Thread]:
    owner, name = pr.repo.owner, pr.repo.name
    variables = {"owner": owner, "name": name, "number": pr.number}

    live = {"reviewThreads": True, "comments": True, "reviews": True}
    cursors: dict[str, str] = {}
    seen: dict[str, set[str]] = {name_: set() for name_ in live}
    raw: dict[str, list[dict[str, Any]]] = {"reviewThreads": [], "comments": [], "reviews": []}

    while any(live.values()):
        result = gh.graphql(_QUERY, {**variables, **cursors})
        pull = _pull_request(result, pr)

        for name_, cursor_var in _KINDS:
            if not live[name_]:
                continue
            what = f"the {name_} of {pr}"
            nodes, has_next, end = _connection(pull, name_, what)
            raw[name_].extend(nodes)
            live[name_] = has_next
            if has_next:
                cursors[cursor_var] = _next_cursor(what, nodes, end,
                                                   seen[name_])

    return _threads_of(gh, raw)


def first_page_threads(gh: Gh, pr: Pr, pull: dict[str, Any]) -> list[Thread] | None:
    raw: dict[str, list[dict[str, Any]]] = {}
    for name_, _ in _KINDS:
        nodes, has_next, _end = _connection(pull, name_, f"the {name_} of {pr}")
        if has_next:
            return None
        raw[name_] = nodes
    return _threads_of(gh, raw)


def _threads_of(gh: Gh, raw: dict[str, list[dict[str, Any]]]) -> list[Thread]:
    found = [_review_thread(gh, n) for n in raw["reviewThreads"]]
    found += [_issue_thread(n) for n in raw["comments"]]
    found += [
        _review_summary_thread(n) for n in raw["reviews"]
        if (n.get("body") or "").strip()
    ]
    return found


_ADD_THREAD_REPLY = """
mutation($threadId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(
    input: {pullRequestReviewThreadId: $threadId, body: $body}
  ) {
    comment { %(comment)s }
  }
}
""" % {"comment": COMMENT_FIELDS}

_RESOLVE_THREAD = """
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread { id isResolved }
  }
}
"""

_UNRESOLVE_THREAD = """
mutation($threadId: ID!) {
  unresolveReviewThread(input: {threadId: $threadId}) {
    thread { id isResolved }
  }
}
"""

_PATHS = {
    CommentKind.REVIEW: "/repos/{repo}/pulls/comments/{id}",
    CommentKind.ISSUE: "/repos/{repo}/issues/comments/{id}",
    CommentKind.REVIEW_SUMMARY: "/repos/{repo}/pulls/{pr}/reviews/{id}",
}


def reply_to_thread(gh: Gh, key: str, body: str) -> ThreadComment | None:
    payload = gh.graphql_mutate(_ADD_THREAD_REPLY, {"threadId": key, "body": body})
    data = (payload or {}).get("data") or {}
    reply = (data.get("addPullRequestReviewThreadReply") or {}).get("comment")
    return _comment(reply) if reply else None


def resolve_thread(gh: Gh, key: str) -> None:
    gh.graphql_mutate(_RESOLVE_THREAD, {"threadId": key})


def unresolve_thread(gh: Gh, key: str) -> None:
    gh.graphql_mutate(_UNRESOLVE_THREAD, {"threadId": key})


def react(gh: Gh, repo: Repo, comment_id: int) -> None:
    gh.api_json(f"repos/{repo}/pulls/comments/{comment_id}/reactions",
                {"content": "+1"})


def _placed(where: Location) -> dict[str, Any]:
    placed: dict[str, Any] = {"path": where.path, "line": where.line,
                              "side": _WORDS[where.side]}
    if where.start_side is not None:
        placed |= {"start_line": where.start_line, "start_side": _WORDS[where.start_side]}
    return placed


def _rest_comment(created: dict[str, Any]) -> ThreadComment:
    return ThreadComment(
        id=created.get("id"),
        author=(created.get("user") or {}).get("login") or "ghost",
        body=created.get("body") or "",
        created_at=created.get("created_at"),
        updated_at=created.get("updated_at") or created.get("created_at"),
    )


def post_review_comment(gh: Gh, pr: Pr, head: str,
                        location: Location, body: str) -> ThreadComment:
    """A review comment of your own, opening a thread on the head's diff."""
    posted = gh.api_json(f"repos/{pr.repo}/pulls/{pr.number}/comments",
                         {"commit_id": head, **_placed(location), "body": body})
    if not isinstance(posted, dict):
        raise GhError(f"posting a review comment on {pr} answered "
                      f"{type(posted).__name__}, not the comment")
    return _rest_comment(posted)


_PENDING_REVIEW = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviews(states: PENDING, first: 1) { nodes { id databaseId } }
    }
  }
}
"""

_ADD_REVIEW_THREAD = """
mutation($reviewId: ID!, $path: String!, $body: String!, $line: Int!,
         $side: DiffSide!, $startLine: Int, $startSide: DiffSide) {
  addPullRequestReviewThread(input: {
    pullRequestReviewId: $reviewId, path: $path, body: $body, line: $line,
    side: $side, startLine: $startLine, startSide: $startSide
  }) {
    thread { id }
  }
}
"""


def _pending_review(gh: Gh, pr: Pr) -> tuple[str, int] | None:
    """The viewer's own pending review, the only one GitHub shows them."""
    result = gh.graphql(_PENDING_REVIEW, {"owner": pr.repo.owner, "name": pr.repo.name,
                                          "number": pr.number})
    nodes = _answered(result, f"the pending review of {pr}", "pull request",
                      "data", "repository", "pullRequest", "reviews", "nodes")
    if not nodes:
        return None
    return nodes[0]["id"], nodes[0]["databaseId"]


def _submitted_pending_review(gh: Gh, pr: Pr, pending: tuple[str, int], verdict: Verdict,
                              body: str | None,
                              comments: Sequence[tuple[Location, str]]) -> object:
    node_id, review_id = pending
    for where, text in comments:
        placed = {"reviewId": node_id, "path": where.path, "body": text,
                  "line": where.line, "side": _WORDS[where.side]}
        if where.start_side is not None:
            placed |= {"startLine": where.start_line, "startSide": _WORDS[where.start_side]}
        gh.graphql_mutate(_ADD_REVIEW_THREAD, placed)
    submitted: dict[str, Any] = {"event": verdict.value}
    if body is not None:
        submitted["body"] = body
    return gh.api_json(f"repos/{pr.repo}/pulls/{pr.number}/reviews/{review_id}/events",
                       submitted)


def post_review(gh: Gh, pr: Pr, head: str, verdict: Verdict,
                body: str | None, comments: Sequence[tuple[Location, str]]) -> SentReview:
    """One review with a verdict, which notifies the author once however
    many comments it carries. A review the viewer left pending on GitHub
    takes the comments and goes out with them, since GitHub holds one
    pending review per viewer and refuses a second."""
    pending = _pending_review(gh, pr)
    if pending is not None:
        posted = _submitted_pending_review(gh, pr, pending, verdict, body, comments)
    else:
        payload: dict[str, Any] = {
            "commit_id": head, "event": verdict.value,
            "comments": [{**_placed(where), "body": text} for where, text in comments],
        }
        if body is not None:
            payload["body"] = body
        posted = gh.api_json(f"repos/{pr.repo}/pulls/{pr.number}/reviews", payload)
    if not isinstance(posted, dict):
        raise GhError(f"sending a review on {pr} answered "
                      f"{type(posted).__name__}, not the review")
    review_id = posted.get("id")
    if not isinstance(review_id, int):
        return SentReview(None, ())
    if not comments:
        return SentReview(review_id, ())
    return SentReview(review_id, _review_comments(gh, pr, review_id))


def _review_comments(gh: Gh, pr: Pr, review_id: int) -> tuple[ReviewComment, ...]:
    listed = gh.api(f"repos/{pr.repo}/pulls/{pr.number}/reviews/{review_id}/comments",
                    paginate=True)
    if not isinstance(listed, list):
        return ()
    return tuple(ReviewComment(path=comment.get("path"), comment=_rest_comment(comment))
                 for comment in listed if isinstance(comment, dict))


def comment_on_pr(gh: Gh, pr: Pr, body: str) -> PostedComment:
    """The comment posted on the PR itself, and the key of the thread it becomes."""
    created = gh.api_post(f"repos/{pr.repo}/issues/{pr.number}/comments", {"body": body})
    return PostedComment(_rest_comment(created), created.get("node_id"))


def _comment_endpoint(pr: Pr, kind: CommentKind, comment_id: int) -> str:
    return _PATHS[kind].format(repo=pr.repo, pr=pr.number, id=comment_id)


def delete_comment(gh: Gh, pr: Pr, kind: CommentKind,
                   comment_id: int) -> None:
    """Take the comment off GitHub. Already gone is done, not a failure."""
    path = _comment_endpoint(pr, kind, comment_id)
    try:
        gh.api_delete(path)
    except GhError as e:
        if "HTTP 404" not in str(e):
            raise
        log.info("%s comment %s was already gone from GitHub",
                 pr, comment_id)


def comment_exists(gh: Gh, pr: Pr, kind: CommentKind,
                   comment_id: int) -> bool | None:
    path = _comment_endpoint(pr, kind, comment_id)
    try:
        gh.api(path)
    except (GhError, subprocess.TimeoutExpired, ValueError) as exc:
        if "HTTP 404" not in str(exc):
            log.warning("could not check %s comment %d on GitHub: %s",
                        pr, comment_id, exc)
            return None
        return False
    return True
