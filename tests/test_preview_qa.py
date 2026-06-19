from __future__ import annotations

import json
from pathlib import Path

from helpers.cli import COMMANDS
from helpers.qa_preview import default_contact_sheet_path, default_report_path, qa_preview
from helpers.render_preview import _segment_args, preview_path


def write_preview_edl(tmp_path: Path) -> Path:
    raw_dir = tmp_path / "raw"
    edit_dir = tmp_path / "edit"
    raw_dir.mkdir()
    edit_dir.mkdir()
    (raw_dir / "clip.mp4").write_bytes(b"")
    edl = {
        "version": 1,
        "project_name": "My/Edit Preview",
        "fps": 30,
        "timelines": [
            {
                "name": "Main Timeline",
                "resolution": [1920, 1080],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": [
                    {"source": "A001", "source_start": 0.0, "source_end": 1.0, "record_start": 0.0},
                    {"source": "A001", "source_start": 2.0, "source_end": 3.0, "record_start": 2.0},
                ],
            },
            {
                "name": "Alt Timeline",
                "resolution": [1280, 720],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": [{"source": "A001", "source_start": 0.0, "source_end": 1.0, "record_start": 0.0}],
            },
        ],
    }
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    return edl_path


def write_transform_coverage_edl(tmp_path: Path) -> Path:
    edl_path = write_preview_edl(tmp_path)
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["timelines"][0]["ranges"][0]["transform"] = {"zoom": 1.07, "pan": 0.0, "tilt": -151.2}
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    return edl_path


def test_preview_commands_are_registered() -> None:
    assert COMMANDS["render-preview"] == ("helpers.render_preview", "Render an MP4 preview from an EDL")
    assert COMMANDS["qa-preview"] == ("helpers.qa_preview", "Run automated QA checks for a preview render")


def test_preview_path_sanitizes_project_and_timeline_names(tmp_path: Path) -> None:
    edl_path = write_preview_edl(tmp_path)
    edl = json.loads(edl_path.read_text(encoding="utf-8"))

    assert preview_path(edl_path, edl, edl["timelines"][0]).name == (
        "My_Edit_Preview_Main_Timeline_preview.mp4"
    )
    assert preview_path(edl_path, edl, edl["timelines"][1]).name == (
        "My_Edit_Preview_Alt_Timeline_preview.mp4"
    )


def test_default_qa_paths_live_under_edit_qa(tmp_path: Path) -> None:
    edl_path = write_preview_edl(tmp_path)

    assert default_report_path(edl_path) == tmp_path / "edit" / "qa" / "preview_report.json"
    assert default_contact_sheet_path(edl_path) == tmp_path / "edit" / "qa" / "contact_sheet.jpg"


def test_segment_args_use_fill_conform_and_compensated_transform(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("helpers.render_preview.find_ffmpeg", lambda: "ffmpeg")

    args = _segment_args(
        tmp_path / "raw" / "clip.mp4",
        0.0,
        1.0,
        1920,
        1080,
        30.0,
        tmp_path / "out.mp4",
        {"video", "audio"},
        {"zoom": 1.07, "pan": 0.0, "tilt": -151.2},
    )
    filter_arg = args[args.index("-vf") + 1]

    assert "force_original_aspect_ratio=increase" in filter_arg
    assert "pad=" not in filter_arg
    assert "scale=2458:1384" in filter_arg
    assert "crop=1920:1080" in filter_arg


def test_qa_preview_writes_report_without_external_probe(tmp_path: Path, monkeypatch) -> None:
    edl_path = write_preview_edl(tmp_path)
    preview = preview_path(edl_path)
    preview.parent.mkdir()
    preview.write_bytes(b"fake mp4")

    monkeypatch.setattr("helpers.qa_preview.media_duration", lambda path: 3.0)
    monkeypatch.setattr("helpers.qa_preview.stream_types", lambda path: {"audio", "video"})
    monkeypatch.setattr("helpers.qa_preview.build_contact_sheet", lambda preview_path, out_path: True)

    report = qa_preview(edl_path)

    report_path = default_report_path(edl_path)
    assert report_path.exists()
    assert report["expected_duration"] == 3.0
    assert report["actual_duration"] == 3.0
    assert report["checks"]["preview_exists"] is True
    assert report["checks"]["duration_matches_edl"] is True
    assert report["checks"]["record_gaps_found"] is True
    assert report["gaps"] == [{"record_start": 1.0, "record_end": 2.0, "duration": 1.0}]


def test_qa_preview_flags_transform_zoom_that_exposes_empty_frame_area(tmp_path: Path, monkeypatch) -> None:
    edl_path = write_transform_coverage_edl(tmp_path)
    preview = preview_path(edl_path)
    preview.parent.mkdir()
    preview.write_bytes(b"fake mp4")

    monkeypatch.setattr("helpers.qa_preview.media_duration", lambda path: 3.0)
    monkeypatch.setattr("helpers.qa_preview.stream_types", lambda path: {"audio", "video"})
    monkeypatch.setattr("helpers.qa_preview.build_contact_sheet", lambda preview_path, out_path: True)

    report = qa_preview(edl_path)

    assert report["checks"]["transform_coverage_ok"] is False
    assert report["checks"]["empty_space_risk_found"] is True
    assert report["transform_coverage_issues"][0]["requested_zoom"] == 1.07
    assert report["transform_coverage_issues"][0]["minimum_zoom"] == 1.28
