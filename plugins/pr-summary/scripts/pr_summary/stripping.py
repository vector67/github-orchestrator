import difflib
import re
from collections.abc import Iterator

from tree_sitter import Node
from tree_sitter_language_pack import detect_language_from_path, get_parser

DOCSTRING_HOMES = {"module", "block"}
DOCSTRING_OWNERS = {"function_definition", "class_definition"}
UNSTRIPPABLE = {"vue", "svelte", "html", "astro", "vimdoc", "markdown"}
HUNK = re.compile(r"^@@ .* @@", re.MULTILINE)


def _remarks(root: Node, language: str) -> Iterator[Node]:
    stack = [root]
    while stack:
        node = stack.pop()
        if "comment" in node.type:
            yield node
            continue
        if language == "python" and _is_docstring(node):
            yield node
            continue
        stack.extend(reversed(node.children))


def _is_docstring(node: Node) -> bool:
    bare_string = node.type == "string"
    wrapped_string = node.type == "expression_statement" and [child.type for child in node.named_children] == ["string"]
    if not (bare_string or wrapped_string):
        return False
    home = node.parent
    if home is None or home.type not in DOCSTRING_HOMES:
        return False
    if home.type == "block" and (home.parent is None or home.parent.type not in DOCSTRING_OWNERS):
        return False
    statements = [child for child in home.named_children if "comment" not in child.type]
    return statements[0] == node


def _parsed(source: str, path: str) -> tuple[bytes, list[Node]] | None:
    language = detect_language_from_path(path)
    if language is None or language in UNSTRIPPABLE:
        return None
    data = source.encode()
    tree = get_parser(language).parse(data)
    return data, list(_remarks(tree.root_node, language))


def stripped(source: str, path: str) -> str | None:
    parsed = _parsed(source, path)
    if parsed is None:
        return None
    data, remarks = parsed
    blanked = bytearray(data)
    for remark in remarks:
        for index in range(remark.start_byte, remark.end_byte):
            if blanked[index] != ord("\n"):
                blanked[index] = ord(" ")
    return "\n".join(line.rstrip() for line in blanked.decode(errors="replace").split("\n"))


def _added_rows(base: str | None, head: str) -> set[int]:
    matcher = difflib.SequenceMatcher(a=(base or "").splitlines(), b=head.splitlines(), autojunk=False)
    return {row for tag, _, _, start, end in matcher.get_opcodes() if tag in ("insert", "replace") for row in range(start, end)}


def added_remarks(base: str | None, head: str, path: str) -> list[str]:
    parsed = _parsed(head, path)
    if parsed is None:
        return []
    data, remarks = parsed
    added_rows = _added_rows(base, head)
    added = []
    for remark in remarks:
        text = data[remark.start_byte : remark.end_byte].decode(errors="replace")
        rows = range(remark.start_point.row, remark.end_point.row + 1)
        if all(row in added_rows for row in rows):
            added.append(text.strip())
            continue
        lines = [line.strip() for row, line in zip(rows, text.split("\n"), strict=True) if row in added_rows and line.strip()]
        if lines:
            added.append("\n".join(lines))
    return added


def code_diff(path: str, before: str | None, after: str | None) -> str:
    def lines(source: str | None) -> list[str]:
        if source is None:
            return []
        text = stripped(source, path)
        return [line + "\n" for line in (source if text is None else text).splitlines()]

    diff = "".join(
        difflib.unified_diff(
            lines(before),
            lines(after),
            fromfile=f"a/{path}" if before is not None else "/dev/null",
            tofile=f"b/{path}" if after is not None else "/dev/null",
        )
    )
    return _without_blank_hunks(diff)


def _without_blank_hunks(diff: str) -> str:
    starts = [match.start() for match in HUNK.finditer(diff)]
    if not starts:
        return ""
    header = diff[: starts[0]]
    hunks = [diff[start:end] for start, end in zip(starts, [*starts[1:], len(diff)], strict=True)]
    kept = [hunk for hunk in hunks if any(line[:1] in "+-" and line[1:].strip() for line in hunk.splitlines()[1:])]
    return header + "".join(kept) if kept else ""
