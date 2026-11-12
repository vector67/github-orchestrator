import os
import stat

import pytest

from github_orchestrator.atomic_write import write_atomically


def test_a_write_lands_whole_in_a_folder_not_made_yet(tmp_path):
    target = tmp_path / "new" / "listing.json"

    write_atomically(target, b"{}")

    assert target.read_bytes() == b"{}"
    assert os.listdir(target.parent) == ["listing.json"]


def test_the_content_is_on_disk_before_it_replaces_the_old_file(tmp_path, monkeypatch):
    target = tmp_path / "listing.json"
    target.write_bytes(b"old")
    synced = []
    real_fsync = os.fsync

    def seen_at_fsync(fd):
        synced.append((os.pread(fd, 100, 0), target.read_bytes()))
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", seen_at_fsync)

    write_atomically(target, b"new")

    assert synced == [(b"new", b"old")]
    assert target.read_bytes() == b"new"


def test_each_write_goes_through_a_temp_file_of_its_own(tmp_path, monkeypatch):
    target = tmp_path / "listing.json"
    staged = []
    real_replace = os.replace

    def noted(source, destination):
        staged.append(os.path.basename(source))
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", noted)

    write_atomically(target, b"one")
    write_atomically(target, b"two")

    assert len(set(staged)) == 2
    assert all(name.startswith("listing.json.") for name in staged)


def test_a_write_that_fails_leaves_the_old_file_and_no_temp_file(tmp_path, monkeypatch):
    target = tmp_path / "listing.json"
    target.write_bytes(b"old")

    def disk_full(fd):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "fsync", disk_full)

    with pytest.raises(OSError):
        write_atomically(target, b"new")

    assert target.read_bytes() == b"old"
    assert os.listdir(tmp_path) == ["listing.json"]


def test_a_write_keeps_the_mode_of_the_file_it_replaces(tmp_path):
    target = tmp_path / "config.toml"
    target.write_bytes(b"old")
    target.chmod(0o640)

    write_atomically(target, b"new")

    assert stat.S_IMODE(target.stat().st_mode) == 0o640
