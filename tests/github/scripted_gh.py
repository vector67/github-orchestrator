import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from github_orchestrator.domain import Location, Repo, Side
from github_orchestrator.github import CommentKind, Thread, ThreadComment, Verdict
from github_orchestrator.github.fake import SEARCH_REFUSED, FakeGitHub, GhError, Whose
from tests.builders import a_pr

NOT_FOUND = "gh: Not Found (HTTP 404)"
UNPROCESSABLE = "gh: Unprocessable Entity (HTTP 422)"

_WORDS = {Side.BEFORE: "LEFT", Side.AFTER: "RIGHT"}


@dataclass
class Failure:
    stderr: str
    returncode: int = 1


@dataclass
class Timeout:
    seconds: int = 120


@dataclass
class Raw:
    stdout: str


@dataclass
class GhRequest:
    argv: list[str]
    token: str | None
    route: str = ""
    method: str = "GET"
    path: str = ""
    fields: dict[str, Any] = field(default_factory=dict)
    jq: str | None = None
    paginate: bool = False
    include: bool = False
    payload: Any = None

    @property
    def query(self) -> str:
        return str(self.fields.get("query", ""))

    @property
    def variables(self) -> dict[str, Any]:
        return {k: v for k, v in self.fields.items() if k != "query"}


def _typed(value: str) -> Any:
    if value in ("true", "false"):
        return value == "true"
    if value == "null":
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


class _FieldFileMissing(Exception):
    pass


def _api_request(argv: list[str], token: str | None, stdin: str | None) -> GhRequest:
    request = GhRequest(argv=argv, token=token)
    method = None
    rest = argv[2:]
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg in ("-X", "--method"):
            method = rest[i + 1]
            i += 2
        elif arg == "--jq":
            request.jq = rest[i + 1]
            i += 2
        elif arg == "--paginate":
            request.paginate = True
            i += 1
        elif arg in ("-i", "--include"):
            request.include = True
            i += 1
        elif arg == "--input":
            request.payload = json.loads(stdin or "null")
            i += 2
        elif arg in ("-f", "--raw-field"):
            key, _, value = rest[i + 1].partition("=")
            request.fields[key] = value
            i += 2
        elif arg in ("-F", "--field"):
            key, _, value = rest[i + 1].partition("=")
            if value.startswith("@"):
                if not Path(value[1:]).exists():
                    raise _FieldFileMissing(value[1:])
                value = Path(value[1:]).read_text()
            request.fields[key] = _typed(value)
            i += 2
        else:
            request.path = arg.lstrip("/")
            i += 1
    if method is None:
        method = "POST" if request.fields or request.path == "graphql" else "GET"
    request.method = method
    request.route = "graphql" if request.path == "graphql" else f"{method} {request.path}"
    return request


class ScriptedGh:
    def __init__(self, world: FakeGitHub | None = None,
                 tokens: dict[str, str] | None = None) -> None:
        self.world = world
        self.tokens = (world.tokens if world is not None
                       else tokens if tokens is not None
                       else {"octocat": "gho_octocat"})
        self.scripted: dict[str, list[Any]] = {}
        self.standing: dict[str, Any] = {}
        self.calls: list[GhRequest] = []
        self.unscripted: list[GhRequest] = []
        self.token_requests: list[str] = []
        self.installed = True

    def answer(self, route: str, *answers: Any) -> "ScriptedGh":
        self.scripted.setdefault(route, []).extend(answers)
        return self

    def always(self, route: str, answer: Any) -> "ScriptedGh":
        self.standing[route] = answer
        return self

    def _routes(self, request: GhRequest) -> list[str]:
        if request.route != "graphql":
            return [request.route]
        refined = [key for key in (*self.scripted, *self.standing)
                   if key.startswith("graphql ") and key[8:] in request.query]
        return [*refined, "graphql"]

    def __call__(self, cmd: list[str], *, env: dict[str, str] | None = None,
                 input: str | None = None, check: bool = False,
                 timeout: float | None = None, **_: Any
                 ) -> subprocess.CompletedProcess[str]:
        assert cmd[0] == "gh", f"not a gh command: {cmd!r}"
        if not self.installed:
            raise FileNotFoundError(2, "No such file or directory", "gh")
        token = (env or {}).get("GH_TOKEN")
        outcome = self._outcome(list(cmd), token, input)
        if isinstance(outcome, Timeout):
            raise subprocess.TimeoutExpired(cmd, outcome.seconds)
        if isinstance(outcome, Failure):
            if check:
                raise subprocess.CalledProcessError(outcome.returncode, cmd,
                                                    output="", stderr=outcome.stderr)
            return subprocess.CompletedProcess(cmd, outcome.returncode, "",
                                               outcome.stderr)
        stdout = outcome.stdout if isinstance(outcome, Raw) else json.dumps(outcome)
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    def _outcome(self, argv: list[str], token: str | None, stdin: str | None) -> Any:
        if argv[1:3] == ["auth", "token"]:
            account = argv[argv.index("--user") + 1]
            self.token_requests.append(account)
            known = self.tokens.get(account)
            if known is None:
                return Failure(f"no oauth token found for github.com account {account}")
            return Raw(f"{known}\n")
        if argv[1:3] == ["api", "user"] and token is None:
            active = self.world.account if self.world is not None else "octocat"
            return Raw(f"{active}\n")
        if argv[1:3] == ["repo", "clone"]:
            request = GhRequest(argv=argv, token=token, route="repo clone", path=argv[3])
        elif token not in self.tokens.values():
            return Failure("gh: Bad credentials (HTTP 401)")
        elif argv[1:3] == ["repo", "view"]:
            request = GhRequest(argv=argv, token=token, route="repo view", path=argv[3])
        elif argv[1:3] == ["search", "prs"]:
            request = GhRequest(argv=argv, token=token, route="search prs")
        elif argv[1] == "api":
            try:
                request = _api_request(argv, token, stdin)
            except _FieldFileMissing as missing:
                return Failure(f"open {missing}: no such file or directory")
        else:
            raise AssertionError(f"gh has no {argv[1]!r} command here: {argv!r}")
        self.calls.append(request)
        for route in self._routes(request):
            queue = self.scripted.get(route)
            if queue:
                answer = queue.pop(0)
                return answer(request) if callable(answer) else answer
            if route in self.standing:
                answer = self.standing[route]
                return answer(request) if callable(answer) else answer
        if self.world is None:
            self.unscripted.append(request)
            raise AssertionError(f"nothing scripted for gh {request.route}: {argv!r}")
        return self.world_answers(request)

    def world_answers(self, request: GhRequest) -> Any:
        assert self.world is not None
        return _World(self.world).answer(request)


def _author(login: str) -> dict[str, str] | None:
    return None if login in ("", "ghost") else {"login": login}


def _graphql_author(login: str | None) -> dict[str, str] | None:
    return None if login in (None, "", "ghost") else {"login": login, "__typename": "User"}


def _rest_comment(comment: ThreadComment, **extra: Any) -> dict[str, Any]:
    return {"id": comment.id, "user": _author(comment.author), "body": comment.body,
            "created_at": comment.created_at, "updated_at": comment.updated_at,
            **extra}


def _comment_node(comment: ThreadComment, original_commit: str | None) -> dict[str, Any]:
    author = _author(comment.author)
    if author is not None and comment.author_name:
        author["name"] = comment.author_name
    return {
        "databaseId": comment.id,
        "author": author,
        "body": comment.body,
        "createdAt": comment.created_at,
        "updatedAt": comment.updated_at,
        "commit": {"oid": None},
        "originalCommit": {"oid": original_commit},
        "pullRequestReview": (None if comment.review_state is None
                              else {"state": comment.review_state.value}),
    }


def _page(nodes: list[Any]) -> dict[str, Any]:
    return {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}


def _review_thread_node(thread: Thread) -> dict[str, Any]:
    anchor = thread.anchor
    assert anchor is not None
    return {
        "id": thread.key,
        "isResolved": bool(thread.is_resolved),
        "resolvedBy": None if thread.resolved_by is None else {"login": thread.resolved_by},
        "isOutdated": anchor.is_outdated,
        "path": thread.path,
        "line": thread.line,
        "startDiffSide": None if anchor.start_side is None else _WORDS[anchor.start_side],
        "originalLine": anchor.original_line,
        "diffSide": None if anchor.side is None else _WORDS[anchor.side],
        "subjectType": "LINE",
        "comments": _page([_comment_node(c, anchor.original_commit)
                           | {"startLine": anchor.start_line,
                              "originalStartLine": anchor.original_start_line}
                           for c in thread.comments]),
    }


def _issue_node(thread: Thread) -> dict[str, Any]:
    comment = thread.comments[0]
    node = _comment_node(comment, None)
    return {"id": thread.key, "databaseId": comment.id, "author": node["author"],
            "body": comment.body, "createdAt": comment.created_at,
            "updatedAt": comment.updated_at}


def _summary_node(thread: Thread) -> dict[str, Any]:
    comment = thread.comments[0]
    node = _comment_node(comment, None)
    return {"id": thread.key, "databaseId": comment.id, "author": node["author"],
            "body": comment.body, "state": None if thread.state is None else thread.state.value,
            "createdAt": comment.created_at}


def _node(thread: Thread) -> dict[str, Any]:
    if thread.kind == CommentKind.REVIEW:
        return {"__typename": "PullRequestReviewThread", **_review_thread_node(thread)}
    if thread.kind == CommentKind.ISSUE:
        return {"__typename": "IssueComment", **_issue_node(thread)}
    return {"__typename": "PullRequestReview", **_summary_node(thread)}


def _thread_connections(record: Any) -> dict[str, Any]:
    return {
        "reviewThreads": _page([_review_thread_node(t) for t in record.threads
                                if t.kind == CommentKind.REVIEW]),
        "comments": _page([_issue_node(t) for t in record.threads
                           if t.kind == CommentKind.ISSUE]),
        "reviews": _page([_summary_node(t) for t in record.threads
                          if t.kind == CommentKind.REVIEW_SUMMARY]),
    }


def _graphql_failure(error: GhError) -> Failure:
    return Failure(f"gh: {error}")


_WHOSE: dict[str, Whose] = {"--author=@me": "author",
                            "--review-requested=@me": "review-requested",
                            "--mentions=@me": "mentions"}


class _World:
    def __init__(self, world: FakeGitHub) -> None:
        self.world = world

    def answer(self, request: GhRequest) -> Any:
        if request.route == "repo clone":
            if Repo.parse(request.path) not in self.world.repos:
                return Failure("GraphQL: Could not resolve to a Repository with "
                               f"the name '{request.path}'.")
            Path(request.argv[4]).mkdir(parents=True)
            return Raw("")
        if request.route == "repo view":
            if Repo.parse(request.path) not in self.world.repos:
                return Failure("GraphQL: Could not resolve to a Repository with "
                               f"the name '{request.path}'. (repository)")
            return {"nameWithOwner": request.path}
        if request.route == "search prs":
            return self._search(request)
        if request.route == "graphql":
            return self._graphql(request)
        return self._rest(request)

    def _search(self, request: GhRequest) -> Any:
        argv = request.argv
        repos = ([Repo.parse(a.split("=", 1)[1]) for a in argv if a.startswith("--repo=")]
                 or sorted(self.world.repos, key=str))
        if not any(repo in self.world.repos for repo in repos):
            return Failure(f"{SEARCH_REFUSED} (HTTP 422)")
        whose = next(_WHOSE[a] for a in argv if a in _WHOSE)
        found = self.world.search(repos, whose)
        return [{"number": pr.number, "repository": {"nameWithOwner": str(pr.repo)}}
                for pr in found]

    def _record(self, repo: str, number: int) -> Any:
        return self.world.prs.get(a_pr(number, repo))

    def _rest(self, request: GhRequest) -> Any:
        method, path = request.method, request.path
        routes = (
            ("GET", r"user", self._user),
            ("GET", r"user/repos\?.*", self._listed),
            ("GET", r"repos/([^/]+/[^/]+)", self._repo),
            ("GET", r"repos/([^/]+/[^/]+)/pulls/(\d+)", self._pull),
            ("PATCH", r"repos/([^/]+/[^/]+)/pulls/(\d+)", self._close),
            ("GET", r"repos/([^/]+/[^/]+)/pulls/(\d+)/reviews/(\d+)/comments",
             self._review_comments),
            ("POST", r"repos/([^/]+/[^/]+)/issues/(\d+)/comments", self._comment_on_pr),
            ("POST", r"repos/([^/]+/[^/]+)/pulls/comments/(\d+)/reactions", self._react),
            ("POST", r"repos/([^/]+/[^/]+)/pulls/(\d+)/comments", self._review_comment),
            ("POST", r"repos/([^/]+/[^/]+)/pulls/(\d+)/reviews", self._review),
            ("POST", r"repos/([^/]+/[^/]+)/pulls/(\d+)/reviews/(\d+)/events", self._submit),
            ("GET", r"repos/([^/]+/[^/]+)/pulls/comments/(\d+)", self._exists(CommentKind.REVIEW)),
            ("GET", r"repos/([^/]+/[^/]+)/issues/comments/(\d+)", self._exists(CommentKind.ISSUE)),
            ("GET", r"repos/([^/]+/[^/]+)/pulls/(\d+)/reviews/(\d+)",
             self._exists(CommentKind.REVIEW_SUMMARY)),
            ("DELETE", r"repos/([^/]+/[^/]+)/pulls/comments/(\d+)", self._delete(CommentKind.REVIEW)),
            ("DELETE", r"repos/([^/]+/[^/]+)/issues/comments/(\d+)", self._delete(CommentKind.ISSUE)),
            ("DELETE", r"repos/([^/]+/[^/]+)/pulls/(\d+)/reviews/(\d+)",
             self._delete(CommentKind.REVIEW_SUMMARY)),
        )
        for wanted, pattern, handler in routes:
            match = re.fullmatch(pattern, path)
            if wanted == method and match:
                return handler(request, *match.groups())
        raise AssertionError(f"GitHub has no {method} {path} here")

    def _login(self, token: str | None) -> str:
        return next(login for login, held in self.world.tokens.items() if held == token)

    def _user(self, request: GhRequest) -> Any:
        login = self._login(request.token)
        body = json.dumps({"login": login})
        if not request.include:
            return Raw(body)
        scopes = ", ".join(self.world.granted.get(login, ()))
        return Raw(f"HTTP/2.0 200 OK\nX-Oauth-Scopes: {scopes}\n\n{body}")

    def _repo_answer(self, repo: Repo) -> dict[str, Any]:
        return {"full_name": str(repo), "default_branch": "main",
                "permissions": {"pull": True, "push": repo not in self.world.read_only}}

    def _listed(self, request: GhRequest) -> Any:
        return [self._repo_answer(repo) for repo in self.world.listed]

    def _repo(self, request: GhRequest, repo: str) -> Any:
        if Repo.parse(repo) not in self.world.repos:
            return Failure(NOT_FOUND)
        return self._repo_answer(Repo.parse(repo))

    def _pull(self, request: GhRequest, repo: str, number: str) -> Any:
        record = self._record(repo, int(number))
        if record is None:
            return Failure(NOT_FOUND)
        state = record.state
        return {
            "number": record.pr.number, "title": state.title, "html_url": state.url,
            "user": None if state.author is None else {"login": state.author},
            "head": {"sha": state.head_sha, "ref": state.branch},
            "base": {"ref": state.base_branch},
            "body": state.body or None, "draft": state.draft,
            "created_at": record.created_at,
            "changed_files": state.changed_files, "additions": state.additions,
            "deletions": state.deletions,
            "mergeable": state.mergeable or None,
            "mergeable_state": None if state.mergeable_state == "unknown" else state.mergeable_state,
            "state": "open" if record.status == "OPEN" else "closed",
        }

    def _close(self, request: GhRequest, repo: str, number: str) -> Any:
        assert request.payload == {"state": "closed"}, request.payload
        if self.world.close(a_pr(int(number), repo)) is not None:
            return Failure(NOT_FOUND)
        return self._pull(request, repo, number)

    def _review_comments(self, request: GhRequest, repo: str, number: str,
                         review_id: str) -> Any:
        listed = self.world.review_comments(a_pr(int(number), repo), int(review_id))
        return [_rest_comment(one.comment, path=one.path) for one in listed]

    def _comment_on_pr(self, request: GhRequest, repo: str, number: str) -> Any:
        try:
            posted = self.world.comment_on_pr(a_pr(int(number), repo),
                                              request.fields["body"])
        except GhError:
            return Failure(NOT_FOUND)
        return _rest_comment(posted.comment, node_id=posted.key)

    def _react(self, request: GhRequest, repo: str, comment_id: str) -> Any:
        assert request.payload == {"content": "+1"}, request.payload
        try:
            self.world.react(Repo.parse(repo), int(comment_id))
        except GhError:
            return Failure(NOT_FOUND)
        return {"id": 1, "content": "+1"}

    def _draft(self, placed: dict[str, Any]) -> tuple[Location, str]:
        sides = {word: side for side, word in _WORDS.items()}
        start_line = placed.get("start_line")
        start_side = None if start_line is None else sides[placed["start_side"]]
        return (Location(placed["path"], placed["line"], sides[placed["side"]],
                         start_line, start_side),
                placed["body"])

    def _review_comment(self, request: GhRequest, repo: str, number: str) -> Any:
        payload = request.payload
        try:
            posted = self.world.post_review_comment(a_pr(int(number), repo),
                                                    payload["commit_id"],
                                                    *self._draft(payload))
        except GhError:
            return Failure(NOT_FOUND)
        return _rest_comment(posted)

    def _review(self, request: GhRequest, repo: str, number: str) -> Any:
        payload = request.payload
        record = self._record(repo, int(number))
        if record is not None and record.pending_review is not None:
            return Failure(UNPROCESSABLE)
        try:
            sent = self.world.post_review(
                a_pr(int(number), repo), payload["commit_id"], Verdict(payload["event"]),
                payload.get("body"), [self._draft(c) for c in payload["comments"]])
        except GhError:
            return Failure(NOT_FOUND)
        return {"id": sent.id, "state": payload["event"]}

    def _submit(self, request: GhRequest, repo: str, number: str, review_id: str) -> Any:
        payload = request.payload
        record = self._record(repo, int(number))
        if record is None or record.pending_review != int(review_id):
            return Failure(NOT_FOUND)
        self.world.submit_review(a_pr(int(number), repo), int(review_id),
                                 record.state.head_sha, Verdict(payload["event"]),
                                 payload.get("body"))
        return {"id": int(review_id), "state": payload["event"]}

    def _exists(self, kind: CommentKind) -> Any:
        def exists(request: GhRequest, repo: str, *ids: str) -> Any:
            pr = int(ids[0]) if len(ids) == 2 else 0
            if not self.world.comment_exists(a_pr(pr, repo), kind, int(ids[-1])):
                return Failure(NOT_FOUND)
            return {"id": int(ids[-1])}
        return exists

    def _delete(self, kind: CommentKind) -> Any:
        def delete(request: GhRequest, repo: str, *ids: str) -> Any:
            pr = int(ids[0]) if len(ids) == 2 else 0
            if not self.world.comment_exists(a_pr(pr, repo), kind, int(ids[-1])):
                return Failure(NOT_FOUND)
            self.world.delete_comment(a_pr(pr, repo), kind, int(ids[-1]))
            return Raw("")
        return delete

    def _graphql(self, request: GhRequest) -> Any:
        query, variables = request.query, request.variables
        if "unresolveReviewThread" in query:
            return self._mutation(lambda: self.world.unresolve_thread(variables["threadId"]),
                                  "unresolveReviewThread")
        if "resolveReviewThread" in query:
            return self._mutation(lambda: self.world.resolve_thread(variables["threadId"]),
                                  "resolveReviewThread")
        if "addPullRequestReviewThreadReply" in query:
            try:
                posted = self.world.reply_to_thread(variables["threadId"], variables["body"])
            except GhError as error:
                return _graphql_failure(error)
            assert posted is not None
            return {"data": {"addPullRequestReviewThreadReply": {
                "comment": _comment_node(posted, None)}}}
        if "addPullRequestReviewThread(" in query:
            return self._add_to_pending_review(variables)
        if "states: PENDING" in query:
            return self._pending_review(variables)
        if "viewerDidAuthor" in query:
            return self._relevance(variables)
        if "mergeStateStatus" in query:
            return self._pulls(query, variables)
        if "__typename" in query:
            found = self.world.thread(variables["id"])
            return {"data": {"node": None if found is None else _node(found)}}
        if "reviewThreads(" in query:
            return self._threads(variables)
        raise AssertionError(f"no such query here: {query[:80]!r}")

    def _add_to_pending_review(self, variables: dict[str, Any]) -> Any:
        sides = {word: side for side, word in _WORDS.items()}
        assert isinstance(variables["line"], int), "GraphQL takes no string for an Int"
        start_line = variables.get("startLine")
        assert start_line is None or isinstance(start_line, int), "GraphQL takes no string for an Int"
        where = Location(variables["path"], variables["line"], sides[variables["side"]],
                         start_line, None if start_line is None else sides[variables["startSide"]])
        try:
            added = self.world.add_to_pending_review(
                int(variables["reviewId"].removeprefix("PRR_")), where, variables["body"])
        except GhError as error:
            return _graphql_failure(error)
        return {"data": {"addPullRequestReviewThread": {
            "thread": {"id": f"PRRT_{added.id}"}}}}

    def _pending_review(self, variables: dict[str, Any]) -> Any:
        record = self._pull_of(variables)
        if record is None:
            return {"data": {"repository": {"pullRequest": None}}}
        nodes = ([] if record.pending_review is None
                 else [{"id": f"PRR_{record.pending_review}",
                        "databaseId": record.pending_review}])
        return {"data": {"repository": {"pullRequest": {"reviews": {"nodes": nodes}}}}}

    def _mutation(self, write: Any, name: str) -> Any:
        try:
            write()
        except GhError as error:
            return _graphql_failure(error)
        return {"data": {name: {"thread": {"id": "", "isResolved": True}}}}

    def _pull_of(self, variables: dict[str, Any]) -> Any:
        repo = f"{variables['owner']}/{variables['name']}"
        return self._record(repo, variables["number"])

    def _relevance(self, variables: dict[str, Any]) -> Any:
        record = self._pull_of(variables)
        if record is None:
            return {"data": {"repository": {"pullRequest": None}}}
        return {"data": {"repository": {"pullRequest": {
            "state": record.status,
            "viewerDidAuthor": record.state.author == self.world.account,
            "viewerLatestReview": {"state": "COMMENTED"} if record.viewer_reviewed else None,
        }}}}

    def _pulls(self, query: str, variables: dict[str, Any]) -> Any:
        repo = f"{variables['owner']}/{variables['name']}"
        found = {}
        for alias, number in re.findall(r"(\w+): pullRequest\(number: (\d+)\)", query):
            record = self._record(repo, int(number))
            found[alias] = None if record is None else self._pull_node(record)
        return {"data": {"repository": found}}

    def _pull_node(self, record: Any) -> dict[str, Any]:
        state = record.state
        return {
            **_thread_connections(record),
            "number": record.pr.number, "title": state.title, "url": state.url,
            "body": state.body, "isDraft": state.draft, "createdAt": record.created_at,
            "headRefName": state.branch, "baseRefName": state.base_branch,
            "headRefOid": state.head_sha, "changedFiles": state.changed_files,
            "additions": state.additions, "deletions": state.deletions,
            "mergeable": "MERGEABLE" if state.mergeable else "UNKNOWN",
            "mergeStateStatus": state.mergeable_state.upper(),
            "reviewDecision": state.review_decision,
            "author": _graphql_author(state.author),
            "reviewRequests": {"nodes": [
                {"requestedReviewer": {"slug": who[1:]} if who.startswith("@")
                 else {"login": who}}
                for who in state.pending_reviewers]},
            "verdicts": {"pageInfo": {"hasNextPage": False}, "nodes": [
                {"author": _graphql_author(r.author or ""),
                 "state": None if r.state is None else r.state.value,
                 "submittedAt": r.submitted_at,
                 "commit": None if r.commit_id is None else {"oid": r.commit_id}}
                for r in state.reviews]},
            "readiness": {"nodes": ([] if state.ready_for_review_at is None
                                    else [{"createdAt": state.ready_for_review_at}])},
            "pushes": {"pageInfo": {"hasNextPage": False}, "nodes": [
                {"__typename": "HeadRefForcePushedEvent", "createdAt": e.at}
                if e.is_force_push
                else {"__typename": "PullRequestCommit", "commit": {"committedDate": e.at}}
                for e in state.push_events]},
            "commits": {"nodes": [{"commit": {"checkSuites": {"nodes": [{"checkRuns": {"nodes": [
                {"databaseId": len(state.checks) - n, "name": c.name,
                 "status": None if c.status is None else c.status.upper(),
                 "conclusion": None if c.conclusion is None else c.conclusion.upper(),
                 "url": c.html_url, "summary": c.summary,
                 "startedAt": None, "completedAt": None}
                for n, c in enumerate(state.checks)]}}]}}}]},
        }

    def _threads(self, variables: dict[str, Any]) -> Any:
        record = self._pull_of(variables)
        if record is None:
            return {"data": {"repository": {"pullRequest": None}}}
        return {"data": {"repository": {"pullRequest": _thread_connections(record)}}}
