import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pr_summary.witnesses import challenge_folders

Check = Callable[[Any], bool]


def _known(value: Any) -> bool:
    return value is not None


def _text(value: Any) -> bool:
    return isinstance(value, str)


def _number(value: Any) -> bool:
    return isinstance(value, int)


def _texts(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _concept_shaped(value: Any) -> bool:
    return isinstance(value, dict) and _text(value.get("name")) and _text(value.get("explanation")) and _subconcepts(value.get("concepts"))


def _subconcepts(value: Any) -> bool:
    return value is None or (isinstance(value, list) and all(_concept_shaped(child) for child in value))


WITNESS_FIELDS: dict[str, Check] = {"witness": _known, "display": _text, "claims": _known, "gaps": _texts}
MISMATCH_FIELDS: dict[str, Check] = {"lower": _text, "higher": _text, "kind": _text, "text": _text, "claims": _texts}
CONCEPT_FIELDS: dict[str, Check] = {"name": _text, "explanation": _text, "concepts": _subconcepts}
ORDER = ("requested", "claimed", "implementation", "tests", "why")


def _loaded(folder: Path | None, fields: dict[str, Check], top: str | None = None) -> dict[str, Any] | str:
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
        found = item if isinstance(item, dict) else {}
        for field, check in fields.items():
            if not check(found.get(field)):
                return f"output.json has a malformed {field}." if field in found else f"output.json has no {field}."
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
        f"## Before you review\n{_primer(_loaded(manifest.get('primer'), CONCEPT_FIELDS, top='concepts'))}",
        f"## Requested\n{_said('requested', witnesses['requested'])}",
        f"## Claimed\n{_said('claimed', witnesses['claimed'])}",
        f"## Intent\n**Implementation:** {_said('implementation', witnesses['implementation'])}\n\n**Tests:** {_said('tests', witnesses['tests'])}",
        f"## Why\n{_said('why', witnesses['why'])}",
        f"## Alignment\n{_alignment(witnesses, alignment)}",
    ]
    return "\n\n".join(sections) + "\n"


def _primer(loaded: dict[str, Any] | str) -> str:
    if isinstance(loaded, str):
        return f"Primer failed: {loaded}"
    return "".join(_concept(concept) for concept in loaded["concepts"]).rstrip("\n")


def _concept(concept: dict[str, Any]) -> str:
    inner = "".join(_concept(child) for child in concept.get("concepts", []))
    return f"<details>\n<summary>{concept['name']}</summary>\n\n{concept['explanation']}\n\n{inner}</details>\n\n"


def _falsified(alignment: Path) -> dict[int, str]:
    critic, verdict = challenge_folders(alignment)
    judged = _loaded(verdict, {"mismatch": _number, "falsified": _known}, top="verdicts")
    cases = _loaded(critic, {"mismatch": _number, "reason": _known}, top="challenges")
    if isinstance(judged, str) or isinstance(cases, str):
        return {}
    reasons = {case["mismatch"]: str(case["reason"]) for case in cases["challenges"]}
    return {ruling["mismatch"]: reasons[ruling["mismatch"]] for ruling in judged["verdicts"] if ruling["falsified"] is True and ruling["mismatch"] in reasons}


def _challenged(alignment: Path, loaded: dict[str, Any]) -> dict[str, Any]:
    falsified_by = _falsified(alignment)
    reasons = [falsified_by.get(number) for number in range(1, len(loaded["mismatches"]) + 1)]
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
