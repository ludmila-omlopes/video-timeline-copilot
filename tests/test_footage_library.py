from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from helpers import contact_sheet
from helpers.common import clock, fold_text, is_image_path, parse_clock
from helpers.contact_sheet import (
    build_sheet,
    build_sheets_for_video,
    default_sheet_path,
    frame_filter,
    segment_ranges,
    sheet_layout,
    sheet_times,
    sheets_for_source,
    time_label,
)
from helpers.inventory import file_fingerprint, iter_source_images
from helpers.pack_transcripts import build_packed_lines
from helpers.project_context import glossary_prompt, load_context, update_context
from helpers.status import build_status, pending, summary_overview, write_library_index


def write_index(edit_dir: Path, media: list[dict], images: list[dict] | None = None) -> None:
    edit_dir.mkdir(parents=True, exist_ok=True)
    (edit_dir / "media_index.json").write_text(
        json.dumps({"root": str(edit_dir.parent), "media": media, "images": images or []}), encoding="utf-8"
    )


def test_fold_text_ignores_case_accents_and_punctuation() -> None:
    assert fold_text("  Olá, Você!  ") == "ola voce"
    assert fold_text("second-floor") == "second floor"


def test_parse_clock_accepts_seconds_and_clock_forms() -> None:
    assert parse_clock("12.5") == 12.5
    assert parse_clock("02:30") == 150.0
    assert parse_clock("01:00:05") == 3605.0
    assert clock(3605.9) == "01:00:05"
    with pytest.raises(ValueError):
        parse_clock("1:2:3:4")


def test_is_image_path_is_case_insensitive() -> None:
    assert is_image_path("raw/Title.PNG")
    assert not is_image_path("raw/clip.mp4")


def test_inventory_lists_images_and_fingerprints(tmp_path: Path) -> None:
    image = tmp_path / "raw" / "card.jpg"
    image.parent.mkdir()
    image.write_bytes(b"12345")
    (tmp_path / "edit" / "qa").mkdir(parents=True)
    (tmp_path / "edit" / "qa" / "contact_sheet.jpg").write_bytes(b"x")

    assert iter_source_images(tmp_path, tmp_path / "edit") == [image]
    assert file_fingerprint(image)["size"] == 5
    assert file_fingerprint(tmp_path / "missing.png") == {}


def test_sheet_layout_uses_fewer_tiles_for_short_ranges() -> None:
    assert sheet_layout(120.0) == (16, 4, 4)
    assert sheet_layout(8.0) == (8, 4, 2)


def test_sheet_times_sample_the_middle_of_each_slice() -> None:
    assert sheet_times(0.0, 8.0, 4) == [1.0, 3.0, 5.0, 7.0]
    with pytest.raises(ValueError):
        sheet_times(5.0, 5.0, 4)


def test_time_label_adds_tenths_only_for_short_ranges() -> None:
    assert time_label(30.5, 8.0) == "00:00:30.5"
    assert time_label(59.96, 8.0) == "00:01:00.0"
    assert time_label(125.4, 600.0) == "00:02:05"


def test_segment_ranges_only_split_long_sources() -> None:
    assert segment_ranges(300.0, 600.0) == []
    assert segment_ranges(1500.0, 600.0) == [(0.0, 600.0), (600.0, 1200.0), (1200.0, 1500.0)]


def test_default_sheet_path_names_whole_clip_and_ranges(tmp_path: Path) -> None:
    video = tmp_path / "raw" / "My Clip.mp4"
    assert default_sheet_path(tmp_path / "edit", video, None, None).name == "My_Clip_full.jpg"
    assert default_sheet_path(tmp_path / "edit", video, 120.0, 150.0).name == "My_Clip_00-02-00_to_00-02-30.jpg"


def test_frame_filter_escapes_timestamp_colons() -> None:
    assert frame_filter(480, None) == "scale=480:-2"
    assert "text='00\\:01\\:05'" in frame_filter(480, "00:01:05")


def test_build_sheet_writes_sidecar_and_falls_back_without_drawtext(tmp_path: Path, monkeypatch) -> None:
    grabbed = []

    def fake_grab(video: Path, seconds: float, out_path: Path, vf: str) -> None:
        grabbed.append(vf)
        if "drawtext" in vf:
            raise subprocess.CalledProcessError(1, "ffmpeg")
        out_path.write_bytes(b"jpg")

    def fake_tile(frames_dir: Path, out_path: Path, columns: int, rows: int) -> None:
        assert len(list(frames_dir.glob("tile_*.jpg"))) == columns * rows
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"sheet")

    monkeypatch.setattr(contact_sheet, "grab_frame", fake_grab)
    monkeypatch.setattr(contact_sheet, "tile_frames", fake_tile)

    out = tmp_path / "edit" / "contact_sheets" / "clip_full.jpg"
    record = build_sheet(tmp_path / "clip.mp4", out, start=0.0, end=160.0)

    assert out.exists()
    assert record["timestamps_burned_in"] is False
    assert [frame["time"] for frame in record["frames"]][:2] == [5.0, 15.0]
    assert json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))["rows"] == 4
    # Only the first frame is tried with drawtext; the rest go straight to the plain filter.
    assert sum("drawtext" in vf for vf in grabbed) == 1


def test_build_sheets_for_video_adds_window_sheets_and_skips_existing(tmp_path: Path, monkeypatch) -> None:
    built = []

    def fake_build(video: Path, out_path: Path, **kwargs) -> dict:
        built.append((out_path.name, kwargs["start"], kwargs["end"]))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"sheet")
        return {}

    monkeypatch.setattr(contact_sheet, "media_duration", lambda path: 1500.0)
    monkeypatch.setattr(contact_sheet, "build_sheet", fake_build)
    edit_dir = tmp_path / "edit"
    video = tmp_path / "raw" / "stream.mp4"

    sheets = build_sheets_for_video(video, edit_dir)

    assert len(sheets) == 4
    assert [name for name, _, _ in built] == [
        "stream_full.jpg",
        "stream_00-00-00_to_00-10-00.jpg",
        "stream_00-10-00_to_00-20-00.jpg",
        "stream_00-20-00_to_00-25-00.jpg",
    ]
    assert sheets_for_source(edit_dir, "stream")[0].name == "stream_full.jpg"

    built.clear()
    build_sheets_for_video(video, edit_dir)
    assert built == []

    with pytest.raises(ValueError, match="past the end"):
        build_sheets_for_video(video, edit_dir, start=10.0, end=2000.0)


def test_context_glossary_merges_heard_forms_and_builds_prompt(tmp_path: Path) -> None:
    edit_dir = tmp_path / "edit"
    update_context(edit_dir, add_terms=["Hollow Knight=Holo Night"], set_values=["language=pt", "editor=resolve"])
    context = update_context(edit_dir, add_terms=["hollow knight=Hollow Night|holo night", "Hornet"], add_notes=["Keep boss fights whole"])

    assert context["glossary"][0] == {"term": "Hollow Knight", "heard_as": ["Holo Night", "Hollow Night"]}
    assert context["language"] == "pt"
    assert context["notes"][0]["text"] == "Keep boss fights whole"
    assert glossary_prompt(context) == "Glossary: Hollow Knight, Hornet."
    assert glossary_prompt(load_context(tmp_path / "other")) is None

    assert update_context(edit_dir, remove_terms=["HORNET"])["glossary"][-1]["term"] == "Hollow Knight"
    with pytest.raises(ValueError, match="editor must be one of"):
        update_context(edit_dir, set_values=["editor=avid"])
    with pytest.raises(ValueError, match="unknown context key"):
        update_context(edit_dir, set_values=["colour=blue"])


def test_status_reports_missing_artifacts_and_readiness(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "a.mp4").write_bytes(b"")
    (raw / "b.mp4").write_bytes(b"")
    (raw / "card.png").write_bytes(b"")
    edit_dir = tmp_path / "edit"
    write_index(
        edit_dir,
        [
            {"path": str(raw / "a.mp4"), "duration": 60.0, "width": 1920, "height": 1080},
            {"path": str(raw / "b.mp4"), "duration": 30.0, "width": 1920, "height": 1080},
        ],
        [{"path": str(raw / "card.png"), "width": 1920, "height": 1080}],
    )
    (edit_dir / "transcripts").mkdir()
    (edit_dir / "transcripts" / "a.json").write_text("{}", encoding="utf-8")
    (edit_dir / "contact_sheets").mkdir()
    (edit_dir / "contact_sheets" / "a_full.jpg").write_bytes(b"")
    (edit_dir / "summaries").mkdir()
    (edit_dir / "summaries" / "a.md").write_text(
        "# a.mp4\n\n## Overview\nA boss fight that ends in a win.\n\n## Visuals\n- Arena\n", encoding="utf-8"
    )
    (edit_dir / "summaries" / "b.md").write_text("# b.mp4\nstub\n", encoding="utf-8")

    status = build_status(edit_dir)

    by_name = {source["name"]: source for source in status["sources"]}
    assert by_name["a.mp4"]["missing"] == ["analysis"]
    assert by_name["b.mp4"]["missing"] == ["transcript", "analysis", "contact_sheet", "summary"]
    assert by_name["card.png"]["missing"] == ["summary"]
    assert status["ready"] is False
    assert [item["name"] for item in status["not_ready"]] == ["b.mp4", "card.png"]
    assert pending(status, "summary") == [str(raw / "b.mp4"), str(raw / "card.png")]
    assert status["total_duration"] == 90.0

    update_context(edit_dir, set_values=["footage_summary=Two sessions of a platformer"], add_terms=["Hornet"])
    index_text = write_library_index(status, edit_dir).read_text(encoding="utf-8")
    assert "Footage: Two sessions of a platformer" in index_text
    assert "Names and terms: Hornet" in index_text
    assert "A boss fight that ends in a win." in index_text
    assert "Missing: transcript, analysis, contact_sheet, summary" in index_text


def test_status_is_ready_when_every_source_is_analyzed_and_warns_on_duplicate_names(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    (raw / "day1").mkdir(parents=True)
    (raw / "day2").mkdir()
    (raw / "day1" / "clip.mp4").write_bytes(b"")
    edit_dir = tmp_path / "edit"
    write_index(edit_dir, [{"path": str(raw / "day1" / "clip.mp4"), "duration": 10.0}])
    for folder, name, body in (
        ("transcripts", "clip.json", "{}"),
        ("contact_sheets", "clip_full.jpg", ""),
        ("summaries", "clip.md", "## Overview\nx\n## Visuals\n- y\n"),
    ):
        (edit_dir / folder).mkdir()
        (edit_dir / folder / name).write_text(body, encoding="utf-8")

    assert build_status(edit_dir)["ready"] is True

    (raw / "day2" / "clip.mp4").write_bytes(b"")
    write_index(
        edit_dir,
        [{"path": str(raw / "day1" / "clip.mp4"), "duration": 10.0}, {"path": str(raw / "day2" / "clip.mp4"), "duration": 10.0}],
    )
    status = build_status(edit_dir)
    assert status["ready"] is False
    assert any("share the name 'clip'" in warning for warning in status["warnings"])


def test_summary_overview_stops_at_the_next_heading(tmp_path: Path) -> None:
    path = tmp_path / "s.md"
    path.write_text("# x\n\n## Overview\nFirst line.\nSecond line.\n\n## Visuals\n- no\n", encoding="utf-8")
    assert summary_overview(path) == "First line. Second line."
    assert summary_overview(tmp_path / "none.md") == ""


def test_pack_transcripts_includes_summary_sheets_and_source_filter(tmp_path: Path) -> None:
    edit_dir = tmp_path / "edit"
    (edit_dir / "transcripts").mkdir(parents=True)
    for stem in ("My Clip", "other"):
        (edit_dir / "transcripts" / f"{stem}.json").write_text(
            json.dumps({"duration": 2.0, "words": [{"start": 0.0, "end": 0.4, "text": " Hello"}]}), encoding="utf-8"
        )
    (edit_dir / "summaries").mkdir()
    (edit_dir / "summaries" / "My_Clip.md").write_text("# My Clip.mp4\n\n## Overview\nA tour of the base.\n", encoding="utf-8")
    (edit_dir / "contact_sheets").mkdir()
    (edit_dir / "contact_sheets" / "My_Clip_full.jpg").write_bytes(b"")
    (edit_dir / "video_analysis").mkdir()
    (edit_dir / "video_analysis" / "My_Clip.json").write_text(
        json.dumps({"scene_changes": [{"time": 1.0}], "sampled_frames": []}), encoding="utf-8"
    )

    lines = build_packed_lines(
        edit_dir,
        silence_threshold=0.5,
        repeat_window=45.0,
        similarity_threshold=0.82,
        min_words=3,
        sources=["My Clip.mp4"],
    )
    text = "\n".join(lines)

    assert "## My Clip " in text and "## other" not in text
    assert "#### Overview" in text and "A tour of the base." in text
    assert "contact_sheets/My_Clip_full.jpg" in text
    # The analysis file is found even though its name was made filesystem-safe.
    assert "Scene-change signals: 001.00" in text

    with pytest.raises(FileNotFoundError):
        build_packed_lines(
            edit_dir, silence_threshold=0.5, repeat_window=45.0, similarity_threshold=0.82, min_words=3, sources=["nope"]
        )
