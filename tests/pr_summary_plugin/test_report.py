import json
from pathlib import Path
from typing import Any

from pr_summary.report import report

WITNESSES = {"requested": "R", "claimed": "C", "implementation": "I", "tests": "T", "why": "W"}


def output(witness: str, display: str, gaps: list[str] | None = None) -> dict[str, Any]:
    prefix = WITNESSES[witness]
    return {"witness": witness, "display": display, "claims": [{"id": f"{prefix}1", "text": display, "evidence": ["x"]}], "gaps": gaps or []}


def folders(tmp_path: Path, outputs: dict[str, Any], mismatches: list[dict[str, Any]] | None) -> dict[str, Path]:
    manifest = {}
    for witness in [*WITNESSES, "alignment"]:
        folder = tmp_path / witness
        folder.mkdir()
        manifest[witness] = folder
    for witness, content in outputs.items():
        (tmp_path / witness / "output.json").write_text(content if isinstance(content, str) else json.dumps(content))
    if mismatches is not None:
        (tmp_path / "alignment" / "output.json").write_text(json.dumps({"mismatches": mismatches}))
    return manifest


ALL = {
    "requested": output("requested", "Hide the export button while exports are off."),
    "claimed": output("claimed", "Hides the button behind the exports flag."),
    "implementation": output("implementation", "Returns no export button when the exports flag is off."),
    "tests": output("tests", "Pins that the toolbar has no export button with exports off."),
    "why": output("why", "Exports time out on large shops until the rewrite lands.", gaps=["No Confluence page found."]),
}


def test_sections_print_in_order(tmp_path: Path) -> None:
    text = report(folders(tmp_path, ALL, []))

    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == ["## Requested", "## Claimed", "## Intent", "## Why", "## Alignment"]
    assert "**Implementation:** Returns no export button" in text
    assert "**Tests:** Pins that the toolbar" in text
    assert "No Confluence page found." in text


def test_everything_matches_only_when_all_witnesses_spoke_and_no_mismatch(tmp_path: Path) -> None:
    assert "Everything matches." in report(folders(tmp_path, ALL, []))


def test_mismatches_are_listed_with_both_witnesses_and_their_claims(tmp_path: Path) -> None:
    mismatch = {"lower": "implementation", "higher": "requested", "kind": "unrequested-refactor", "text": "Also renames the export service.", "claims": ["I1", "R1"]}

    text = report(folders(tmp_path, ALL, [mismatch]))

    assert "Everything matches." not in text
    assert "1. **Implementation vs Requested** (unrequested refactor): Also renames the export service. [I1, R1]" in text


def test_no_ticket_is_the_first_rung_and_never_matches(tmp_path: Path) -> None:
    outputs = {name: value for name, value in ALL.items() if name != "requested"}
    manifest = folders(tmp_path, outputs, [])
    del manifest["requested"]

    text = report(manifest)

    assert "## Requested\nNo ticket found." in text
    assert "Everything matches." not in text
    assert "1. **Requested**: No ticket found." in text


def test_a_malformed_output_is_that_section_failing(tmp_path: Path) -> None:
    text = report(folders(tmp_path, {**ALL, "why": "{not json"}, []))

    assert "## Why\nWhy failed: output.json is not valid JSON." in text
    assert "1. **Why**: Why failed: output.json is not valid JSON." in text


def test_an_output_missing_a_field_fails(tmp_path: Path) -> None:
    broken = {key: value for key, value in ALL["tests"].items() if key != "display"}

    text = report(folders(tmp_path, {**ALL, "tests": broken}, []))

    assert "Tests failed: output.json has no display." in text


def test_a_missing_alignment_says_so(tmp_path: Path) -> None:
    text = report(folders(tmp_path, ALL, None))

    assert "Alignment failed: no output.json." in text
    assert "Everything matches." not in text


def test_a_witness_whose_tools_stayed_unavailable_fails_naming_why(tmp_path: Path) -> None:
    unavailable = {"witness": "requested", "unavailable": "the Atlassian tools never connected"}

    text = report(folders(tmp_path, {**ALL, "requested": unavailable}, []))

    assert "## Requested\nRequested failed: its tools stayed unavailable: the Atlassian tools never connected" in text


def judged(tmp_path: Path, number: int, critic_reason: str, falsified: bool) -> None:
    (tmp_path / f"critic-{number}").mkdir()
    (tmp_path / f"critic-{number}" / "output.json").write_text(json.dumps({"falsified": True, "reason": critic_reason, "evidence": []}))
    (tmp_path / f"verdict-{number}").mkdir()
    (tmp_path / f"verdict-{number}" / "output.json").write_text(json.dumps({"falsified": falsified, "reason": "The judge's view."}))


def test_falsified_mismatches_follow_the_standing_ones_crossed_out_with_the_critics_reason(tmp_path: Path) -> None:
    renamed = {"lower": "implementation", "higher": "requested", "kind": "unrequested-refactor", "text": "Also renames the export service.", "claims": ["I1", "R1"]}
    untested = {"lower": "tests", "higher": "implementation", "kind": "untested", "text": "Nothing pins the hidden button.", "claims": ["I1"]}
    unsupported = {"lower": "claimed", "higher": "implementation", "kind": "unsupported", "text": "Claims a cache.", "claims": ["C1"]}
    manifest = folders(tmp_path, ALL, [renamed, untested, unsupported])
    judged(tmp_path, 1, "The rename is in requested's R1.", falsified=True)
    judged(tmp_path, 2, "T1 pins it.", falsified=False)

    text = report(manifest)

    assert (
        "1. **Tests vs Implementation** (untested): Nothing pins the hidden button. [I1]\n"
        "2. **Claimed vs Implementation** (unsupported): Claims a cache. [C1]\n"
        "3. ~~**Implementation vs Requested** (unrequested refactor): Also renames the export service. [I1, R1]~~ The rename is in requested's R1.\n"
    ) in text
