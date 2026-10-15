import difflib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from pr_summary.pull_request import PullRequest, Remark, cleaned, voices
from pr_summary.settings import Settings, kind_of, ticket_keys
from pr_summary.stripping import added_remarks, code_diff, stripped

LIMIT = 300_000

Contents = Callable[[str, str], bytes | None]


@dataclass(frozen=True)
class ChangedFile:
    path: str
    previous: str | None
    status: str
    changes: int


@dataclass(frozen=True)
class EarlierPr:
    number: int
    url: str
    title: str
    body: str
    author: str
    merged_at: str
    remarks: tuple[Remark, ...]


@dataclass(frozen=True)
class Side:
    before: str | None
    after: str | None


def _text(raw: bytes | None) -> str | None:
    if raw is None:
        return None
    if b"\x00" in raw:
        raise UnicodeDecodeError("utf-8", raw, 0, 1, "binary")
    return raw.decode()


def _sides(pr: PullRequest, changed: ChangedFile, contents: Contents) -> Side | None:
    try:
        before = None if changed.status == "added" else _text(contents(pr.base_sha, changed.previous or changed.path))
        after = None if changed.status == "removed" else _text(contents(pr.head_sha, changed.path))
    except UnicodeDecodeError:
        return None
    return Side(before, after)


def _write(folder: Path, name: str, lines: Iterable[str]) -> None:
    text = "".join(f"{line}\n" for line in lines)
    if text:
        (folder / name).write_text(text)


def _largest_first_until_within(entries: dict[str, str], budget: int) -> tuple[dict[str, str], list[str]]:
    kept = dict(entries)
    dropped = []
    while kept and sum(map(len, kept.values())) > budget:
        largest = max(kept, key=lambda path: len(kept[path]))
        dropped.append(largest)
        del kept[largest]
    return kept, dropped


def _code_folder(folder: Path, diffs: dict[str, str], wholes: dict[str, str], skipped: list[str], unstripped: list[str], limit: int) -> None:
    kept_diffs, dropped_diffs = _largest_first_until_within(diffs, limit)
    kept_wholes, dropped_wholes = _largest_first_until_within(wholes, limit - sum(map(len, kept_diffs.values())))
    truncated = [*dropped_diffs, *(f"files/{path}" for path in dropped_wholes)]
    _write(folder, "changes.diff", [diff.rstrip("\n") for diff in kept_diffs.values() if diff])
    for path, text in kept_wholes.items():
        whole = folder / "files" / path
        whole.parent.mkdir(parents=True, exist_ok=True)
        whole.write_text(text)
    _write(folder, "skipped.txt", skipped)
    _write(folder, "unstripped.txt", unstripped)
    _write(folder, "truncated.txt", truncated)


def _remark_lines(remarks: Iterable[Remark]) -> list[str]:
    return [f"## {remark.author} ({remark.url})\n{cleaned(remark.body)}\n" for remark in remarks]


def write_inputs(
    pr: PullRequest,
    files: list[ChangedFile],
    contents: Contents,
    earlier: list[EarlierPr],
    settings: Settings,
    ticket: str | None,
    out: Path,
    limit: int = LIMIT,
) -> dict[str, Path]:
    witnesses = ["claimed", "implementation", "tests", "why", "alignment", *(["requested"] if ticket else [])]
    manifest = {name: out / name for name in witnesses}
    for folder in manifest.values():
        folder.mkdir()

    diffs: dict[str, dict[str, str]] = {"production": {}, "tests": {}}
    wholes: dict[str, dict[str, str]] = {"production": {}, "tests": {}}
    skipped: dict[str, list[str]] = {"production": [], "tests": []}
    unstripped: dict[str, list[str]] = {"production": [], "tests": []}
    remarks_added: list[str] = []
    docs: list[str] = []
    for changed in files:
        kind = kind_of(changed.path, settings)
        if kind == "ignored":
            continue
        side = _sides(pr, changed, contents)
        if side is None:
            if kind != "docs":
                skipped[kind].append(changed.path)
            continue
        if kind == "docs":
            docs.append(_raw_diff(changed.path, side))
            continue
        diffs[kind][changed.path] = code_diff(changed.path, side.before, side.after)
        if side.after is not None:
            whole = stripped(side.after, changed.path)
            wholes[kind][changed.path] = side.after if whole is None else whole
        if stripped(side.after or side.before or "", changed.path) is None:
            unstripped[kind].append(changed.path)
        if side.after is not None:
            added = added_remarks(side.before, side.after, changed.path)
            if added:
                remarks_added.append(f"## {changed.path}\n" + "\n".join(added) + "\n")

    _code_folder(manifest["implementation"], diffs["production"], wholes["production"], skipped["production"], unstripped["production"], limit)
    _code_folder(manifest["tests"], diffs["tests"], wholes["tests"], skipped["tests"], unstripped["tests"], limit)

    by_authors, by_others = voices(pr.remarks, pr.authors, settings)
    claimed = manifest["claimed"]
    _write(claimed, "pull_request.md", [f"# {pr.title}\n", pr.body])
    _write(claimed, "comments.md", [f"## {remark.author} ({remark.url})\n{remark.body}\n" for remark in by_authors])
    _write(claimed, "commits.md", [f"- {message}" for message in pr.commit_messages])
    _write(claimed, "added_remarks.md", remarks_added)
    _write(claimed, "docs.diff", [diff.rstrip("\n") for diff in docs if diff])

    why = manifest["why"]
    _write(why, "ticket.txt", [ticket or "No ticket found."])
    _write(why, "authors.txt", sorted(pr.authors | pr.author_names))
    _write(why, "guidance.md", [settings.why_guidance] if settings.why_guidance else [])
    _write(why, "comments.md", _remark_lines(by_others))
    _write(why, "earlier_prs.md", [line for earlier_pr in earlier for line in _earlier_lines(earlier_pr, pr.authors, settings)])

    if ticket:
        _write(manifest["requested"], "ticket.txt", [ticket])
    return manifest


def _earlier_lines(earlier_pr: EarlierPr, authors: frozenset[str], settings: Settings) -> list[str]:
    _, others = voices(earlier_pr.remarks, authors, settings)
    written_by_others = earlier_pr.author not in authors
    if not others and not written_by_others:
        return []
    title = f" {earlier_pr.title}" if written_by_others else ""
    keys = ticket_keys(settings, f"{earlier_pr.title}\n{earlier_pr.body}")
    tickets = f", tickets {', '.join(keys)}" if keys else ""
    heading = f"# #{earlier_pr.number}{title} ({earlier_pr.url}): merged {earlier_pr.merged_at[:10]}{tickets}\n"
    body = [f"{earlier_pr.body}\n"] if written_by_others and earlier_pr.body else []
    return [heading, *body, *_remark_lines(others)]


def _raw_diff(path: str, side: Side) -> str:
    def lines(text: str | None) -> list[str]:
        return [line + "\n" for line in (text or "").splitlines()]

    return "".join(
        difflib.unified_diff(
            lines(side.before),
            lines(side.after),
            fromfile=f"a/{path}" if side.before is not None else "/dev/null",
            tofile=f"b/{path}" if side.after is not None else "/dev/null",
        )
    )
