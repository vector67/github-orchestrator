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


def listed(pr: Pr, mention: Mention, *, url: str, on_board: bool,
           building: bool) -> ListedMention:
    return ListedMention(pr=pr, thread=mention.thread, comment_id=mention.comment_id,
                         kind=mention.kind, author=mention.author, at=mention.at,
                         body=mention.body, url=url, on_board=on_board, building=building)


def started_before(path: Path) -> dict[str, str] | None:
    try:
        started: dict[str, str] = json.loads(path.read_text())["started"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return started if isinstance(started, dict) else None


def building_since(path: Path) -> dict[str, str]:
    try:
        building: dict[str, str] = json.loads(path.read_text())["building_since"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    return building if isinstance(building, dict) else {}


def write_listing(path: Path, searched_at: datetime, started: Mapping[str, str],
                  mentions: Sequence[ListedMention], building: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writing = path.with_name(f"{path.name}.writing")
    writing.write_text(json.dumps({"searched_at": searched_at.isoformat(),
                                   "started": dict(started),
                                   "building_since": dict(building),
                                   "mentions": [_entry(mention) for mention in mentions]}))
    os.replace(writing, path)


class ListingFile:
    def __init__(self, path: Path) -> None:
        self._path = path

    def listed(self) -> MentionsListing:
        try:
            document = json.loads(self._path.read_text())
        except FileNotFoundError:
            return NO_MENTIONS_LISTED
        except (OSError, ValueError) as damaged:
            log.warning("%s will not read, so no mentions are listed: %s", self._path, damaged)
            return NO_MENTIONS_LISTED
        try:
            return MentionsListing(searched_at=document["searched_at"], mentions=tuple(
                _listed_mention(entry) for entry in document["mentions"]))
        except (KeyError, TypeError, ValueError) as damaged:
            log.warning("%s is damaged, so no mentions are listed: %r", self._path, damaged)
            return NO_MENTIONS_LISTED


def _entry(mention: ListedMention) -> dict[str, Any]:
    return {"repo": str(mention.pr.repo), "number": mention.pr.number,
            "thread": mention.thread, "comment_id": mention.comment_id, "kind": mention.kind,
            "author": mention.author, "at": mention.at, "body": mention.body,
            "url": mention.url, "on_board": mention.on_board, "building": mention.building}


def _listed_mention(entry: Mapping[str, Any]) -> ListedMention:
    if type(entry["number"]) is not int:
        raise TypeError(f"the PR number {entry['number']!r} is not a number")
    return ListedMention(pr=Pr(Repo.parse(entry["repo"]), entry["number"]),
                         thread=entry["thread"], comment_id=entry["comment_id"],
                         kind=entry["kind"], author=entry["author"], at=entry["at"],
                         body=entry["body"], url=entry["url"], on_board=entry["on_board"],
                         building=entry["building"])
