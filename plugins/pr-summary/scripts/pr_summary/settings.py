import re
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import PurePosixPath
from typing import Any, Literal

Kind = Literal["ignored", "docs", "tests", "production"]


@dataclass(frozen=True)
class Settings:
    ticket_pattern: str = "[A-Z][A-Z0-9]+-[0-9]+"
    ticket_sources: tuple[str, ...] = ("title", "branch")
    ticket_projects: tuple[str, ...] = ()
    tests: tuple[str, ...] = ("tests/**", "test/**", "**/test_*.py", "**/*_test.py", "**/*.test.*", "**/*.spec.*", "**/__tests__/**")
    docs: tuple[str, ...] = ("**/*.md", "**/*.rst", "**/*.adoc", "**/*.ipynb", "docs/**", "**/docs/**", "**/README*", "**/CHANGELOG*")
    ignore: tuple[str, ...] = ("**/*.lock", "**/package-lock.json", "**/pnpm-lock.yaml", "**/yarn.lock")
    bots: tuple[str, ...] = ()
    why_guidance: str = ""


def settings_from(toml_text: str | None) -> Settings:
    if toml_text is None:
        return Settings()
    table = tomllib.loads(toml_text).get("pr_summary", {})
    known = {field.name for field in fields(Settings)}
    given: dict[str, Any] = {key: tuple(value) if isinstance(value, list) else value for key, value in table.items() if key in known}
    return replace(Settings(), **given)


def ticket_keys(settings: Settings, text: str) -> list[str]:
    keys = (found.group(0) for found in re.finditer(settings.ticket_pattern, text))
    return list(dict.fromkeys(key for key in keys if not settings.ticket_projects or key.split("-")[0] in settings.ticket_projects))


def ticket_key(settings: Settings, title: str, branch: str) -> str | None:
    texts = {"title": title, "branch": branch}
    for source in settings.ticket_sources:
        keys = ticket_keys(settings, texts.get(source, ""))
        if keys:
            return keys[0]
    return None


def kind_of(path: str, settings: Settings) -> Kind:
    def matches(globs: tuple[str, ...]) -> bool:
        return any(PurePosixPath(path).full_match(glob) for glob in globs)

    if matches(settings.ignore):
        return "ignored"
    if matches(settings.docs):
        return "docs"
    if matches(settings.tests):
        return "tests"
    return "production"

