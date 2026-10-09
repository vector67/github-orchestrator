import re
from pathlib import Path

import github_orchestrator

SOURCE = Path(github_orchestrator.__file__).parent
FRONT_END = SOURCE.parents[1] / "frontend" / "app"
AGENT_NAMES = re.compile(r"claude|codex", re.IGNORECASE)

KNOWS_THE_AGENT = (
    "agent_runs/",
    "cli/_doctor.py",
    "cli/_install_checks.py",
    "settings/_renamed_keys.py",
)
GITHUB_BOT_LOGINS = ('_BOTS = frozenset({"claude", "codex", "copilot"})',)


def _naming_lines(root, paths, allowed):
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if relative.startswith(allowed):
            continue
        if AGENT_NAMES.search(relative):
            yield f"{relative} (its name)"
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if AGENT_NAMES.search(line) and line.strip() not in GITHUB_BOT_LOGINS:
                yield f"{relative}:{number}: {line.strip()}"


def test_only_agent_runs_doctor_and_the_legacy_keys_name_an_agent():
    named = list(_naming_lines(SOURCE, sorted(SOURCE.rglob("*.py")), KNOWS_THE_AGENT))

    assert named == [], (
        "which agent runs is agent_runs' secret; outside it only the doctor, its install "
        "checks and the renamed config keys may name one:\n" + "\n".join(named))


def test_the_front_end_names_no_agent():
    files = sorted(path for path in FRONT_END.rglob("*")
                   if path.is_file() and path.suffix in {".ts", ".gts", ".css", ".hbs"})
    named = list(_naming_lines(FRONT_END, files, ()))

    assert len(files) > 20, "the walk found no front end to check"
    assert named == [], (
        "the board shows the agent's display name from the board API, never a name of "
        "its own:\n" + "\n".join(named))
