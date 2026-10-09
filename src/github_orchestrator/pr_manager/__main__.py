import argparse
import logging
import os
import sys
from pathlib import Path

from github_orchestrator.domain import Pr, Repo
from github_orchestrator.pr_manager import ManagedPr, PrManager
from github_orchestrator.settings import ConfigFile, Logs, Process
from github_orchestrator.wiring import make_container

log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="PR Agent Manager")
    parser.add_argument("--repo", required=True, type=Repo.parse, help="e.g. acme/widgets")
    parser.add_argument("--pr", required=True, type=int, help="PR number")
    args = parser.parse_args()

    pr = Pr(args.repo, args.pr)
    container = make_container(os.environ, Path.home(), ManagedPr(pr=pr, worktree=os.getcwd()))
    container.get(Logs).configure_logging(Process.PR_MANAGER, context=str(pr))
    problem = container.get(ConfigFile).check()
    if problem is not None:
        log.error("agent manager for %s not started: %s", pr, problem)
        print(problem, file=sys.stderr)
        sys.exit(2)
    container.get(PrManager).run()


if __name__ == "__main__":
    main()
