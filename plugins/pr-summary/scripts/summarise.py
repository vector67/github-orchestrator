# /// script
# requires-python = ">=3.13"
# dependencies = ["tree-sitter-language-pack>=1.22"]
# ///
import argparse
import sys
import tempfile
from pathlib import Path

from pr_summary.github import (
    GhFailed,
    changed_files,
    contents,
    earlier_prs,
    gh_cli,
    pull_request,
    target,
)
from pr_summary.inputs import write_inputs
from pr_summary.report import report
from pr_summary.settings import settings_from, ticket_key
from pr_summary.witnesses import launcher, run_witnesses

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REPO_CONFIG = ".github/pr-summary.toml"


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise a pull request by what was requested, claimed, intended and why.")
    parser.add_argument("pr", help="a pull request URL, or its number in the current repository")
    parser.add_argument("--config", type=Path, help="a TOML file with a [pr_summary] table, used when the repository has no .github/pr-summary.toml")
    parser.add_argument("--prepare-only", action="store_true", help="write the witnesses' input folders and stop")
    arguments = parser.parse_args()

    owner, repo, number = target(gh_cli, arguments.pr)
    pr = pull_request(gh_cli, owner, repo, number)
    read = contents(gh_cli, owner, repo)
    repo_config = read(pr.base_sha, REPO_CONFIG)
    fallback = arguments.config.read_text() if arguments.config else None
    settings = settings_from(repo_config.decode() if repo_config is not None else fallback)
    ticket = ticket_key(settings, title=pr.title, branch=pr.branch)
    files = changed_files(gh_cli, owner, repo, number)
    earlier = earlier_prs(gh_cli, owner, repo, pr, ticket, files, settings)
    out = Path(tempfile.mkdtemp(prefix="pr-summary-"))
    manifest = write_inputs(pr, files, read, earlier, settings, ticket, out)
    if not arguments.prepare_only:
        run_witnesses(manifest, launcher(PLUGIN_ROOT))
        print(report(manifest))
    print(f"Working files: {out}")


if __name__ == "__main__":
    try:
        main()
    except GhFailed as failure:
        sys.exit(f"gh failed: {failure}")
