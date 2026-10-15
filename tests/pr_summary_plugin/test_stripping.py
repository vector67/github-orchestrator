from pr_summary.stripping import added_remarks, code_diff, stripped

PYTHON = '''"""Exports rows."""
import csv


class Rows:
    """Rows of an export."""

    def keep(self, row):
        """Say whether a row is kept."""
        return any(row)  # empty rows go


message = "# not a comment"
'''


def test_python_loses_comments_and_docstrings_but_keeps_its_lines() -> None:
    result = stripped(PYTHON, "src/rows.py")

    assert result is not None
    assert "Exports rows" not in result
    assert "Rows of an export" not in result
    assert "Say whether" not in result
    assert "empty rows go" not in result
    assert 'message = "# not a comment"' in result
    assert "return any(row)" in result
    assert len(result.splitlines()) == len(PYTHON.splitlines())
    assert result.splitlines()[9] == "        return any(row)"


def test_typescript_loses_line_block_and_doc_comments() -> None:
    source = "/** Rows. */\nexport function keep(row: string[]) {\n  // empty rows go\n  return row.length > 0; /* inline */\n}\nconst url = 'http://x';\n"

    result = stripped(source, "app/rows.ts")

    assert result is not None
    assert "Rows." not in result and "empty rows go" not in result and "inline" not in result
    assert "return row.length > 0;" in result
    assert "const url = 'http://x';" in result


def test_markup_that_embeds_code_counts_as_not_strippable() -> None:
    for path in ["app/mask.vue", "app/Card.svelte", "site/index.html", "notes/CHANGES.txt"]:
        assert stripped("<script>\n// note\nlet x = 1\n</script>\n", path) is None, path


def test_a_file_in_an_unknown_language_is_not_stripped() -> None:
    assert stripped("-- a comment\nselect 1;\n", "db/query.unknownext") is None


def test_added_remarks_are_the_comments_and_docstrings_the_head_adds() -> None:
    base = 'def keep(row):\n    # old note\n    return row\n'
    head = 'def keep(row):\n    """Keep non-empty rows."""\n    # old note\n    # drop empties, per the ticket\n    return any(row)\n'

    assert added_remarks(base, head, "src/rows.py") == ['"""Keep non-empty rows."""', "# drop empties, per the ticket"]


def test_an_edited_docstring_contributes_only_its_added_lines() -> None:
    base = 'def keep(row):\n    """Keep rows.\n\n    Sorted top-down.\n    """\n    return row\n'
    head = 'def keep(row):\n    """Keep rows.\n\n    Sorted top-down.\n    Empty rows are dropped.\n    """\n    return any(row)\n'

    assert added_remarks(base, head, "src/rows.py") == ["Empty rows are dropped."]


def test_added_remarks_of_a_new_file_are_all_its_remarks() -> None:
    assert added_remarks(None, "x = 1  # set x\n", "src/x.py") == ["# set x"]


def test_the_code_diff_shows_code_changes_without_remark_noise() -> None:
    base = "def keep(row):\n    return row\n"
    head = "def keep(row):\n    # drop empties\n    return any(row)\n"

    diff = code_diff("src/rows.py", base, head)

    assert "drop empties" not in diff
    assert "-    return row" in diff
    assert "+    return any(row)" in diff
    assert diff.startswith("--- a/src/rows.py\n+++ b/src/rows.py\n")


def test_a_change_only_to_remarks_leaves_no_code_diff() -> None:
    assert code_diff("src/rows.py", "x = 1\n", "# set x\nx = 1  # really\n") == ""


def test_a_deleted_file_diffs_against_nothing() -> None:
    diff = code_diff("src/gone.py", "x = 1\n", None)

    assert "--- a/src/gone.py\n+++ /dev/null\n" in diff
    assert "-x = 1" in diff


def test_an_unknown_language_diffs_unstripped() -> None:
    diff = code_diff("db/q.unknownext", "select 1;\n", "-- note\nselect 2;\n")

    assert "+-- note" in diff
