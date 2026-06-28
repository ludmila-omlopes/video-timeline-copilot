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
