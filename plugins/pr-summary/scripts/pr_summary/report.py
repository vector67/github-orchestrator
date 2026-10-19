import json
from pathlib import Path
from typing import Any

from pr_summary.witnesses import challenge_folders

WITNESS_FIELDS = ("witness", "display", "claims", "gaps")
MISMATCH_FIELDS = ("lower", "higher", "kind", "text", "claims")
ORDER = ("requested", "claimed", "implementation", "tests", "why")


def _loaded(folder: Path | None, fields: tuple[str, ...], top: str | None = None) -> dict[str, Any] | str:
    if folder is None:
        return "No ticket found."
    path = folder / "output.json"
    if not path.exists():
        return "no output.json."
    try:
        content: dict[str, Any] | Any = json.loads(path.read_text())
    except json.JSONDecodeError:
        return "output.json is not valid JSON."
    if not isinstance(content, dict):
        return "output.json is not an object."
    if "unavailable" in content:
        return f"its tools stayed unavailable: {content['unavailable']}"
    items = content.get(top, None) if top else [content]
    if not isinstance(items, list):
        return f"output.json has no {top}."
    for item in items:
        missing = [field for field in fields if not isinstance(item, dict) or field not in item]
        if missing:
            return f"output.json has no {missing[0]}."
    return content


def _said(name: str, loaded: dict[str, Any] | str) -> str:
    if isinstance(loaded, str):
        return loaded if loaded == "No ticket found." else f"{name.capitalize()} failed: {loaded}"
    gaps = "".join(f"\n- {gap}" for gap in loaded["gaps"])
    return f"{loaded['display']}{gaps}"


def report(manifest: dict[str, Path]) -> str:
    witnesses = {name: _loaded(manifest.get(name), WITNESS_FIELDS) for name in ORDER}
    alignment = _loaded(manifest.get("alignment"), MISMATCH_FIELDS, top="mismatches")
    if not isinstance(alignment, str):
        alignment = _challenged(manifest["alignment"], alignment)
    sections = [
        f"## Requested\n{_said('requested', witnesses['requested'])}",
        f"## Claimed\n{_said('claimed', witnesses['claimed'])}",
        f"## Intent\n**Implementation:** {_said('implementation', witnesses['implementation'])}\n\n**Tests:** {_said('tests', witnesses['tests'])}",
        f"## Why\n{_said('why', witnesses['why'])}",
        f"## Alignment\n{_alignment(witnesses, alignment)}",
    ]
    return "\n\n".join(sections) + "\n"


def _falsified_by(alignment: Path, number: int) -> str | None:
    critic, verdict = challenge_folders(alignment, number)
    judged = _loaded(verdict, ("falsified",))
    case = _loaded(critic, ("reason",))
    if isinstance(judged, str) or isinstance(case, str) or judged["falsified"] is not True:
        return None
    return str(case["reason"])


def _challenged(alignment: Path, loaded: dict[str, Any]) -> dict[str, Any]:
    reasons = [_falsified_by(alignment, number) for number in range(1, len(loaded["mismatches"]) + 1)]
    standing = [mismatch for mismatch, reason in zip(loaded["mismatches"], reasons) if reason is None]
    falsified = [{**mismatch, "falsified_by": reason} for mismatch, reason in zip(loaded["mismatches"], reasons) if reason is not None]
    return {**loaded, "mismatches": standing + falsified}


def _mismatch(mismatch: dict[str, Any]) -> str:
    line = f"**{mismatch['lower'].capitalize()} vs {mismatch['higher'].capitalize()}** ({mismatch['kind'].replace('-', ' ')}): {mismatch['text']} [{', '.join(mismatch['claims'])}]"
    return f"~~{line}~~ {mismatch['falsified_by']}" if "falsified_by" in mismatch else line


def _alignment(witnesses: dict[str, dict[str, Any] | str], alignment: dict[str, Any] | str) -> str:
    rungs = [f"**{name.capitalize()}**: {_said(name, loaded)}" for name, loaded in witnesses.items() if isinstance(loaded, str)]
    if isinstance(alignment, str):
        rungs.append(f"**Alignment**: Alignment failed: {alignment}")
    else:
        rungs.extend(_mismatch(mismatch) for mismatch in alignment["mismatches"])
    if not rungs:
        return "Everything matches."
    return "\n".join(f"{number}. {rung}" for number, rung in enumerate(rungs, start=1))
