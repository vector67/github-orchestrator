import shutil
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROMPT = "Your inputs are the files in your working directory. Follow your instructions and write output.json there."
TIMEOUT_SECONDS = 600

Launch = Callable[[str, Path], bool]


def _tools(agent: Path) -> list[str]:
    frontmatter = agent.read_text().split("---")[1]
    line = next(line for line in frontmatter.splitlines() if line.startswith("tools:"))
    return [tool.strip() for tool in line.removeprefix("tools:").split(",")]


def command(witness: str, plugin_root: Path) -> list[str]:
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
        *(["--allowedTools", *mcp_tools] if mcp_tools else []),
    ]


def launcher(plugin_root: Path) -> Launch:
    def launch(witness: str, folder: Path) -> bool:
        result = subprocess.run(command(witness, plugin_root), input=PROMPT, cwd=folder, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
        (folder.parent / f"{witness}.log").write_text(result.stdout + result.stderr)
        return result.returncode == 0

    return launch


def run_witnesses(manifest: dict[str, Path], launch: Launch) -> dict[str, str]:
    witnesses = [name for name in manifest if name != "alignment"]
    failures: dict[str, str] = {}

    def attempt(witness: str) -> None:
        try:
            if not launch(witness, manifest[witness]):
                failures[witness] = "exited with an error"
        except Exception as error:
            failures[witness] = type(error).__name__

    with ThreadPoolExecutor(max_workers=len(witnesses)) as pool:
        list(pool.map(attempt, witnesses))
    for witness in witnesses:
        output = manifest[witness] / "output.json"
        if output.exists():
            shutil.copy(output, manifest["alignment"] / f"{witness}.json")
    attempt("alignment")
    return failures
