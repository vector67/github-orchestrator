import logging
from typing import Any

from github_orchestrator.domain import Pr
from github_orchestrator.github._gh_cli import Gh
from github_orchestrator.github.interface import (
    Check,
    GhError,
    PullRequestState,
    PushEvent,
    Relevance,
    Review,
    review_state_of,
)

log = logging.getLogger(__name__)

PAGE = 100
SUITES = 50

STATE_FIELDS = """
      number title url body isDraft createdAt
      headRefName baseRefName headRefOid
      changedFiles additions deletions
      mergeable mergeStateStatus reviewDecision
      author { login __typename }
      reviewRequests(first: %(page)d) {
        nodes { requestedReviewer { ... on User { login } ... on Team { slug } } }
      }
      verdicts: reviews(first: %(page)d) {
        pageInfo { hasNextPage }
        nodes { author { login __typename } state submittedAt commit { oid } }
      }
      readiness: timelineItems(itemTypes: [READY_FOR_REVIEW_EVENT], last: 1) {
        nodes { ... on ReadyForReviewEvent { createdAt } }
      }
      pushes: timelineItems(itemTypes: [PULL_REQUEST_COMMIT, HEAD_REF_FORCE_PUSHED_EVENT],
                            first: %(page)d) {
        pageInfo { hasNextPage }
        nodes {
          __typename
          ... on PullRequestCommit { commit { committedDate } }
          ... on HeadRefForcePushedEvent { createdAt }
        }
      }
      commits(last: 1) {
        nodes { commit { checkSuites(first: %(suites)d) { nodes {
          checkRuns(first: %(page)d, filterBy: {checkType: LATEST}) { nodes {
            databaseId name status conclusion url detailsUrl summary startedAt completedAt
          } }
        } } } }
      }
""" % {"page": PAGE, "suites": SUITES}

_EVENTS = {"PullRequestCommit": "committed",
           "HeadRefForcePushedEvent": "head_ref_force_pushed"}

_RELEVANCE_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      state
      viewerDidAuthor
      viewerLatestReview { state }
    }
  }
}
"""


def pulls_query(numbers: list[int], fields: str, declarations: str = "") -> str:
    aliased = "\n".join(f"    pr{n}: pullRequest(number: {n}) {{{fields}    }}"
                        for n in numbers)
    more = f", {declarations}" if declarations else ""
    return (f"query($owner: String!, $name: String!{more}) {{\n"
            "  repository(owner: $owner, name: $name) {\n"
            f"{aliased}\n  }}\n}}\n")


def _user_login(thing: dict[str, Any] | None) -> str | None:
    if not thing:
        return None
    user = thing.get("user")
    if not user:
        return None
    login = user.get("login")
    return login if isinstance(login, str) else None


def _author_login(author: dict[str, Any] | None) -> str | None:
    if not author:
        return None
    login = author.get("login")
    if not isinstance(login, str):
        return None
    return f"{login}[bot]" if author.get("__typename") == "Bot" else login


def _lower(word: object) -> str | None:
    return word.lower() if isinstance(word, str) else None


def _dedupe_check_runs_by_name(check_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[Any, dict[str, Any]] = {}
    for run in check_runs:
        name = run.get("name")
        key = (
            run.get("startedAt") or "",
            run.get("completedAt") or "",
            run.get("databaseId") or 0,
        )
        current = latest.get(name)
        if current is None:
            latest[name] = run
            continue
        current_key = (
            current.get("startedAt") or "",
            current.get("completedAt") or "",
            current.get("databaseId") or 0,
        )
        if key > current_key:
            latest[name] = run
    return list(latest.values())


def _page_of(run: dict[str, Any]) -> str | None:
    details = run.get("detailsUrl")
    if isinstance(details, str) and details.startswith("https://github.com/"):
        return details
    return run.get("url")


def _checks(pull: dict[str, Any]) -> tuple[Check, ...]:
    heads = (pull.get("commits") or {}).get("nodes") or []
    head = ((heads[-1] or {}).get("commit") or {}) if heads else {}
    suites = (head.get("checkSuites") or {}).get("nodes") or []
    runs = sorted((run for suite in suites
                   for run in ((suite or {}).get("checkRuns") or {}).get("nodes") or [] if run),
                  key=lambda run: run.get("databaseId") or 0, reverse=True)
    return tuple(
        Check(name=r["name"], status=_lower(r.get("status")),
              conclusion=_lower(r.get("conclusion")), html_url=_page_of(r),
              summary=r.get("summary"))
        for r in _dedupe_check_runs_by_name(runs)
    )


def _more(connection: dict[str, Any] | None) -> bool:
    return bool(((connection or {}).get("pageInfo") or {}).get("hasNextPage"))


def _rest_reviews(gh: Gh, pr: Pr) -> tuple[Review, ...]:
    listed = gh.api(f"/repos/{pr.repo}/pulls/{pr.number}/reviews", paginate=True)
    return tuple(
        Review(author=_user_login(r), state=review_state_of(r.get("state")),
               submitted_at=r.get("submitted_at"), commit_id=r.get("commit_id"))
        for r in listed
    )


def _reviews(gh: Gh, pr: Pr, pull: dict[str, Any]) -> tuple[Review, ...]:
    verdicts = pull.get("verdicts")
    if _more(verdicts):
        return _rest_reviews(gh, pr)
    return tuple(
        Review(author=_author_login(r.get("author")), state=review_state_of(r.get("state")),
               submitted_at=r.get("submittedAt"),
               commit_id=(r.get("commit") or {}).get("oid"))
        for r in (verdicts or {}).get("nodes") or []
    )


def _rest_push_events(gh: Gh, pr: Pr) -> tuple[PushEvent, ...]:
    try:
        events = gh.api(
            f"/repos/{pr.repo}/issues/{pr.number}/timeline",
            jq='[.[] | select(.event == "committed" or .event == "head_ref_force_pushed") '
               '| {event: .event, at: (.created_at // .committer.date)}]',
            paginate=True,
        )
    except Exception:
        log.exception("Failed to fetch push timeline for %s", pr)
        return ()
    return tuple(PushEvent(event=e.get("event") or "", at=e.get("at") or "")
                 for e in events)


def _push_events(gh: Gh, pr: Pr, pull: dict[str, Any]) -> tuple[PushEvent, ...]:
    pushes = pull.get("pushes")
    if _more(pushes):
        return _rest_push_events(gh, pr)
    return tuple(
        PushEvent(event=_EVENTS.get(e.get("__typename") or "", ""),
                  at=(e.get("createdAt") or (e.get("commit") or {}).get("committedDate")
                      or ""))
        for e in (pushes or {}).get("nodes") or []
    )


def _ready_for_review_at(pull: dict[str, Any]) -> str | None:
    if pull.get("isDraft"):
        return None
    ready = [e.get("createdAt") for e in (pull.get("readiness") or {}).get("nodes") or []
             if e and e.get("createdAt")]
    if ready:
        return str(ready[-1])
    created_at = pull.get("createdAt")
    return None if created_at is None else str(created_at)


def _pending_reviewers(pull: dict[str, Any]) -> tuple[str, ...]:
    pending: list[str] = []
    for request in (pull.get("reviewRequests") or {}).get("nodes") or []:
        reviewer = (request or {}).get("requestedReviewer") or {}
        if "login" in reviewer:
            pending.append(reviewer["login"])
        elif "slug" in reviewer:
            pending.append(f"@{reviewer['slug']}")
    return tuple(pending)


def state_of(gh: Gh, account: str, pr: Pr, pull: dict[str, Any]) -> PullRequestState:
    author = _author_login(pull.get("author"))
    return PullRequestState(
        title=pull.get("title"),
        url=pull.get("url"),
        author=author,
        branch=pull.get("headRefName"),
        base_branch=pull.get("baseRefName"),
        head_sha=pull.get("headRefOid"),
        body=pull.get("body") or "",
        draft=bool(pull.get("isDraft", False)),
        changed_files=pull.get("changedFiles"),
        additions=pull.get("additions"),
        deletions=pull.get("deletions"),
        mergeable=pull.get("mergeable") == "MERGEABLE",
        mergeable_state=_lower(pull.get("mergeStateStatus")) or "unknown",
        checks=_checks(pull),
        reviews=_reviews(gh, pr, pull),
        review_decision=pull.get("reviewDecision"),
        pending_reviewers=_pending_reviewers(pull),
        ready_for_review_at=_ready_for_review_at(pull),
        push_events=() if author == account else _push_events(gh, pr, pull),
    )


def _error_text(result: dict[str, Any]) -> str:
    errors = result.get("errors")
    if not isinstance(errors, list):
        return ""
    return "; ".join(str(e.get("message") or e) if isinstance(e, dict) else str(e)
                     for e in errors)


def pulls(gh: Gh, prs: list[Pr], fields: str,
          declarations: str = "") -> tuple[dict[str, Any], str]:
    repo = prs[0].repo
    result = gh.graphql(pulls_query([pr.number for pr in prs], fields, declarations),
                        {"owner": repo.owner, "name": repo.name})
    if not isinstance(result, dict):
        raise GhError(f"the pull request query for {repo} answered "
                      f"{type(result).__name__}, not an object")
    found = ((result.get("data") or {}).get("repository")) or {}
    return found, _error_text(result)


def pr_state(gh: Gh, account: str, pr: Pr) -> PullRequestState:
    found, errors = pulls(gh, [pr], STATE_FIELDS)
    pull = found.get(f"pr{pr.number}")
    if not isinstance(pull, dict):
        raise GhError(f"the state query for {pr} answered with no pull request"
                      + (f": {errors}" if errors else ""))
    if errors:
        log.warning("the state query for %s carried errors beside it: %s", pr, errors)
    return state_of(gh, account, pr, pull)


def head_branch(gh: Gh, pr: Pr) -> str | None:
    try:
        answer = gh.api(f"/repos/{pr.repo}/pulls/{pr.number}")
    except GhError as e:
        log.warning("could not read the head branch of %s: %s", pr, e)
        return None
    branch = (answer.get("head") or {}).get("ref")
    return branch if isinstance(branch, str) and branch else None


def is_closed(gh: Gh, pr: Pr) -> bool | None:
    try:
        answer = gh.api(f"repos/{pr.repo}/pulls/{pr.number}")
    except GhError as e:
        log.warning("could not tell whether %s is closed: %s", pr, e)
        return None
    return bool(answer.get("state") == "closed")


def relevance(gh: Gh, pr: Pr) -> Relevance | None:
    owner, name = pr.repo.owner, pr.repo.name
    gql = gh.graphql(_RELEVANCE_QUERY, {"owner": owner, "name": name, "number": pr.number})
    pr_data = (((gql or {}).get("data") or {}).get("repository", {}) or {}).get("pullRequest")
    if not pr_data:
        return None
    return Relevance(
        state=pr_data.get("state"),
        viewer_did_author=bool(pr_data.get("viewerDidAuthor")),
        viewer_reviewed=pr_data.get("viewerLatestReview") is not None,
    )
