from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers.export_fcpxml import build_fcpxml, default_fcpxml_path, timeline_duration


def write_fcpx_edl(
    tmp_path: Path,
    ranges: list[dict] | None = None,
    *,
    project_name: str = "Example Project",
) -> tuple[Path, dict]:
    raw_dir = tmp_path / "raw"
    edit_dir = tmp_path / "edit"
    raw_dir.mkdir()
    edit_dir.mkdir()
    (raw_dir / "clip.mp4").write_bytes(b"")
    edl = {
        "version": 1,
        "project_name": project_name,
        "fps": 30,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": ranges
                or [
                    {"source": "A001", "source_start": 0.0, "source_end": 1.0, "record_start": 0.0},
                    {"source": "A001", "source_start": 2.0, "source_end": 3.0, "record_start": 2.0},
                ],
            }
        ],
    }
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    return edl_path, edl


def test_timeline_duration_uses_latest_record_end() -> None:
    timeline = {
        "ranges": [
            {"record_start": 5.0, "source_start": 1.0, "source_end": 2.0},
            {"record_start": 2.0, "source_start": 0.0, "source_end": 4.0},
        ]
    }

    assert timeline_duration(timeline) == 6.0


def test_build_fcpxml_creates_root_asset_and_gap(tmp_path: Path) -> None:
    edl_path, _ = write_fcpx_edl(tmp_path)

    root = build_fcpxml(edl_path).getroot()

    assert root.tag == "fcpxml"
    assert len(root.findall("./resources/asset")) == 1
    spine = root.find("./library/event/project/sequence/spine")
    assert spine is not None
    assert spine.find("gap") is not None


def test_build_fcpxml_rejects_range_that_rounds_to_zero_frames(tmp_path: Path) -> None:
    edl_path, _ = write_fcpx_edl(
        tmp_path,
        ranges=[{"source": "A001", "source_start": 0.0, "source_end": 0.001, "record_start": 0.0}],
    )

    with pytest.raises(ValueError, match="rounds to zero frames"):
        build_fcpxml(edl_path)


def test_default_fcpxml_path_sanitizes_project_name(tmp_path: Path) -> None:
    edl_path, edl = write_fcpx_edl(tmp_path, project_name="My Project:/Cut")

    assert default_fcpxml_path(edl_path, edl).name == "My_Project_Cut.fcpxml"
