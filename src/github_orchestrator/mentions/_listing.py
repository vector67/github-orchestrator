import json
import logging
import os
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from github_orchestrator.board_api.interface import (
    NO_MENTIONS_LISTED,
    ListedMention,
    MentionsListing,
)
from github_orchestrator.domain import Mention, Pr, Repo

log = logging.getLogger(__name__)


def listed(pr: Pr, mention: Mention, *, url: str, card: bool) -> dict[str, Any]:
    return {"repo": str(pr.repo), "number": pr.number, "thread": mention.thread,
            "comment_id": mention.comment_id, "kind": mention.kind, "author": mention.author,
            "at": mention.at, "body": mention.body, "url": url, "card": card}


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


class ListingFile:
    def __init__(self, path: Path) -> None:
        self._path = path

    def listed(self) -> MentionsListing:
        try:
            document = json.loads(self._path.read_text())
        except FileNotFoundError:
            return NO_MENTIONS_LISTED
        return MentionsListing(searched_at=document["searched_at"], mentions=tuple(
            ListedMention(pr=Pr(Repo.parse(entry["repo"]), entry["number"]),
                          thread=entry["thread"], comment_id=entry["comment_id"],
                          kind=entry["kind"], author=entry["author"], at=entry["at"],
                          body=entry["body"], url=entry["url"], card=entry["card"])
            for entry in document["mentions"]))
