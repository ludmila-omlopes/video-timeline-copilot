from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from helpers.cli import COMMANDS
from helpers.qa_preview import default_contact_sheet_path, default_report_path, qa_preview
from helpers.render_fcpxml_preview import _layer_geometry, _trimmed_source_rect
from helpers.render_preview import _layered_segment_args, _segment_args, preview_path, render_preview


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
    assert COMMANDS["render-fcpxml-preview"] == (
        "helpers.render_fcpxml_preview",
        "Render an MP4 preview from an FCPXML file",
    )
    assert COMMANDS["qa-preview"] == ("helpers.qa_preview", "Run automated QA checks for a preview render")


def test_fcpxml_preview_applies_resolve_horizontal_crop_factor() -> None:
    clip = ET.fromstring(
        """
        <asset-clip>
          <adjust-crop mode="trim">
            <trim-rect top="0.791605" right="45.0833" bottom="78.7916" />
          </adjust-crop>
        </asset-clip>
        """
    )

    crop_x, crop_y, crop_w, crop_h = _trimmed_source_rect(
        clip,
        source_width=2560,
        source_height=1440,
        timeline_width=1080,
        timeline_height=1920,
        resolve_crop_x_factor=2.0,
    )

    assert crop_x == 0
    assert crop_y == 11
    assert crop_w == 252
    assert crop_h == 294


def test_fcpxml_preview_treats_transform_y_as_resolve_y_up() -> None:
    clip = ET.fromstring(
        """
        <asset-clip>
          <adjust-transform position="0 25" scale="1 1" />
        </asset-clip>
        """
    )

    overlay_x, overlay_y, display_w, display_h = _layer_geometry(
        clip,
        crop_x=0,
        crop_width=1080,
        crop_height=960,
        source_width=1080,
        source_height=1920,
        timeline_width=1080,
        timeline_height=1920,
    )

    assert (overlay_x, overlay_y, display_w, display_h) == (0, 0, 1080, 960)


def test_fcpxml_preview_applies_horizontal_source_center_compensation() -> None:
    clip = ET.fromstring(
        """
        <asset-clip>
          <adjust-transform position="82.344 27.865" scale="4.02963 4.02963" />
        </asset-clip>
        """
    )

    overlay_x, overlay_y, display_w, display_h = _layer_geometry(
        clip,
        crop_x=32,
        crop_width=635,
        crop_height=500,
        source_width=2560,
        source_height=1440,
        timeline_width=1080,
        timeline_height=1920,
    )

    assert abs(overlay_x) <= 2
    assert overlay_y == 0
    assert display_w == 1080
    assert display_h == 850


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


def test_segment_args_apply_speed_to_audio_and_video(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("helpers.render_preview.find_ffmpeg", lambda: "ffmpeg")

    args = _segment_args(
        tmp_path / "raw" / "clip.mp4",
        0.0,
        4.0,
        2.0,
        1920,
        1080,
        30.0,
        tmp_path / "out.mp4",
        {"video", "audio"},
    )

    assert args[args.index("-t") + 1] == "4.000000"
    assert args[args.index("-vf") + 1].startswith("setpts=0.5*PTS")
    assert "atempo=2" in args[args.index("-af") + 1]
    assert args[args.index("-af") + 1].endswith("apad")


def test_layered_segment_args_builds_crop_overlay_filter_graph(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("helpers.render_preview.find_ffmpeg", lambda: "ffmpeg")
    source = tmp_path / "raw" / "clip.mp4"
    out = tmp_path / "out.mp4"
    item = {
        "source": "A001",
        "source_start": 10.0,
        "source_end": 12.0,
        "visual_layers": [
            {
                "name": "Facecam",
                "source_rect": {"x": 0, "y": 480, "width": 478, "height": 374},
                "dest_rect": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.45},
            },
            {
                "name": "Screen",
                "source_rect": {"x": 260, "y": 150, "width": 1280, "height": 720},
                "dest_rect": {"x": 0.0, "y": 0.5, "width": 1.0, "height": 0.45},
            },
        ],
    }

    args = _layered_segment_args(
        source,
        10.0,
        2.0,
        2.0,
        1080,
        1920,
        30.0,
        out,
        {"video", "audio"},
        item,
        {"A001": source},
        {source: (1912, 1070)},
    )
    filter_graph = args[args.index("-filter_complex") + 1]

    assert "-vf" not in args
    assert args.count("-i") == 4
    assert "color=c=black:s=1080x1920:r=30.0:d=2.000000" in args
    assert "crop=478:374:0:480" in filter_graph
    assert "crop=1280:720:260:150" in filter_graph
    assert "scale=1080:864" in filter_graph
    assert "overlay=x=0:y=0" in filter_graph
    assert "overlay=x=0:y=960" in filter_graph
    assert args[args.index("-map") + 1] == "[vout]"


def test_render_preview_probes_each_source_once(tmp_path: Path, monkeypatch) -> None:
    raw_dir = tmp_path / "raw"
    edit_dir = tmp_path / "edit"
    raw_dir.mkdir()
    edit_dir.mkdir()
    (raw_dir / "clip.mp4").write_bytes(b"")
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(
        json.dumps(
            {
                "version": 1,
                "project_name": "Probe Cache",
                "fps": 30,
                "timelines": [
                    {
                        "name": "Main",
                        "resolution": [1920, 1080],
                        "sources": {"s1": "raw/clip.mp4"},
                        "ranges": [
                            {"source": "s1", "source_start": 0.0, "source_end": 1.0, "record_start": 0.0},
                            {"source": "s1", "source_start": 1.0, "source_end": 2.0, "record_start": 1.0},
                            {"source": "s1", "source_start": 2.0, "source_end": 3.0, "record_start": 2.0},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    probed_sources = []
    subprocess_calls = []

    def fake_stream_types(path: Path) -> set[str]:
        probed_sources.append(path)
        return {"video", "audio"}

    def fake_run(args: list[str], check: bool) -> SimpleNamespace:
        subprocess_calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("helpers.render_preview.find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr("helpers.render_preview.stream_types", fake_stream_types)
    monkeypatch.setattr("helpers.render_preview.video_dimensions", lambda path: None)
    monkeypatch.setattr("helpers.render_preview.subprocess.run", fake_run)

    render_preview(edl_path)

    assert len(probed_sources) == 1
    assert len(subprocess_calls) == 4


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
    assert report["gaps"] == [
        {"range_index": 1, "record_start": 1.0, "record_end": 2.0, "duration": 1.0, "frames": 30}
    ]


def test_qa_preview_flags_half_second_clip(tmp_path: Path, monkeypatch) -> None:
    edl_path = write_preview_edl(tmp_path)
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["timelines"][0]["ranges"] = [
        {"source": "A001", "source_start": 0.0, "source_end": 0.5, "record_start": 0.0}
    ]
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    preview = preview_path(edl_path)
    preview.parent.mkdir()
    preview.write_bytes(b"fake mp4")

    monkeypatch.setattr("helpers.qa_preview.media_duration", lambda path: 0.5)
    monkeypatch.setattr("helpers.qa_preview.stream_types", lambda path: {"audio", "video"})
    monkeypatch.setattr("helpers.qa_preview.build_contact_sheet", lambda preview_path, out_path: True)

    report = qa_preview(edl_path)

    assert report["checks"]["short_clips_found"] is True
    assert report["short_clips"][0]["duration"] == 0.5


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
