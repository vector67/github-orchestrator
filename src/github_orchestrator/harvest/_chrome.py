import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

Run = Callable[..., subprocess.CompletedProcess[Any]]


def handed_to_chrome(folder: Path, run: Run) -> None:
    run(["open", "-a", "Google Chrome", "chrome://extensions/"], check=False)
    run(["open", "-R", str(folder)], check=False)
    run(["pbcopy"], input=str(folder), text=True, check=False)
