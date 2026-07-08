from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pytest

from helpers.export_fcpxml import (
    FCPXML_VERSION,
    RANGE_ID_METADATA_KEY,
    build_fcpxml,
    default_fcpxml_path,
    fcpx_time_from_frames,
    fps_fraction,
    frame_duration,
    timeline_duration,
)


def write_fcpx_edl(
    tmp_path: Path,
    ranges: list[dict] | None = None,
    *,
    fps: float = 30,
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
        "fps": fps,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": ranges
                or [
                    {"source": "A001", "source_start": 0.0, "source_end": 1.0, "record_start": 0.0},
                    {"source": "A001", "source_start": 2.0, "source_end": 3.0, "record_start": 1.0},
                ],
            }
        ],
    }
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    return edl_path, edl


def parse_fcpx_time(value: str) -> Fraction:
    assert value.endswith("s")
    time_value = value[:-1]
    if "/" in time_value:
        numerator, denominator = time_value.split("/", maxsplit=1)
        return Fraction(int(numerator), int(denominator))
    return Fraction(int(time_value), 1)


def test_timeline_duration_uses_latest_record_end() -> None:
    timeline = {
        "ranges": [
            {"record_start": 5.0, "source_start": 1.0, "source_end": 2.0},
            {"record_start": 2.0, "source_start": 0.0, "source_end": 4.0},
        ]
    }

    assert timeline_duration(timeline) == 6.0


def test_timeline_duration_uses_speed() -> None:
    timeline = {
        "ranges": [
            {"record_start": 0.0, "source_start": 0.0, "source_end": 4.0, "speed": 2.0},
            {"record_start": 2.0, "source_start": 10.0, "source_end": 11.0},
        ]
    }

    assert timeline_duration(timeline) == 3.0


def test_build_fcpxml_creates_root_asset_without_gap(tmp_path: Path) -> None:
    edl_path, _ = write_fcpx_edl(tmp_path)

    root = build_fcpxml(edl_path).getroot()

    assert root.tag == "fcpxml"
    assert root.attrib["version"] == FCPXML_VERSION
    assert len(root.findall("./resources/asset")) == 1
    spine = root.find("./library/event/project/sequence/spine")
    assert spine is not None
    assert spine.find("gap") is None


def test_build_fcpxml_rejects_record_gap(tmp_path: Path) -> None:
    edl_path, _ = write_fcpx_edl(
        tmp_path,
        ranges=[
            {"source": "A001", "source_start": 0.0, "source_end": 1.0, "record_start": 0.0},
            {"source": "A001", "source_start": 2.0, "source_end": 3.0, "record_start": 2.0},
        ],
    )

    with pytest.raises(ValueError, match="record gap"):
        build_fcpxml(edl_path)


def test_build_fcpxml_adds_fill_conform_to_avoid_empty_canvas(tmp_path: Path) -> None:
    edl_path, _ = write_fcpx_edl(tmp_path)

    root = build_fcpxml(edl_path).getroot()
    conform = root.find("./library/event/project/sequence/spine/asset-clip/adjust-conform")

    assert conform is not None
    assert conform.attrib["type"] == "fill"


def test_build_fcpxml_adds_stable_range_id_metadata(tmp_path: Path) -> None:
    edl_path, _ = write_fcpx_edl(tmp_path)

    root = build_fcpxml(edl_path).getroot()
    metadata = root.find("./library/event/project/sequence/spine/asset-clip/metadata/md")

    assert metadata is not None
    assert metadata.attrib["key"] == RANGE_ID_METADATA_KEY
    assert metadata.attrib["value"] == "t001-r0001"


def test_build_fcpxml_adds_resolve_style_time_map_for_speed(tmp_path: Path) -> None:
    edl_path, _ = write_fcpx_edl(
        tmp_path,
        ranges=[
            {"source": "A001", "source_start": 0.0, "source_end": 4.0, "record_start": 0.0, "speed": 2.0},
            {"source": "A001", "source_start": 10.0, "source_end": 11.0, "record_start": 2.0},
        ],
    )

    root = build_fcpxml(edl_path).getroot()
    clip = root.find("./library/event/project/sequence/spine/asset-clip")
    time_map = root.find("./library/event/project/sequence/spine/asset-clip/timeMap")
    points = root.findall("./library/event/project/sequence/spine/asset-clip/timeMap/timept")

    assert clip is not None
    assert clip.attrib["duration"] == "2s"
    assert time_map is not None
    assert time_map.attrib["frameSampling"] == "floor"
    assert [point.attrib for point in points] == [
        {"time": "0s", "interp": "linear", "value": "0s"},
        {"time": "2s", "interp": "linear", "value": "4s"},
    ]


def test_build_fcpxml_compensates_zoom_for_transform_position(tmp_path: Path) -> None:
    edl_path, _ = write_fcpx_edl(
        tmp_path,
        ranges=[
            {
                "source": "A001",
                "source_start": 0.0,
                "source_end": 1.0,
                "record_start": 0.0,
                "transform": {"zoom": 1.07, "pan": 0.0, "tilt": -151.2},
            }
        ],
    )

    root = build_fcpxml(edl_path).getroot()
    transform = root.find("./library/event/project/sequence/spine/asset-clip/adjust-transform")

    assert transform is not None
    assert transform.attrib["position"] == "0.000 -151.200"
    assert transform.attrib["scale"] == "1.280 1.280"


def test_build_fcpxml_exports_gameplay_screen_preset_transform(tmp_path: Path) -> None:
    edl_path, _ = write_fcpx_edl(
        tmp_path,
        ranges=[
            {
                "source": "A001",
                "source_start": 0.0,
                "source_end": 1.0,
                "record_start": 0.0,
                "transform": {
                    "preset": "gameplay-screen",
                    "facecam": {"x": 0, "y": 720, "width": 320, "height": 360},
                },
            }
        ],
    )

    root = build_fcpxml(edl_path).getroot()
    transform = root.find("./library/event/project/sequence/spine/asset-clip/adjust-transform")

    assert transform is not None
    assert transform.attrib["position"] == "-192.000 0.000"
    assert transform.attrib["scale"] == "1.200 1.200"


def test_build_fcpxml_exports_visual_layers_as_connected_video_clips(tmp_path: Path) -> None:
    edl_path, edl = write_fcpx_edl(
        tmp_path,
        ranges=[
            {
                "source": "A001",
                "source_start": 0.0,
                "source_end": 2.0,
                "record_start": 0.0,
                "visual_layers": [
                    {
                        "name": "Facecam",
                        "source_rect": {"x": 0.0, "y": 0.45, "width": 0.25, "height": 0.35},
                        "dest_rect": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.45},
                    },
                    {
                        "name": "Screen",
                        "source_rect": {"x": 0.0, "y": 0.0, "width": 0.75, "height": 0.75},
                        "dest_rect": {"x": 0.0, "y": 0.5, "width": 1.0, "height": 0.45},
                    },
                ],
            }
        ],
    )
    edl["timelines"][0]["resolution"] = [1080, 1920]
    edl_path.write_text(json.dumps(edl), encoding="utf-8")

    root = build_fcpxml(edl_path).getroot()
    primary = root.find("./library/event/project/sequence/spine/asset-clip")
    layers = root.findall("./library/event/project/sequence/spine/asset-clip/asset-clip")

    assert primary is not None
    assert primary.attrib["name"] == "Screen"
    assert "srcEnable" not in primary.attrib
    assert [layer.attrib["name"] for layer in layers] == ["Facecam"]
    assert [layer.attrib["srcEnable"] for layer in layers] == ["video"]
    assert [layer.attrib["lane"] for layer in layers] == ["1"]
    assert [layer.attrib["offset"] for layer in layers] == [primary.attrib["start"]]

    first_trim = layers[0].find("./adjust-crop/trim-rect")
    first_conform = layers[0].find("./adjust-conform")
    first_transform = layers[0].find("./adjust-transform")

    assert first_trim is not None
    assert first_trim.attrib == {
        "right": "37.5",
        "top": "56.875",
        "bottom": "31.875",
    }
    assert first_conform is None
    assert first_transform is not None
    assert first_transform.attrib["anchor"] == "0 0"
    assert first_transform.attrib["position"] == "84.375 27.500"
    assert first_transform.attrib["scale"] == "4.000000 4.000000"


def test_build_fcpxml_anchors_layers_at_parent_start(tmp_path: Path) -> None:
    edl_path, _ = write_fcpx_edl(
        tmp_path,
        ranges=[
            {
                "source": "A001",
                "source_start": 12.0,
                "source_end": 14.0,
                "record_start": 0.0,
                "visual_layers": [
                    {
                        "name": "Layer",
                        "source_rect": {"x": 0, "y": 0, "width": 1, "height": 1},
                        "dest_rect": {"x": 0, "y": 0, "width": 1, "height": 1},
                    }
                ],
            }
        ],
    )

    root = build_fcpxml(edl_path).getroot()
    primary = root.find("./library/event/project/sequence/spine/asset-clip")
    layers = root.findall("./library/event/project/sequence/spine/asset-clip/asset-clip")

    assert primary is not None
    assert primary.attrib["start"] == "12s"
    assert not layers
    assert primary.find("./adjust-transform") is not None


def test_build_fcpxml_layer_only_source_gets_media_duration_and_format(tmp_path: Path) -> None:
    edl_path, edl = write_fcpx_edl(
        tmp_path,
        ranges=[
            {
                "source": "A001",
                "source_start": 0.0,
                "source_end": 2.0,
                "record_start": 0.0,
                "visual_layers": [
                    {
                        "name": "Facecam",
                        "source": "FACE",
                        "source_start": 20.0,
                        "source_end": 22.0,
                        "source_rect": {"x": 0, "y": 0, "width": 1, "height": 1},
                        "dest_rect": {"x": 0, "y": 0, "width": 1, "height": 0.5},
                    }
                ],
            }
        ],
    )
    (tmp_path / "raw" / "facecam.mp4").write_bytes(b"")
    edl["timelines"][0]["resolution"] = [1080, 1920]
    edl["timelines"][0]["sources"]["FACE"] = "raw/facecam.mp4"
    (tmp_path / "edit" / "media_index.json").write_text(
        json.dumps(
            {
                "media": [
                    {
                        "path": "raw/facecam.mp4",
                        "duration": 90.0,
                        "width": 1920,
                        "height": 1080,
                        "audio_channels": 2,
                        "audio_rate": 48000,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    edl_path.write_text(json.dumps(edl), encoding="utf-8")

    root = build_fcpxml(edl_path).getroot()
    formats = {fmt.attrib["id"]: fmt for fmt in root.findall("./resources/format")}
    facecam = next(asset for asset in root.findall("./resources/asset") if asset.attrib["name"] == "facecam")
    facecam_format = formats[facecam.attrib["format"]]
    facecam_layer = root.find("./library/event/project/sequence/spine/asset-clip/asset-clip")
    assert facecam_layer is not None

    assert parse_fcpx_time(facecam.attrib["duration"]) == Fraction(90, 1)
    assert facecam_format.attrib["width"] == "1920"
    assert facecam_format.attrib["height"] == "1080"
    assert facecam_layer.attrib["format"] == facecam.attrib["format"]


def test_build_fcpxml_asset_duration_covers_visual_layers_across_timelines(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    edit_dir = tmp_path / "edit"
    raw_dir.mkdir()
    edit_dir.mkdir()
    (raw_dir / "clip.mp4").write_bytes(b"")
    edl = {
        "version": 1,
        "project_name": "Multi Timeline Shorts",
        "fps": 30,
        "timelines": [
            {
                "name": "Short 01",
                "resolution": [1080, 1920],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": [
                    {
                        "source": "A001",
                        "source_start": 10.0,
                        "source_end": 12.0,
                        "record_start": 0.0,
                    }
                ],
            },
            {
                "name": "Short 02",
                "resolution": [1080, 1920],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": [
                    {
                        "source": "A001",
                        "source_start": 100.0,
                        "source_end": 102.0,
                        "record_start": 0.0,
                        "visual_layers": [
                            {
                                "name": "Facecam",
                                "source_rect": {"x": 0.0, "y": 0.0, "width": 0.2, "height": 0.2},
                                "dest_rect": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.35},
                            },
                            {
                                "name": "Gameplay",
                                "source_rect": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
                                "dest_rect": {"x": 0.0, "y": 0.4, "width": 1.0, "height": 0.55},
                            },
                        ],
                    }
                ],
            },
        ],
    }
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(json.dumps(edl), encoding="utf-8")

    root = build_fcpxml(edl_path).getroot()
    assets = root.findall("./resources/asset")
    projects = root.findall("./library/event/project")
    second_primary = projects[1].find("./sequence/spine/asset-clip")
    assert second_primary is not None
    layers = second_primary.findall("./asset-clip")

    assert len(assets) == 1
    assert parse_fcpx_time(assets[0].attrib["duration"]) >= Fraction(102, 1)
    assert second_primary.attrib["name"] == "Gameplay"
    assert "srcEnable" not in second_primary.attrib
    assert [layer.attrib["name"] for layer in layers] == ["Facecam"]


def test_build_fcpxml_layer_geometry_for_horizontal_source_on_vertical_timeline(tmp_path: Path) -> None:
    edl_path, edl = write_fcpx_edl(
        tmp_path,
        ranges=[
            {
                "source": "A001",
                "source_start": 0.0,
                "source_end": 2.0,
                "record_start": 0.0,
                "visual_layers": [
                    {
                        "name": "Gameplay",
                        "source": "GAME",
                        "source_rect": {"x": 0, "y": 270, "width": 480, "height": 540},
                        "dest_rect": {"x": 0, "y": 0, "width": 1080, "height": 864},
                    }
                ],
            }
        ],
    )
    (tmp_path / "raw" / "gameplay.mp4").write_bytes(b"")
    edl["timelines"][0]["resolution"] = [1080, 1920]
    edl["timelines"][0]["sources"]["GAME"] = "raw/gameplay.mp4"
    (tmp_path / "edit" / "media_index.json").write_text(
        json.dumps({"media": [{"path": "raw/gameplay.mp4", "duration": 90.0, "width": 1920, "height": 1080}]}),
        encoding="utf-8",
    )
    edl_path.write_text(json.dumps(edl), encoding="utf-8")

    root = build_fcpxml(edl_path).getroot()
    layer = root.find("./library/event/project/sequence/spine/asset-clip/asset-clip")
    assert layer is not None
    trim = layer.find("./adjust-crop/trim-rect")
    conform = layer.find("./adjust-conform")
    transform = layer.find("./adjust-transform")

    assert trim is not None
    assert trim.attrib == {
        "right": "37.5",
        "top": "32.222222",
        "bottom": "32.222222",
    }
    assert conform is None
    assert transform is not None
    assert transform.attrib["anchor"] == "0 0"
    assert transform.attrib["position"] == "84.375 27.500"
    assert transform.attrib["scale"] == "4.000000 4.000000"


def test_build_fcpxml_keeps_horizontal_crop_compensation_but_places_y_by_destination(tmp_path: Path) -> None:
    edl_path, edl = write_fcpx_edl(
        tmp_path,
        ranges=[
            {
                "source": "A001",
                "source_start": 325.333333,
                "source_end": 338.866666,
                "record_start": 0.0,
                "visual_layers": [
                    {
                        "name": "Facecam",
                        "source_rect": {"x": 0, "y": 610, "width": 700, "height": 500},
                        "dest_rect": {"x": 0, "y": 0, "width": 1080, "height": 850},
                    },
                    {
                        "name": "Screen",
                        "source_rect": {"x": 0, "y": 0, "width": 2560, "height": 1440},
                        "dest_rect": {"x": 0, "y": 1020, "width": 1080, "height": 760},
                    },
                ],
            }
        ],
    )
    edl["timelines"][0]["resolution"] = [1080, 1920]
    (tmp_path / "edit" / "media_index.json").write_text(
        json.dumps({"media": [{"path": "raw/clip.mp4", "duration": 705.733333, "width": 2560, "height": 1440}]}),
        encoding="utf-8",
    )
    edl_path.write_text(json.dumps(edl), encoding="utf-8")

    root = build_fcpxml(edl_path).getroot()
    facecam = root.find("./library/event/project/sequence/spine/asset-clip/asset-clip")
    assert facecam is not None
    trim = facecam.find("./adjust-crop/trim-rect")
    transform = facecam.find("./adjust-transform")

    assert trim is not None
    assert trim.attrib == {
        "left": "0.631893",
        "right": "36.960018",
        "top": "42.361111",
        "bottom": "22.916667",
    }
    assert transform is not None
    assert transform.attrib["position"] == "82.344 27.865"
    assert transform.attrib["scale"] == "4.029630 4.029630"


def test_build_fcpxml_rejects_range_that_rounds_to_zero_frames(tmp_path: Path) -> None:
    edl_path, _ = write_fcpx_edl(
        tmp_path,
        ranges=[{"source": "A001", "source_start": 0.0, "source_end": 0.001, "record_start": 0.0}],
    )

    with pytest.raises(ValueError, match="shorter than the minimum"):
        build_fcpxml(edl_path)


def test_default_fcpxml_path_sanitizes_project_name(tmp_path: Path) -> None:
    edl_path, edl = write_fcpx_edl(tmp_path, project_name="My Project:/Cut")

    assert default_fcpxml_path(edl_path, edl).name == "My_Project_Cut.fcpxml"


@pytest.mark.parametrize(
    ("fps", "expected"),
    [
        (30.0, Fraction(30, 1)),
        (29.97002997002997, Fraction(30000, 1001)),
        (29.97, Fraction(30000, 1001)),
        (23.976, Fraction(24000, 1001)),
        (25, Fraction(25, 1)),
        (59.94, Fraction(60000, 1001)),
    ],
)
def test_fps_fraction_maps_common_rates(fps: float, expected: Fraction) -> None:
    assert fps_fraction(fps) == expected


def test_frame_duration_uses_rational_frame_rate() -> None:
    assert frame_duration(29.97002997002997) == "1001/30000s"
    assert frame_duration(30) == "1/30s"


def test_fcpx_time_from_frames_uses_rational_frame_rate() -> None:
    assert fcpx_time_from_frames(1, 29.97002997002997) == "1001/30000s"


def test_build_fcpxml_uses_integer_rational_time_attributes_for_ntsc_fps(tmp_path: Path) -> None:
    edl_path, _ = write_fcpx_edl(tmp_path, fps=29.97002997002997)

    root = build_fcpxml(edl_path).getroot()

    time_attribute = re.compile(r"^\d+(?:/\d+)?s$")
    for element in root.iter():
        for attribute in ("offset", "start", "duration", "frameDuration"):
            value = element.attrib.get(attribute)
            if value is not None:
                assert time_attribute.match(value), (element.tag, attribute, value)

    serialized = ET.tostring(root, encoding="unicode")
    serialized_time_attribute = re.compile(r'\b(?:offset|start|duration|frameDuration)="([^"]+)"')
    assert serialized_time_attribute.findall(serialized)
    for value in serialized_time_attribute.findall(serialized):
        assert time_attribute.match(value), value


def test_build_fcpxml_sequence_duration_matches_timeline_duration_for_ntsc_fps(tmp_path: Path) -> None:
    edl_path, edl = write_fcpx_edl(tmp_path, fps=29.97002997002997)

    root = build_fcpxml(edl_path).getroot()
    sequence = root.find("./library/event/project/sequence")
    assert sequence is not None
    duration = sequence.attrib["duration"]

    actual_seconds = parse_fcpx_time(duration)
    expected_seconds = Fraction.from_float(timeline_duration(edl["timelines"][0])).limit_denominator(100000)
    one_frame = Fraction(1001, 30000)
    assert abs(actual_seconds - expected_seconds) <= one_frame
