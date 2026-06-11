from __future__ import annotations

import json
from pathlib import Path

from helpers.validate_edl import cut_inside_word, validate


def write_edl(
    tmp_path: Path,
    *,
    source_path: str = "raw/clip.mp4",
    fps: float = 30.0,
    range_overrides: dict | None = None,
) -> Path:
    raw_dir = tmp_path / "raw"
    edit_dir = tmp_path / "edit"
    raw_dir.mkdir()
    edit_dir.mkdir()
    (raw_dir / "clip.mp4").write_bytes(b"")
    range_item = {
        "source": "A001",
        "source_start": 0.0,
        "source_end": 2.0,
        "record_start": 0.0,
        "track": 1,
        "beat": "INTRO",
        "quote": "hello",
        "reason": "keep",
    }
    if range_overrides:
        range_item.update(range_overrides)
    edl = {
        "version": 1,
        "project_name": "Example",
        "fps": fps,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": source_path},
                "ranges": [range_item],
            }
        ],
    }
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    return edl_path


def test_validate_accepts_minimal_valid_edl(tmp_path: Path) -> None:
    assert validate(write_edl(tmp_path)) == []


def test_validate_reports_missing_source_file(tmp_path: Path) -> None:
    errors = validate(write_edl(tmp_path, source_path="raw/missing.mp4"))

    assert any("does not exist" in error for error in errors)


def test_validate_reports_source_that_escapes_workspace(tmp_path: Path) -> None:
    errors = validate(write_edl(tmp_path, source_path="../outside.mp4"))

    assert any("escapes workspace" in error for error in errors)


def test_validate_reports_invalid_fps_range_and_media_type(tmp_path: Path) -> None:
    errors = validate(
        write_edl(
            tmp_path,
            fps=0,
            range_overrides={"source_start": 2.0, "source_end": 1.0, "media_type": "audio"},
        )
    )

    assert any("fps must be positive" in error for error in errors)
    assert any("source_end must be greater" in error for error in errors)
    assert any("media_type must be av" in error for error in errors)


def test_cut_inside_word_detects_strict_interior_but_not_boundary_tolerance() -> None:
    words = [{"start": 1.0, "end": 2.0, "text": "hello"}]

    assert cut_inside_word(1.5, words) == words[0]
    assert cut_inside_word(1.01, words) is None
    assert cut_inside_word(1.99, words) is None
