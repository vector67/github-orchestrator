from typing import Any

from pr_summary.inputs import ChangedFile, EarlierPr
from pr_summary.pull_request import remarks_from
from pr_summary.settings import Settings, kind_of

EARLIER_LIMIT = 5
MOST_CHANGED = 3


def most_changed(files: list[ChangedFile], settings: Settings) -> list[str]:
    production = [changed for changed in files if kind_of(changed.path, settings) == "production"]
    return [changed.path for changed in sorted(production, key=lambda changed: -changed.changes)[:MOST_CHANGED]]


def chosen(numbers: list[int], this: int) -> list[int]:
    return [number for number in dict.fromkeys(numbers) if number != this][:EARLIER_LIMIT]


def earlier_from(pr: dict[str, Any], opened: str) -> EarlierPr | None:
    if pr["mergedAt"] is None or pr["mergedAt"] >= opened:
        return None
    return EarlierPr(
        number=pr["number"],
        url=pr["url"],
        title=pr["title"],
        body=pr["body"] or "",
        author=(pr["author"] or {"login": "ghost"})["login"],
        remarks=remarks_from(pr),
    )
