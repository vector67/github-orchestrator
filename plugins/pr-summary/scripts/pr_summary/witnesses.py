import json
import os
import shutil
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROMPT = "Your inputs are the files in your working directory. Follow your instructions and write output.json there."
TIMEOUT_SECONDS = 600
ATTEMPTS = 2
RETRY_WAIT_SECONDS = 30.0

Launch = Callable[[str, Path], bool]
Wait = Callable[[float], None]


def _tools(agent: Path) -> list[str]:
    frontmatter = agent.read_text().split("---")[1]
    line = next(line for line in frontmatter.splitlines() if line.startswith("tools:"))
    return [tool.strip() for tool in line.removeprefix("tools:").split(",")]


def command(witness: str, plugin_root: Path, mcp_config: Path | None) -> list[str]:
    mcp_tools = [tool for tool in _tools(plugin_root / "agents" / f"{witness}.md") if tool.startswith("mcp__")]
    return [
        "claude",
        "-p",
        "--restricted",
        "--plugin-dir",
        str(plugin_root),
        "--agent",
        f"pr-summary:{witness}",
        "--permission-mode",
        "acceptEdits",
        "--no-session-persistence",
        *(["--mcp-config", str(mcp_config), "--strict-mcp-config"] if mcp_config else []),
        *(["--allowedTools", *mcp_tools] if mcp_tools else []),
    ]


def launcher(plugin_root: Path, mcp_config: Path | None) -> Launch:
    def launch(witness: str, folder: Path) -> bool:
        result = subprocess.run(command(witness, plugin_root, mcp_config), input=PROMPT, cwd=folder, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
        (folder.parent / f"{folder.name}.log").write_text(result.stdout + result.stderr)
        return result.returncode == 0

    return launch


def _unavailable(folder: Path) -> str | None:
    try:
        content = json.loads((folder / "output.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return content.get("unavailable") if isinstance(content, dict) else None


def challenge_folders(alignment: Path) -> tuple[Path, Path]:
    return alignment.parent / "critic", alignment.parent / "verdict"


def _numbered_mismatches(alignment: Path) -> list[dict[str, object]]:
    try:
        content = json.loads((alignment / "output.json").read_text())
    except (OSError, json.JSONDecodeError):
        return []
    mismatches = content.get("mismatches") if isinstance(content, dict) else None
    if not isinstance(mismatches, list):
        return []
    return [{"number": number, **mismatch} for number, mismatch in enumerate(mismatches, start=1) if isinstance(mismatch, dict)]


def _evidence_into(folder: Path, manifest: dict[str, Path], mismatches: list[dict[str, object]]) -> None:
    folder.mkdir()
    (folder / "mismatches.json").write_text(json.dumps(mismatches, indent=2))
    shutil.copytree(manifest["alignment"], folder / "witnesses", ignore=shutil.ignore_patterns("output.json"))
    for code in ("implementation", "tests"):
        if code in manifest:
            shutil.copytree(manifest[code], folder / code, ignore=shutil.ignore_patterns("output.json"), copy_function=os.link)


def run_witnesses(manifest: dict[str, Path], launch: Launch, wait: Wait) -> dict[str, str]:
    witnesses = [name for name in manifest if name != "alignment"]
    failures: dict[str, str] = {}

    def attempt(agent: str, folder: Path) -> bool:
        for attempt_number in range(1, ATTEMPTS + 1):
            try:
                if not launch(agent, folder):
                    failures[folder.name] = "exited with an error"
                    return False
            except Exception as error:
                failures[folder.name] = type(error).__name__
                return False
            reason = _unavailable(folder)
            if reason is None:
                return True
            if attempt_number < ATTEMPTS:
                (folder / "output.json").unlink()
                wait(RETRY_WAIT_SECONDS)
        failures[folder.name] = f"its tools stayed unavailable: {reason}"
        return False

    with ThreadPoolExecutor(max_workers=len(witnesses)) as pool:
        list(pool.map(lambda witness: attempt(witness, manifest[witness]), witnesses))
    for witness in witnesses:
        output = manifest[witness] / "output.json"
        if output.exists() and witness not in failures:
            shutil.copy(output, manifest["alignment"] / f"{witness}.json")
    attempt("alignment", manifest["alignment"])
    mismatches = _numbered_mismatches(manifest["alignment"])
    if not mismatches:
        return failures
    critic, verdict = challenge_folders(manifest["alignment"])
    _evidence_into(critic, manifest, mismatches)
    if not attempt("critic", critic) or not (critic / "output.json").exists():
        return failures
    _evidence_into(verdict, manifest, mismatches)
    shutil.copy(critic / "output.json", verdict / "critic.json")
    attempt("verdict", verdict)
    return failures
