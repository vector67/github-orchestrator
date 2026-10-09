from collections.abc import Sequence

from github_orchestrator.agent_runs._report_commands import ReportCommands
from github_orchestrator.agent_runs._rules import test_parallelism_note
from github_orchestrator.agent_runs.interface import FixComment, Replied
from github_orchestrator.domain import Pr

LARGE_PR_LOC_THRESHOLD = 400

REBASE_ON_MAIN = "/rebase-on-main"


def _draft_command(commands: ReportCommands, pr: Pr) -> str:
    return commands.draft(
        pr, path="<the file, relative to the repo root>",
        line="<the line on the pull request's head>",
        start_line="<the first line, where it spans several>",
        body_file="<a file holding the comment, as you would post it>")


def _findings_as_drafts(draft_command: str, rest: str, changes_file: str) -> str:
    return (
        "Hand each finding that belongs on a line of the diff back as a "
        "draft review comment, one command per finding: "
        f"`{draft_command}`. Write the comment as you would post it "
        "to the author; nothing reaches GitHub until the reviewer sends it "
        f"from the board. Append {rest} to `{changes_file}` in the repo "
        "root, under the most recent `## [...]` header."
    )


def review_prompt(commands: ReportCommands, changes_file: str, pr: Pr, title: str, url: str,
                  branch: str, additions: int, deletions: int) -> str:
    draft_command = _draft_command(commands, pr)
    total_loc = additions + deletions
    if total_loc < LARGE_PR_LOC_THRESHOLD:
        return (
            f"You have been asked to review \"{title}\" (branch {branch}, URL {url}). "
            "Start with the tests to understand expected behavior, then walk the "
            "implementation changes against those expectations."
            "\n\n"
            "Extract the Jira ticket from the branch using regex ([A-Za-z]+-[0-9]+) "
            "and fetch its context via the Atlassian MCP tools; also find related PRs "
            "(especially closed ones on the same Jira ticket) for additional context. "
            + _findings_as_drafts(draft_command, "anything that is not about one line",
                                  changes_file)
        )
    return (
        f"You have been asked to perform an in-depth review of \"{title}\" "
        f"(branch {branch}, URL {url}). This is a large change set "
        f"({total_loc} LOC modified), so plan a careful pass."
        "\n\n"
        "Begin with the tests: read every new and modified test file, understand "
        "what behavior is being asserted, and identify gaps in coverage. Map the "
        "full testing surface before touching anything else."
        "\n\n"
        "Then walk through the implementation files and check each change against "
        "the tests; flag any behavior change that lacks a corresponding test, and "
        "note any abstractions that look premature or hard to reason about."
        "\n\n"
        "Before drawing conclusions, research the broader context: extract the Jira "
        "ticket from the branch using regex ([A-Za-z]+-[0-9]+) and fetch it via the "
        "Atlassian MCP tools, then find related PRs (especially closed ones on the "
        "same Jira ticket) to understand prior decisions and constraints."
        "\n\n"
        + _findings_as_drafts(
            draft_command,
            "what is not about one line (cross-cutting concerns, "
            "architecture-level observations and unresolved questions)", changes_file)
    )


def _quoted(text: str) -> str:
    return "\n".join(f"> {line}" for line in text.splitlines())


def _last_review(verdict: str, said: FixComment | None) -> str:
    stated = f"Your last review on GitHub: {verdict.replace('-', ' ')}."
    if said is None:
        return stated + " None of your reviews carried a summary."
    return (f"{stated} The newest review summary you wrote"
            f"{f' ({said.created_at})' if said.created_at else ''} said:\n\n{_quoted(said.body)}")


def _commits_since(since: str | None, commits: Sequence[str] | None) -> str:
    if since is None:
        return ("Which commit you last reviewed is not on record, so review the whole branch "
                "against its base.")
    if commits is None:
        return (f"The commit you last reviewed or commented on, {since}, is not in this branch's "
                "history: "
                "the branch was most likely rebased or force-pushed. Review the whole branch "
                f"against its base, and if `git fetch origin {since}` brings the old commit "
                f"back, compare the two with `git range-diff`.")
    if not commits:
        return (f"No commits have landed since you last reviewed or commented, at {since}; the "
                "answer may be in the replies alone.")
    listed = "\n".join(f"- {commit}" for commit in commits)
    return (f"The commits since you last reviewed or commented, at {since}, newest first:\n\n{listed}\n\n"
            f"Read them with `git log -p {since}..HEAD`.")


def _where(path: str | None, line: int | None) -> str:
    if path is None:
        return "On the pull request"
    return f"On {path}:{line}" if line is not None else f"On {path}"


def _replies(replied: Replied) -> str:
    if not replied:
        return "None of the threads you opened has a reply."
    threads = "\n\n".join(
        f"{_where(path, line)}:\n" + "\n".join(
            f"- {comment.author}: {' '.join(comment.body.split())}" for comment in comments)
        for path, line, comments in replied)
    return f"The threads you opened that have a reply:\n\n{threads}"


def rereview_prompt(commands: ReportCommands, changes_file: str, pr: Pr, title: str, url: str,
                    branch: str, *, verdict: str, said: FixComment | None, since: str | None,
                    commits: Sequence[str] | None, replied: Replied) -> str:
    return (
        f"You have been asked to re-review \"{title}\" (branch {branch}, URL {url}). "
        "You reviewed it before and the author has asked for your review again. Review "
        "what changed since your last review rather than the whole pull request afresh."
        "\n\n" + _last_review(verdict, said)
        + "\n\n" + _commits_since(since, commits)
        + "\n\n" + _replies(replied)
        + "\n\n"
        "Check each point you raised before: was it addressed by a commit, answered in a "
        "reply, or left open? Do not raise a point again when the author's answer settles "
        "it. Then look for new problems in the code that changed. "
        + _findings_as_drafts(_draft_command(commands, pr),
                              "anything that is not about one line", changes_file)
    )


def fix_check_prompt(changes_file: str, pr: Pr, check: str, summary: str | None, push: bool,
                     workers: int) -> str:
    if push:
        push_instr = (
            "Commit your fix, then push the branch so CI re-runs (use "
            "`git push`, or `git push --force-with-lease` if history was "
            "rewritten). This pushes every accumulated CI-failure fix commit "
            "from earlier instances along with your own — you are the last "
            "queued CI-failure fix."
        )
    else:
        push_instr = (
            "Commit your fix but DO NOT push the branch — other CI-failure "
            "fixes are still queued, and a later instance will push all of "
            "them together once every failing check has been addressed."
        )
    return (
        f"CI check '{check}' failed on PR {pr.in_repo} in {pr.repo}. "
        + (f"Check summary: {summary}. " if summary else "")
        + "Investigate and fix ONLY this specific check's failure. Other "
        "failing checks are handled by their own separate runs, so do not "
        "try to fix everything at once. "
        + test_parallelism_note(workers).strip() + " "
        + push_instr
        + " Then append a short summary of what you found and changed to "
        f"`{changes_file}` in the repo root, under the most recent "
        "`## [...]` header (just append to the end of the file)."
    )


def rebase_prompt(pr: Pr, reason: str) -> str:
    return (
        f"PR {pr.in_repo} in {pr.repo} has become unmergeable. "
        f"Reason: {reason}. "
        f"Use {REBASE_ON_MAIN} to rebase the branch and resolve the conflicts."
    )
