from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from helpers.export_fcpxml import build_fcpxml


def write_invariant_workspace(tmp_path: Path) -> tuple[Path, dict]:
    raw_dir = tmp_path / "raw"
    edit_dir = tmp_path / "edit"
    raw_dir.mkdir()
    edit_dir.mkdir()
    (raw_dir / "clip.mp4").write_bytes(b"")
    (raw_dir / "facecam.mp4").write_bytes(b"")
    edl = {
        "version": 1,
        "project_name": "FCPXML Invariants",
        "fps": 30,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1080, 1920],
                "sources": {"A001": "raw/clip.mp4", "FACE": "raw/facecam.mp4"},
                "ranges": [
                    {
                        "source": "A001",
                        "source_start": 12.0,
                        "source_end": 14.0,
                        "record_start": 0.0,
                        "visual_layers": [
                            {
                                "name": "Screen",
                                "lane": 1,
                                "source_rect": {"x": 0, "y": 270, "width": 480, "height": 540},
                                "dest_rect": {"x": 0, "y": 0, "width": 1080, "height": 864},
                            },
                            {
                                "name": "Facecam",
                                "source": "FACE",
                                "lane": 2,
                                "source_start": 30.0,
                                "source_end": 32.0,
                                "source_rect": {"x": 1440, "y": 120, "width": 480, "height": 540},
                                "dest_rect": {"x": 0, "y": 960, "width": 1080, "height": 864},
                            },
                        ],
                    },
                    {
                        "source": "A001",
                        "source_start": 20.0,
                        "source_end": 24.0,
                        "record_start": 2.0,
                        "speed": 2.0,
                    },
                ],
            }
        ],
    }
    (edit_dir / "media_index.json").write_text(
        json.dumps(
            {
                "media": [
                    {"path": "raw/clip.mp4", "duration": 120.0, "width": 1920, "height": 1080},
                    {"path": "raw/facecam.mp4", "duration": 90.0, "width": 1920, "height": 1080},
                ]
            }
        ),
        encoding="utf-8",
    )
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    return edl_path, edl


def parse_fcpx_time(value: str) -> Fraction:
    assert value.endswith("s")
    raw = value[:-1]
    if "/" in raw:
        numerator, denominator = raw.split("/", maxsplit=1)
        return Fraction(int(numerator), int(denominator))
    return Fraction(int(raw), 1)


def built_tree(tmp_path: Path) -> tuple[ET.Element, dict]:
    edl_path, edl = write_invariant_workspace(tmp_path)
    return build_fcpxml(edl_path).getroot(), edl


def test_all_time_attributes_are_rational_seconds(tmp_path: Path) -> None:
    root, _ = built_tree(tmp_path)
    time_attribute = re.compile(r"^\d+(?:/\d+)?s$")

    for element in root.iter():
        for attribute in ("offset", "start", "duration", "frameDuration"):
            value = element.attrib.get(attribute)
            if value is not None:
                assert time_attribute.match(value), (element.tag, attribute, value)


def test_anchored_clips_offset_equals_parent_start(tmp_path: Path) -> None:
    root, _ = built_tree(tmp_path)

    for parent in root.iter("asset-clip"):
        for child in parent.findall("./asset-clip"):
            assert child.attrib["offset"] == parent.attrib["start"]


def test_lanes_are_positive_and_unique_per_parent(tmp_path: Path) -> None:
    root, _ = built_tree(tmp_path)

    for parent in root.iter("asset-clip"):
        lanes = [int(child.attrib["lane"]) for child in parent.findall("./asset-clip")]
        assert all(lane > 0 for lane in lanes)
        assert len(lanes) == len(set(lanes))


def test_every_ref_resolves(tmp_path: Path) -> None:
    root, _ = built_tree(tmp_path)
    resources = root.find("./resources")
    assert resources is not None
    resource_ids = {child.attrib["id"] for child in list(resources) if child.attrib.get("id")}

    for element in root.iter():
        for attribute in ("ref", "format"):
            value = element.attrib.get(attribute)
            if value is not None:
                assert value in resource_ids, (element.tag, attribute, value)


def test_asset_durations_cover_all_referenced_source_ends(tmp_path: Path) -> None:
    root, edl = built_tree(tmp_path)
    source_end_by_stem: dict[str, float] = {}
    timeline = edl["timelines"][0]
    for source_id, source_path in timeline["sources"].items():
        ends = []
        for item in timeline["ranges"]:
            if item["source"] == source_id:
                ends.append(float(item["source_end"]))
            for layer in item.get("visual_layers") or []:
                if layer.get("source", item["source"]) == source_id:
                    ends.append(float(layer.get("source_end", item["source_end"])))
        source_end_by_stem[Path(source_path).stem] = max(ends)

    # The fixture maps source ids to asset names, so source_end comparison is
    # enough to enforce the duration rule without reverse-parsing media-rep URLs.
    for asset in root.findall("./resources/asset"):
        assert parse_fcpx_time(asset.attrib["duration"]) >= source_end_by_stem[asset.attrib["name"]]


def test_primary_clips_with_layers_keep_one_visible_primary(tmp_path: Path) -> None:
    root, _ = built_tree(tmp_path)

    for clip in root.findall("./library/event/project/sequence/spine/asset-clip"):
        layers = clip.findall("./asset-clip")
        if not layers:
            continue
        assert clip.attrib.get("srcEnable") != "audio"
        assert clip.find("./adjust-crop") is not None
        assert clip.find("./adjust-transform") is not None
        assert [layer.attrib["srcEnable"] for layer in layers] == ["video"]
