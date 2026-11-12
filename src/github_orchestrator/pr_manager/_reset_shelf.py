import json
from dataclasses import asdict

from github_orchestrator.board_api.interface import (
    RESET_STATE,
    RESET_TO_ORIGIN,
    ResetRefusal,
    ResetRefusalCode,
    ResetToOrigin,
    Shelf,
)


def _text(field: object) -> bool:
    return field is None or (isinstance(field, str) and bool(field))


def _refusal_of(field: object) -> ResetRefusal:
    if not isinstance(field, dict):
        raise ValueError(field)
    code, detail = field.get("code"), field.get("detail")
    if not isinstance(code, str) or not _text(detail):
        raise ValueError(field)
    return ResetRefusal(ResetRefusalCode(code), detail)


def keep_reset(shelf: Shelf, reset: ResetToOrigin) -> None:
    shelf.save(RESET_TO_ORIGIN, RESET_STATE, json.dumps(asdict(reset)).encode())


def kept_reset(shelf: Shelf) -> ResetToOrigin | None:
    document = shelf.list(RESET_TO_ORIGIN).get(RESET_STATE)
    if document is None:
        return None
    try:
        fields = json.loads(document)
        queued_at, ran_at = fields.get("queued_at"), fields.get("ran_at")
        refused = fields.get("refused")
        if not (_text(queued_at) and _text(ran_at)):
            return None
        return ResetToOrigin(queued_at, ran_at,
                             None if refused is None else _refusal_of(refused))
    except (ValueError, TypeError, AttributeError, RecursionError):
        return None
