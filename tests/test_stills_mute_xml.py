from __future__ import annotations

from fractions import Fraction
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from helpers import export_srt
from helpers.cli import COMMANDS, tool_version
from helpers.export_fcpxml import build_fcpxml, fcpxml_integrity_issues, frame_rate_mismatches, write_fcpxml
from helpers.export_xml import audio_channels, build_xml, default_xml_path, rate_parts, source_rate, write_xml
from helpers.guide import guide_summary, guide_topics, read_guide
from helpers.import_fcpxml import import_fcpxml
from helpers.qa_preview import qa_preview
from helpers.render_preview import _segment_args
from helpers.validate_edl import validate


def write_project(tmp_path: Path, ranges: list[dict], *, fps: float = 30, media: list[dict] | None = None) -> Path:
    raw = tmp_path / "raw"
    edit_dir = tmp_path / "edit"
    raw.mkdir()
    edit_dir.mkdir()
    (raw / "clip.mp4").write_bytes(b"")
    (raw / "title.png").write_bytes(b"")
    edl = {
        "version": 1,
        "project_name": "Cut",
        "fps": fps,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": "raw/clip.mp4", "T001": "raw/title.png"},
                "ranges": ranges,
                "markers": True,
            }
        ],
    }
    (edit_dir / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    index = {
        "root": str(tmp_path),
        "media": media
        if media is not None
        else [
            {
                "path": str(raw / "clip.mp4"),
                "duration": 60.0,
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30/1",
                "audio_channels": 2,
                "audio_rate": 48000,
            }
        ],
        "images": [{"path": str(raw / "title.png"), "width": 1920, "height": 1080}],
    }
    (edit_dir / "media_index.json").write_text(json.dumps(index), encoding="utf-8")
    return edit_dir / "edl.json"


STILL_AND_MUTE = [
    {"source": "T001", "source_start": 0, "source_end": 2.0, "record_start": 0, "beat": "TITLE"},
    {"source": "A001", "source_start": 10.0, "source_end": 14.0, "record_start": 2.0, "beat": "HOOK", "reason": "Best line"},
    {"source": "A001", "source_start": 30.0, "source_end": 33.0, "record_start": 6.0, "mute": True},
]


def test_validate_accepts_stills_and_mute_and_rejects_misuse(tmp_path: Path) -> None:
    assert validate(write_project(tmp_path, STILL_AND_MUTE)) == []

    (tmp_path / "bad").mkdir()
    bad = write_project(
        tmp_path / "bad",
        [
            {"source": "T001", "source_start": 0, "source_end": 2.0, "record_start": 0, "speed": 2.0},
            {"source": "A001", "source_start": 0, "source_end": 2.0, "record_start": 1.0, "mute": "yes"},
        ],
    )
    errors = validate(bad)
    assert any("still image; speed does not apply" in error for error in errors)
    assert any("mute must be true or false" in error for error in errors)


def test_fcpxml_writes_stills_as_video_elements_and_mutes_with_src_enable(tmp_path: Path) -> None:
    edl_path = write_project(tmp_path, STILL_AND_MUTE)

    root = build_fcpxml(edl_path).getroot()

    spine = root.find("./library/event/project/sequence/spine")
    assert [child.tag for child in spine] == ["video", "asset-clip", "asset-clip"]
    still, hook, muted = list(spine)
    assert (still.attrib["offset"], still.attrib["start"], still.attrib["duration"]) == ("0s", "0s", "2s")
    assert still.find("adjust-conform").attrib["type"] == "fit"
    assert "srcEnable" not in hook.attrib
    assert muted.attrib["srcEnable"] == "video"

    assets = {asset.attrib["name"]: asset for asset in root.findall("./resources/asset")}
    assert assets["title"].attrib["duration"] == "0s" and "hasAudio" not in assets["title"].attrib
    still_format = root.find(f"./resources/format[@id='{assets['title'].attrib['format']}']")
    assert still_format.attrib["name"] == "FFVideoFormatRateUndefined" and "frameDuration" not in still_format.attrib
    ids = [item.attrib["id"] for item in root.findall("./resources/format")]
    assert len(ids) == len(set(ids))

    out = write_fcpxml(edl_path, edl_path.parent / "Cut.fcpxml")
    assert fcpxml_integrity_issues(edl_path, out) == []


def test_fcpxml_with_still_and_mute_round_trips_through_import(tmp_path: Path) -> None:
    edl_path = write_project(tmp_path, STILL_AND_MUTE)
    xml_path = write_fcpxml(edl_path, edl_path.parent / "Cut.fcpxml")
    out_path = edl_path.parent / "edl.imported.json"

    report = import_fcpxml(xml_path, edl_path, out_path)

    assert report["status"] == "pass"
    ranges = json.loads(out_path.read_text(encoding="utf-8"))["timelines"][0]["ranges"]
    assert [(item["source"], item["source_start"], item["source_end"], item["record_start"]) for item in ranges] == [
        ("T001", 0.0, 2.0, 0.0),
        ("A001", 10.0, 14.0, 2.0),
        ("A001", 30.0, 33.0, 6.0),
    ]
    assert [bool(item.get("mute")) for item in ranges] == [False, False, True]
    assert validate(out_path) == []


def test_frame_rate_mismatches_flags_only_differing_video_sources(tmp_path: Path) -> None:
    (tmp_path / "same").mkdir()
    assert frame_rate_mismatches(write_project(tmp_path / "same", STILL_AND_MUTE)) == []
    (tmp_path / "mixed").mkdir()
    mixed = write_project(
        tmp_path / "mixed",
        STILL_AND_MUTE,
        fps=24,
        media=[{"path": str(tmp_path / "mixed" / "raw" / "clip.mp4"), "duration": 60.0, "avg_frame_rate": "24000/1001"}],
    )
    assert frame_rate_mismatches(mixed) == ["clip.mp4 is 23.976 fps on a 24.000 fps timeline"]


def test_xml_rate_helpers() -> None:
    assert rate_parts(Fraction(30000, 1001)) == (30, True)
    assert rate_parts(Fraction(24, 1)) == (24, False)
    assert source_rate({"avg_frame_rate": "60000/1001"}, Fraction(30)) == Fraction(60000, 1001)
    assert source_rate({"avg_frame_rate": "0/0"}, Fraction(30)) == Fraction(30)
    assert source_rate(None, Fraction(25)) == Fraction(25)
    assert audio_channels({"audio_channels": 6}) == 2
    assert audio_channels({"audio_channels": 0}) == 0
    assert audio_channels(None) == 2


def test_xml_export_lays_out_cuts_links_stills_mute_and_markers(tmp_path: Path) -> None:
    edl_path = write_project(tmp_path, STILL_AND_MUTE)

    tree, notes = build_xml(edl_path)
    root = tree.getroot()

    assert notes == []
    sequence = root.find("./project/children/sequence")
    assert sequence.findtext("duration") == "270"
    video_clips = sequence.findall("./media/video/track/clipitem")
    assert [(c.findtext("start"), c.findtext("end"), c.findtext("in"), c.findtext("out")) for c in video_clips] == [
        ("0", "60", "0", "60"),
        ("60", "180", "300", "420"),
        ("180", "270", "900", "990"),
    ]
    assert video_clips[0].findtext("stillframe") == "TRUE"
    assert video_clips[1].findtext("./comments/mastercomment1") == "HOOK"

    audio_tracks = sequence.findall("./media/audio/track")
    # The still and the muted clip contribute no audio; the hook has both channels.
    assert [len(track.findall("clipitem")) for track in audio_tracks] == [1, 1]
    left = audio_tracks[0].find("clipitem")
    assert left.findtext("./sourcetrack/trackindex") == "1"
    assert (left.findtext("start"), left.findtext("in")) == ("60", "300")
    linked = {link.findtext("linkclipref") for link in video_clips[1].findall("link")}
    assert linked == {video_clips[1].attrib["id"], left.attrib["id"], audio_tracks[1].find("clipitem").attrib["id"]}
    assert video_clips[2].findall("link") == []

    files = root.findall(".//file")
    full = [item for item in files if item.find("pathurl") is not None]
    assert len(full) == 2 and len(files) > 2
    assert all(item.findtext("pathurl").startswith("file://localhost/") for item in full)
    assert [marker.findtext("in") for marker in sequence.findall("marker")] == ["0", "60", "180"]

    out, _ = write_xml(edl_path, default_xml_path(edl_path))
    text = out.read_text(encoding="utf-8")
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">')
    ET.fromstring(text.split("<!DOCTYPE xmeml>\n", 1)[1])


def test_xml_export_uses_each_files_own_rate_for_source_frames(tmp_path: Path) -> None:
    edl_path = write_project(
        tmp_path,
        [{"source": "A001", "source_start": 10.0, "source_end": 12.0, "record_start": 0}],
        fps=30,
        media=[{"path": str(tmp_path / "raw" / "clip.mp4"), "duration": 60.0, "avg_frame_rate": "60/1", "audio_channels": 1}],
    )

    root = build_xml(edl_path)[0].getroot()

    clip = root.find(".//video/track/clipitem")
    assert (clip.findtext("start"), clip.findtext("end")) == ("0", "60")
    assert (clip.findtext("in"), clip.findtext("out")) == ("600", "720")
    assert clip.findtext("./rate/timebase") == "60"
    assert [len(track.findall("clipitem")) for track in root.findall(".//audio/track")] == [1, 0]


def test_xml_export_warns_about_framing_and_refuses_retimes(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    framed = write_project(
        tmp_path / "a",
        [{"source": "A001", "source_start": 0, "source_end": 2.0, "record_start": 0, "transform": {"zoom": 1.2}}],
    )
    assert build_xml(framed)[1] == ["Main: range 1: zoom/pan/tilt is not carried; reapply the framing in the editor"]

    (tmp_path / "b").mkdir()
    retimed = write_project(
        tmp_path / "b", [{"source": "A001", "source_start": 0, "source_end": 4.0, "record_start": 0, "speed": 2.0}]
    )
    with pytest.raises(ValueError, match="does not support retimed ranges"):
        build_xml(retimed)


def test_preview_holds_stills_with_silence_and_forces_stereo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("helpers.render_preview.find_ffmpeg", lambda: "ffmpeg")
    args = _segment_args(tmp_path / "title.png", 0.0, 2.0, 2.0, 1920, 1080, 30.0, tmp_path / "out.mp4", {"video"}, None, True)

    assert args[args.index("-loop") + 1] == "1"
    assert "-ss" not in args
    assert any(str(value).startswith("anullsrc=") for value in args)
    assert args[args.index("-ac") + 1] == "2" and args[args.index("-ar") + 1] == "48000"

    muted = _segment_args(tmp_path / "clip.mp4", 5.0, 2.0, 2.0, 1920, 1080, 30.0, tmp_path / "out.mp4", {"video"})
    assert muted[muted.index("-map") + 3] == "1:a:0"


def test_preview_qa_treats_stills_and_muted_clips_as_silent_by_design(tmp_path: Path, monkeypatch) -> None:
    edl_path = write_project(tmp_path, STILL_AND_MUTE)
    probed = []

    def fake_stream_types(path: Path) -> set[str]:
        probed.append(path.name)
        return {"video", "audio"}

    monkeypatch.setattr("helpers.qa_preview.stream_types", fake_stream_types)
    monkeypatch.setattr("helpers.qa_preview.media_duration", lambda path: None)

    report = qa_preview(edl_path)

    assert probed == ["clip.mp4"]
    assert report["video_only_regions"] == []
    assert [region["reason"] for region in report["silent_by_design_regions"]] == ["still image", "muted"]
    assert report["checks"]["video_only_regions_found"] is False


def test_srt_skips_muted_ranges(tmp_path: Path) -> None:
    edl_path = write_project(
        tmp_path,
        [
            {"source": "A001", "source_start": 0.0, "source_end": 1.0, "record_start": 0.0, "mute": True},
            {"source": "A001", "source_start": 2.0, "source_end": 3.0, "record_start": 1.0},
        ],
    )
    edit_dir = edl_path.parent
    (edit_dir / "transcripts").mkdir()
    (edit_dir / "transcripts" / "clip.json").write_text(
        json.dumps({"words": [{"start": 0.1, "end": 0.5, "text": "Muted"}, {"start": 2.1, "end": 2.5, "text": "Heard"}]}),
        encoding="utf-8",
    )
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    out = edit_dir / "subtitles" / "main.srt"
    out.parent.mkdir()

    export_srt.build_srt_for_timeline(edl, edl["timelines"][0], edit_dir, out)

    text = out.read_text(encoding="utf-8")
    assert "Heard" in text and "Muted" not in text


def test_guides_ship_with_the_package_and_cover_every_routed_topic() -> None:
    topics = guide_topics()
    for name in ("session", "footage", "cuts", "edl", "cut-craft", "shorts", "handoff", "resolve-console", "resolve-talking-head", "fcpxml-audio"):
        assert name in topics, name
        assert guide_summary(topics[name])
    assert read_guide("Footage.md").startswith("# Knowing The Footage")
    with pytest.raises(KeyError, match="unknown guide"):
        read_guide("nope")


def test_skill_routes_only_to_guides_and_commands_that_exist() -> None:
    repo = Path(__file__).resolve().parents[1]
    skill = (repo / "SKILL.md").read_text(encoding="utf-8")
    topics = guide_topics()
    table_guides = set(re.findall(r"^\| `([a-z-]+)`", skill, flags=re.MULTILINE))
    assert table_guides and table_guides <= set(topics)

    documents = [skill, *(path.read_text(encoding="utf-8") for path in topics.values())]
    used = set()
    for document in documents:
        used.update(re.findall(r"`vtc ([a-z][a-z-]+)", document))
        used.update(re.findall(r"^\s*vtc ([a-z][a-z-]+)", document, flags=re.MULTILINE))
    assert used - set(COMMANDS) == set()
    for document in documents:
        for name in re.findall(r"the `([a-z-]+)` guide", document):
            assert name in topics, name
        assert "docs/" not in document


def test_new_commands_are_registered_and_version_is_reported() -> None:
    for name in ("guide", "status", "context", "verify-media", "contact-sheet", "fix-transcript", "dialogue", "find-phrase", "export-xml", "backup"):
        assert name in COMMANDS
        __import__(COMMANDS[name][0], fromlist=["main"]).main
    assert tool_version()
