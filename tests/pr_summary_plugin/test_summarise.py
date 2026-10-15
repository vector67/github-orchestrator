import tempfile
from pathlib import Path

import pytest
import summarise
from pr_summary.github import Gh, GhFailed


def failing_target(gh: Gh, given: str) -> tuple[str, str, int]:
    raise GhFailed("no such pull request")


def test_without_a_work_dir_a_failed_lookup_leaves_no_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(summarise, "target", failing_target)
    monkeypatch.setattr("sys.argv", ["summarise.py", "7"])

    with pytest.raises(GhFailed):
        summarise.main()

    assert list(tmp_path.iterdir()) == []


def test_a_work_dir_that_holds_anything_is_refused_before_the_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "leftover").write_text("")
    monkeypatch.setattr(summarise, "target", failing_target)
    monkeypatch.setattr("sys.argv", ["summarise.py", "7", "--work-dir", str(tmp_path)])

    with pytest.raises(summarise.WorkDirNotEmpty):
        summarise.main()
