import contextlib
import functools
import io
import re
import tempfile
from pathlib import Path

from tests.cli.support import Machine

_INVOCATION = re.compile(
    r"(?:github_orchestrator\.cli|…) thread "
    r"(open|plan|step|skip|reply|ticket|filed|ready|fail|draft)([^\n]*)"
)


def invocations(text: str) -> list[tuple[str, set[str]]]:
    joined = text.replace("\\\n", " ")
    return [
        (match.group(1), set(re.findall(r"--[a-z-]+", match.group(2))))
        for match in _INVOCATION.finditer(joined)
    ]


@functools.cache
def usage(verb: str) -> str:
    with tempfile.TemporaryDirectory() as scratch:
        machine = Machine(data_dir=Path(scratch), home=Path(scratch))
        machine.configure()
        shown = io.StringIO()
        with contextlib.redirect_stdout(shown):
            assert machine.cli().main(["thread", verb, "--help"]) == 0
    return shown.getvalue().split("\n\n", 1)[0]


def _flags(verb: str) -> tuple[set[str], set[str]]:
    shown = usage(verb)
    known = set(re.findall(r"(?<![\w-])(--[a-z-]+)", shown))
    optional = set(re.findall(r"\[(--[a-z-]+)", shown))
    return known - optional, known


def assert_the_cli_takes(verb: str, flags: set[str]) -> None:
    required, known = _flags(verb)
    assert required <= flags, (verb, flags)
    assert flags <= known, (verb, flags)
