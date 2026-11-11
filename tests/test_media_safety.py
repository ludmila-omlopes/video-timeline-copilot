from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from helpers.backup import create_backup, list_backups, restore_backup
from helpers.inventory import file_fingerprint
from helpers.verify_media import apply_relinks, check_item, verify


def make_project(tmp_path: Path) -> tuple[Path, Path]:
    raw = tmp_path / "raw"
    raw.mkdir()
    clip = raw / "clip.mp4"
    clip.write_bytes(b"12345678")
    edit_dir = tmp_path / "edit"
    edit_dir.mkdir()
    index = {"root": str(tmp_path), "media": [{"path": str(clip), **file_fingerprint(clip)}], "images": []}
    (edit_dir / "media_index.json").write_text(json.dumps(index), encoding="utf-8")
    edl = {
        "version": 1,
        "project_name": "P",
        "fps": 30,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": [{"source": "A001", "source_start": 0, "source_end": 2, "record_start": 0}],
            }
        ],
    }
    (edit_dir / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    return clip, edit_dir


def test_check_item_distinguishes_ok_changed_missing_and_unverified(tmp_path: Path) -> None:
    clip, _ = make_project(tmp_path)
    fingerprint = file_fingerprint(clip)
    assert check_item({"path": str(clip), **fingerprint})["status"] == "ok"
    assert check_item({"path": str(clip)})["status"] == "unverified"
    assert check_item({"path": str(clip), "size": 3, "mtime": fingerprint["mtime"]})["status"] == "changed"
    # A copy keeps the bytes but not the timestamp; that is still the same media.
    assert check_item({"path": str(clip), "size": 8, "mtime": 1.0})["status"] == "ok"
    assert check_item({"path": str(tmp_path / "gone.mp4"), "size": 8})["status"] == "missing"


def test_verify_suggests_a_relink_for_a_moved_file_and_applies_it_on_request(tmp_path: Path) -> None:
    clip, edit_dir = make_project(tmp_path)
    moved = tmp_path / "raw" / "day1" / "clip.mp4"
    moved.parent.mkdir()
    clip.rename(moved)
    # A generated file with the same name inside edit/ must never be offered as the source.
    (edit_dir / "previews").mkdir()
    (edit_dir / "previews" / "clip.mp4").write_bytes(b"12345678")

    report = verify(edit_dir, edl_path=edit_dir / "edl.json")

    assert report["ok"] is False
    assert report["counts"] == {"ok": 0, "missing": 1, "changed": 0}
    assert report["suggested_relinks"] == [{"from": str(clip), "to": str(moved)}]
    assert report["edl_issues"][0]["source"] == "A001"

    assert apply_relinks(edit_dir, report["suggested_relinks"], [edit_dir / "edl.json"]) == 1
    after = verify(edit_dir, edl_path=edit_dir / "edl.json")
    assert after["ok"] is True
    edl = json.loads((edit_dir / "edl.json").read_text(encoding="utf-8"))
    assert edl["timelines"][0]["sources"]["A001"] == "raw/day1/clip.mp4"


def test_verify_does_not_guess_between_several_candidates(tmp_path: Path) -> None:
    clip, edit_dir = make_project(tmp_path)
    for folder in ("a", "b"):
        target = tmp_path / folder / "clip.mp4"
        target.parent.mkdir()
        target.write_bytes(b"12345678")
    clip.unlink()

    report = verify(edit_dir)

    assert len(report["media"][0]["candidates"]) == 2
    assert report["suggested_relinks"] == []


def test_verify_needs_an_index(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="vtc inventory"):
        verify(tmp_path / "edit")


def test_backup_skips_rebuildable_files_and_restores_beside_the_edit_folder(tmp_path: Path) -> None:
    _, edit_dir = make_project(tmp_path)
    (edit_dir / "summaries").mkdir()
    (edit_dir / "summaries" / "clip.md").write_text("## Overview\nx\n", encoding="utf-8")
    (edit_dir / "previews").mkdir()
    (edit_dir / "previews" / "big.mp4").write_bytes(b"0" * 100)
    backups = tmp_path / "backups"
    stamp = datetime(2026, 11, 11, 9, 30, 0)

    archive = create_backup(edit_dir, backups, label="first cut", now=stamp)

    assert archive.name == f"{tmp_path.name}_20261111_093000_first_cut.zip"
    with zipfile.ZipFile(archive) as bundle:
        names = sorted(bundle.namelist())
    assert names == ["edit/edl.json", "edit/media_index.json", "edit/summaries/clip.md"]
    assert list_backups(edit_dir, backups) == [archive]

    with_media = create_backup(edit_dir, backups, include_rebuildable=True, now=datetime(2026, 11, 11, 9, 31, 0))
    with zipfile.ZipFile(with_media) as bundle:
        assert "edit/previews/big.mp4" in bundle.namelist()

    (edit_dir / "summaries" / "clip.md").write_text("changed", encoding="utf-8")
    restored = restore_backup(archive, edit_dir, now=stamp)
    assert restored.name == "edit.restored_20261111_093000"
    assert (restored / "summaries" / "clip.md").read_text(encoding="utf-8") == "## Overview\nx\n"
    assert (edit_dir / "summaries" / "clip.md").read_text(encoding="utf-8") == "changed"


def test_restore_rejects_entries_that_escape_the_restore_folder(tmp_path: Path) -> None:
    _, edit_dir = make_project(tmp_path)
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("edit/../../outside.txt", "x")

    with pytest.raises(ValueError, match="escapes the restore folder"):
        restore_backup(archive, edit_dir)
    assert not (tmp_path.parent / "outside.txt").exists()


def test_backup_reports_missing_or_empty_edit_folder(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        create_backup(tmp_path / "edit", tmp_path / "backups")
    (tmp_path / "edit").mkdir()
    with pytest.raises(FileNotFoundError, match="nothing to back up"):
        create_backup(tmp_path / "edit", tmp_path / "backups")
