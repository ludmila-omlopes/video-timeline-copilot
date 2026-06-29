from __future__ import annotations

import copy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from helpers.export_fcpxml import write_fcpxml
from helpers.import_fcpxml import import_fcpxml


def write_base_edl(tmp_path: Path) -> Path:
    raw_dir = tmp_path / "raw"
    edit_dir = tmp_path / "edit"
    raw_dir.mkdir()
    edit_dir.mkdir()
    (raw_dir / "clip.mp4").write_bytes(b"")
    edl = {
        "version": 1,
        "project_name": "Example",
        "fps": 30.0,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": [
                    {
                        "source": "A001",
                        "source_start": 0.0,
                        "source_end": 1.0,
                        "record_start": 0.0,
                        "track": 1,
                        "beat": "INTRO",
                        "quote": "hello",
                        "reason": "keep intro",
                    },
                    {
                        "source": "A001",
                        "source_start": 2.0,
                        "source_end": 3.0,
                        "record_start": 1.0,
                        "track": 1,
                        "beat": "BODY",
                        "quote": "world",
                        "reason": "keep body",
                    },
                ],
            }
        ],
    }
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    return edl_path


def exported_xml(edl_path: Path) -> Path:
    xml_path = edl_path.parent / "Example.fcpxml"
    write_fcpxml(edl_path, xml_path)
    return xml_path


def imported_payload(edl_path: Path) -> dict:
    return json.loads(edl_path.read_text(encoding="utf-8"))


def test_import_fcpxml_round_trips_exported_ranges_and_metadata(tmp_path: Path) -> None:
    base_edl = write_base_edl(tmp_path)
    xml_path = exported_xml(base_edl)
    out_path = base_edl.parent / "edl.imported.json"

    report = import_fcpxml(xml_path, base_edl, out_path)
    imported = imported_payload(out_path)

    assert report["status"] == "pass"
    ranges = imported["timelines"][0]["ranges"]
    assert [item["id"] for item in ranges] == ["t001-r0001", "t001-r0002"]
    assert [item["source_start"] for item in ranges] == [0.0, 2.0]
    assert ranges[0]["beat"] == "INTRO"
    assert ranges[1]["reason"] == "keep body"


def test_import_fcpxml_keeps_nle_trims(tmp_path: Path) -> None:
    base_edl = write_base_edl(tmp_path)
    xml_path = exported_xml(base_edl)
    tree = ET.parse(xml_path)
    first_clip = tree.getroot().find("./library/event/project/sequence/spine/asset-clip")
    assert first_clip is not None
    first_clip.attrib["start"] = "5/30s"
    first_clip.attrib["duration"] = "25/30s"
    second_clip = tree.getroot().findall("./library/event/project/sequence/spine/asset-clip")[1]
    second_clip.attrib["offset"] = "25/30s"
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    out_path = base_edl.parent / "edl.imported.json"

    report = import_fcpxml(xml_path, base_edl, out_path)
    imported = imported_payload(out_path)

    assert report["status"] == "pass"
    assert imported["timelines"][0]["ranges"][0]["source_start"] == 0.166667
    assert imported["timelines"][0]["ranges"][0]["source_end"] == 1.0
    assert report["timelines"][0]["trimmed_ranges"][0]["id"] == "t001-r0001"


def test_import_fcpxml_reads_resolve_time_map_as_speed(tmp_path: Path) -> None:
    base_edl = write_base_edl(tmp_path)
    xml_path = exported_xml(base_edl)
    tree = ET.parse(xml_path)
    first_clip = tree.getroot().find("./library/event/project/sequence/spine/asset-clip")
    assert first_clip is not None
    first_clip.attrib["duration"] = "1s"
    time_map = ET.SubElement(first_clip, "timeMap", {"frameSampling": "floor"})
    ET.SubElement(time_map, "timept", {"time": "0s", "interp": "linear", "value": "0s"})
    ET.SubElement(time_map, "timept", {"time": "1s", "interp": "linear", "value": "2s"})
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    out_path = base_edl.parent / "edl.imported.json"

    report = import_fcpxml(xml_path, base_edl, out_path)
    imported = imported_payload(out_path)
    first_range = imported["timelines"][0]["ranges"][0]

    assert report["status"] == "pass"
    assert first_range["source_start"] == 0.0
    assert first_range["source_end"] == 2.0
    assert first_range["speed"] == 2.0
    assert first_range["record_duration"] == 1.0
    assert report["timelines"][0]["retimed_ranges"][0]["id"] == "t001-r0001"


def test_import_fcpxml_reports_reordered_ranges(tmp_path: Path) -> None:
    base_edl = write_base_edl(tmp_path)
    xml_path = exported_xml(base_edl)
    tree = ET.parse(xml_path)
    spine = tree.getroot().find("./library/event/project/sequence/spine")
    assert spine is not None
    clips = list(spine)
    reordered = [copy.deepcopy(clips[1]), copy.deepcopy(clips[0])]
    reordered[0].attrib["offset"] = "0s"
    reordered[1].attrib["offset"] = "1s"
    spine.clear()
    spine.extend(reordered)
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    out_path = base_edl.parent / "edl.imported.json"

    report = import_fcpxml(xml_path, base_edl, out_path)
    imported = imported_payload(out_path)

    assert report["status"] == "pass"
    assert [item["id"] for item in imported["timelines"][0]["ranges"]] == ["t001-r0002", "t001-r0001"]
    assert report["timelines"][0]["reordered_ranges"] == ["t001-r0002", "t001-r0001"]


def test_import_fcpxml_strict_fails_for_unknown_source(tmp_path: Path) -> None:
    base_edl = write_base_edl(tmp_path)
    xml_path = exported_xml(base_edl)
    tree = ET.parse(xml_path)
    asset = tree.getroot().find("./resources/asset")
    assert asset is not None
    media_rep = asset.find("media-rep")
    assert media_rep is not None
    media_rep.attrib["src"] = (tmp_path / "raw" / "other.mp4").resolve().as_uri()
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    out_path = base_edl.parent / "edl.imported.json"

    report = import_fcpxml(xml_path, base_edl, out_path, strict=True)

    assert report["status"] == "failed"
    assert "unknown source" in report["errors"][0]
