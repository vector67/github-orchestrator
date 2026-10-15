# /// script
# requires-python = ">=3.13"
# dependencies = ["tree-sitter-language-pack>=1.22"]
# ///
import argparse
import dataclasses
import sys
import tempfile
from pathlib import Path

from pr_summary.clone import Clone, CloneFailed
from pr_summary.github import (
    HISTORY_DEPTH,
    GhFailed,
    History,
    changed_files,
    contents,
    earlier_prs,
    gh_cli,
    history,
    merge_base,
    pull_request,
    target,
)
from pr_summary.inputs import Contents, write_inputs
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
    parser.add_argument("--use-github-api", action="store_true", help="read files over the GitHub API when the working directory is not a clone of the repository")
    arguments = parser.parse_args()

    owner, repo, number = target(gh_cli, arguments.pr)
    pr = pull_request(gh_cli, owner, repo, number)
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
        base = merge_base(gh_cli, owner, repo, pr.base_sha, pr.head_sha)
        files = changed_files(gh_cli, owner, repo, number)
        read = contents(gh_cli, owner, repo)
        history_of = history(gh_cli, owner, repo, base)
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
    earlier = earlier_prs(gh_cli, owner, repo, pr, ticket, files, settings, history_of)
    out = Path(tempfile.mkdtemp(prefix="pr-summary-"))
    manifest = write_inputs(pr, files, read, earlier, settings, ticket, out)
    if not arguments.prepare_only:
        run_witnesses(manifest, launcher(PLUGIN_ROOT))
        print(report(manifest))
    print(f"Working files: {out}")


if __name__ == "__main__":
    try:
        main()
    except (GhFailed, CloneFailed) as failure:
        sys.exit(f"{type(failure).__name__}: {failure}")
