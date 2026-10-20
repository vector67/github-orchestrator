# /// script
# requires-python = ">=3.13"
# dependencies = ["tree-sitter-language-pack>=1.22"]
# ///
import argparse
import dataclasses
import functools
import shutil
import sys
import tempfile
import time
from pathlib import Path

from pr_summary.clone import Clone, CloneFailed
from pr_summary.github import (
    HISTORY_DEPTH,
    GhFailed,
    History,
    changed_files,
    contents,
    earlier_prs,
    gh_as,
    gh_cli,
    history,
    merge_base,
    pull_request,
    target,
)
from pr_summary.inputs import (
    Contents,
    WorkDirNotEmpty,
    work_dir,
    write_inputs,
    write_surroundings,
)
from pr_summary.report import report
from pr_summary.settings import settings_from, ticket_key
from pr_summary.witnesses import launcher, run_witnesses

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REPO_CONFIG = ".github/pr-summary.toml"
NEEDS_CONFIRMATION = 3


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise a pull request by what was requested, claimed, intended and why.")
    parser.add_argument("pr", help="a pull request URL, or its number in the current repository")
    parser.add_argument("--config", type=Path, help="a TOML file with a [pr_summary] table, used when the repository has no .github/pr-summary.toml")
    parser.add_argument("--prepare-only", action="store_true", help="write the witnesses' input folders and stop")
    parser.add_argument("--work-dir", type=Path, help="write the witness folders here, creating it if missing; it must be empty")
    parser.add_argument("--use-github-api", action="store_true", help="read files over the GitHub API when the working directory is not a clone of the repository")
    parser.add_argument("--gh-account", help="run gh as this logged-in account, with the token gh auth token --user gives for it, instead of gh's active account")
    parser.add_argument("--mcp-config", type=Path, help="an MCP config file the witnesses load instead of every MCP server claude would find, so their servers are connected before they start")
    parser.add_argument("--earlier-primer", type=Path, help="the primer's output.json from an earlier run on this pull request, for the primer to start from")
    arguments = parser.parse_args()

    named = work_dir(arguments.work_dir) if arguments.work_dir else None
    gh = gh_as(arguments.gh_account) if arguments.gh_account else gh_cli
    owner, repo, number = target(gh, arguments.pr)
    pr = pull_request(gh, owner, repo, number)
    clone = Clone.find(Path.cwd(), owner, repo)
    unavailable = "the working directory is not a clone of it"
    if clone is not None:
        try:
            clone.fetch(number, pr.base_sha)
        except CloneFailed as failure:
            clone, unavailable = None, f"fetching the pull request into the clone failed: {failure}"
    read: Contents
    history_of: History
    if clone is not None:
        local = clone
        base = local.merge_base(pr.base_sha, pr.head_sha)
        files = local.changed_files(base, pr.head_sha)
        read = local.contents

        def history_of(path: str) -> list[str]:
            return local.history(base, path, HISTORY_DEPTH)

    elif arguments.use_github_api:
        base = merge_base(gh, owner, repo, pr.base_sha, pr.head_sha)
        files = changed_files(gh, owner, repo, number)
        read = contents(gh, owner, repo)
        history_of = history(gh, owner, repo, base)
    else:
        sys.stderr.write(
            f"Cannot read {owner}/{repo} locally: {unavailable}.\n"
            f"Run this from a clone of {owner}/{repo}, or confirm reading its {pr.changed_file_count} changed files over the GitHub API "
            f"(about {2 * pr.changed_file_count + 25} API calls) by adding --use-github-api.\n"
        )
        sys.exit(NEEDS_CONFIRMATION)
    pr = dataclasses.replace(pr, base_sha=base)

    repo_config = read(base, REPO_CONFIG)
    fallback = arguments.config.read_text() if arguments.config else None
    settings = settings_from(repo_config.decode() if repo_config is not None else fallback)
    ticket = ticket_key(settings, title=pr.title, branch=pr.branch)
    earlier = earlier_prs(gh, owner, repo, pr, ticket, files, settings, history_of)
    out = named or Path(tempfile.mkdtemp(prefix="pr-summary-"))
    manifest = write_inputs(pr, files, read, earlier, settings, ticket, out)
    if arguments.earlier_primer:
        shutil.copy(arguments.earlier_primer, manifest["primer"] / "earlier_primer.json")
    if clone is not None:
        for reader in ("implementation", "primer"):
            write_surroundings(manifest[reader], files, settings, functools.partial(clone.export, pr.head_sha))
    if arguments.prepare_only:
        print(f"Working files: {out}")
        return
    failures = run_witnesses(manifest, launcher(PLUGIN_ROOT, arguments.mcp_config), time.sleep)
    print(report(manifest))
    print(f"Working files: {out}")
    if failures:
        sys.exit("Witnesses failed: " + "; ".join(f"{witness}: {reason}" for witness, reason in failures.items()))


if __name__ == "__main__":
    try:
        main()
    except (GhFailed, CloneFailed, WorkDirNotEmpty) as failure:
        sys.exit(f"{type(failure).__name__}: {failure}")
