from typing import Any

from pr_summary.earlier import chosen, earlier_from, most_changed
from pr_summary.inputs import ChangedFile
from pr_summary.settings import Settings


def test_most_changed_are_the_production_files_with_the_most_changed_lines() -> None:
    files = [
        ChangedFile("src/a.py", None, "modified", 5),
        ChangedFile("tests/test_a.py", None, "modified", 90),
        ChangedFile("src/b.py", None, "modified", 40),
        ChangedFile("README.md", None, "modified", 70),
        ChangedFile("src/c.py", None, "added", 12),
        ChangedFile("src/d.py", None, "modified", 30),
    ]

    assert most_changed(files, Settings()) == ["src/b.py", "src/d.py", "src/c.py"]


def test_chosen_keeps_order_drops_this_pr_and_repeats_and_stops_at_five() -> None:
    assert chosen([4, 7, 4, 3, 9, 1, 2, 8], this=7) == [4, 3, 9, 1, 2]


def pr_node(merged_at: str | None) -> dict[str, Any]:
    return {
        "number": 3,
        "url": "https://github.com/acme/shop/pull/3",
        "title": "Rewrite the exporter",
        "body": None,
        "mergedAt": merged_at,
        "author": {"login": "monalisa", "__typename": "User"},
        "comments": {"nodes": [{"author": {"login": "hubot", "__typename": "User"}, "body": "Exports time out.", "url": "c1"}]},
        "reviews": {"nodes": []},
        "reviewThreads": {"nodes": [{"comments": {"nodes": [{"author": None, "body": "Old note.", "url": "c2"}]}}]},
    }


def test_an_earlier_pr_merged_before_this_one_opened_is_kept() -> None:
    earlier = earlier_from(pr_node("2026-09-20T10:00:00Z"), opened="2026-10-01T09:00:00Z")

    assert earlier is not None
    assert (earlier.number, earlier.title, earlier.body, earlier.author) == (3, "Rewrite the exporter", "", "monalisa")
    assert [remark.body for remark in earlier.remarks] == ["Exports time out.", "Old note."]


def test_a_pr_merged_after_this_one_opened_or_never_merged_is_dropped() -> None:
    assert earlier_from(pr_node("2026-10-02T10:00:00Z"), opened="2026-10-01T09:00:00Z") is None
    assert earlier_from(pr_node(None), opened="2026-10-01T09:00:00Z") is None
