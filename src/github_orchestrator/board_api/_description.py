import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime

from github_orchestrator.board_api.interface import Shelf, ShelfKey

DESCRIPTION = "description"
_KEPT = ShelfKey("kept")


def digest(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


@dataclass(frozen=True)
class DescriptionRecord:
    checked: str | None = None
    saved_title: str | None = None
    saved_body: str | None = None
    saved_at: str | None = None

    def keep(self, shelf: Shelf) -> None:
        shelf.save(DESCRIPTION, _KEPT, json.dumps(asdict(self)).encode())

    @staticmethod
    def kept(shelf: Shelf) -> "DescriptionRecord":
        document = shelf.list(DESCRIPTION).get(_KEPT)
        if document is None:
            return DescriptionRecord()
        try:
            fields = json.loads(document)
            return DescriptionRecord(**{name: value for name, value in fields.items()
                                        if isinstance(value, str)})
        except (ValueError, TypeError, AttributeError, RecursionError):
            return DescriptionRecord()


@dataclass(frozen=True)
class ServedDescription:
    title: str | None
    body: str
    checked: bool
    saved_at: str | None


def _before(polled_at: str | None, saved_at: str) -> bool:
    return polled_at is None or datetime.fromisoformat(polled_at) < datetime.fromisoformat(saved_at)


def served(record: DescriptionRecord, title: str | None, body: str,
           polled_at: str | None) -> ServedDescription:
    if (record.saved_at is not None and record.saved_body is not None
            and _before(polled_at, record.saved_at)):
        title, body = record.saved_title, record.saved_body
    return ServedDescription(title, body, record.checked == digest(body), record.saved_at)
