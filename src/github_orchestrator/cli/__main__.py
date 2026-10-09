import os
import sys
from collections.abc import Sequence
from pathlib import Path

from github_orchestrator.cli import Cli
from github_orchestrator.wiring import instance_refused, make_container, with_instance

INSTANCE_OPTION = "--instance"


def named_instance(argv: Sequence[str]) -> str | None:
    named = None
    for at, argument in enumerate(argv):
        if argument == INSTANCE_OPTION and at + 1 < len(argv):
            named = argv[at + 1]
        elif argument.startswith(f"{INSTANCE_OPTION}="):
            named = argument.partition("=")[2]
    return named


def main() -> int:
    argv = sys.argv[1:]
    env = with_instance(os.environ, named_instance(argv))
    refused = instance_refused(env)
    if refused is not None:
        print(refused, file=sys.stderr)
        return 2
    cli: Cli = make_container(env, Path.home()).get(Cli)
    return cli.main(argv)


if __name__ == "__main__":
    sys.exit(main())
