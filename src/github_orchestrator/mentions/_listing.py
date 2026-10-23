import json
import os
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from github_orchestrator.domain import Mention, Pr


def listed(pr: Pr, mention: Mention) -> dict[str, Any]:
    return {"repo": str(pr.repo), "number": pr.number, "thread": mention.thread,
            "comment_id": mention.comment_id, "kind": mention.kind, "author": mention.author,
            "at": mention.at, "body": mention.body}


def started_before(path: Path) -> dict[str, str] | None:
    try:
        started: dict[str, str] = json.loads(path.read_text())["started"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return started


def write_listing(path: Path, searched_at: datetime, started: Mapping[str, str],
                  mentions: Sequence[Mapping[str, Any]]) -> None:
    writing = path.with_name(f"{path.name}.writing")
    writing.write_text(json.dumps({"searched_at": searched_at.isoformat(),
                                   "started": dict(started), "mentions": list(mentions)}))
    os.replace(writing, path)
