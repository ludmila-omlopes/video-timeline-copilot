from __future__ import annotations

import json
import sys
from pathlib import Path

from helpers import export_srt
from helpers.export_srt import build_srt_for_timeline, words_in_range


def write_transcript(edit_dir: Path, stem: str = "clip", words: list[dict] | None = None) -> None:
    transcript_dir = edit_dir / "transcripts"
    transcript_dir.mkdir(exist_ok=True)
    (transcript_dir / f"{stem}.json").write_text(
        json.dumps(
            {
                "words": words
                or [
                    {"start": 0.0, "end": 0.2, "text": "Hello"},
                    {"start": 0.3, "end": 0.5, "text": "world"},
                    {"start": 0.6, "end": 0.8, "text": "again."},
                ]
            }
        ),
        encoding="utf-8",
    )


def test_build_srt_for_timeline_writes_expected_words_from_zero_record_start(tmp_path: Path) -> None:
    edit_dir = tmp_path / "edit"
    edit_dir.mkdir()
    write_transcript(edit_dir)
    timeline = {
        "sources": {"A001": "raw/clip.mp4"},
        "ranges": [{"source": "A001", "source_start": 0.0, "source_end": 1.0, "record_start": 0.0}],
    }
    out_path = edit_dir / "subtitles" / "main.srt"

    build_srt_for_timeline({}, timeline, edit_dir, out_path)

    text = out_path.read_text(encoding="utf-8")
    assert "00:00:00,000 -->" in text
    assert "Hello world again." in text


def test_build_srt_for_timeline_writes_empty_file_without_transcript(tmp_path: Path) -> None:
    edit_dir = tmp_path / "edit"
    edit_dir.mkdir()
    timeline = {
        "sources": {"A001": "raw/missing.mp4"},
        "ranges": [{"source": "A001", "source_start": 0.0, "source_end": 1.0, "record_start": 0.0}],
    }
    out_path = edit_dir / "subtitles" / "main.srt"

    build_srt_for_timeline({}, timeline, edit_dir, out_path)

    assert out_path.read_text(encoding="utf-8") == ""


def test_build_srt_for_timeline_honors_record_gaps(tmp_path: Path) -> None:
    edit_dir = tmp_path / "edit"
    edit_dir.mkdir()
    write_transcript(
        edit_dir,
        words=[
            {"start": 0.5, "end": 1.0, "text": "first."},
            {"start": 10.5, "end": 11.0, "text": "second."},
        ],
    )
    timeline = {
        "sources": {"A001": "raw/clip.mp4"},
        "ranges": [
            {"source": "A001", "source_start": 0.0, "source_end": 2.0, "record_start": 0.0},
            {"source": "A001", "source_start": 10.0, "source_end": 12.0, "record_start": 5.0},
        ],
    }
    out_path = edit_dir / "subtitles" / "main.srt"

    build_srt_for_timeline({}, timeline, edit_dir, out_path)

    text = out_path.read_text(encoding="utf-8")
    assert "00:00:05,500 -->" in text
    assert "00:00:02,500 -->" not in text


def test_build_srt_for_timeline_defaults_missing_record_start_to_cursor(tmp_path: Path) -> None:
    edit_dir = tmp_path / "edit"
    edit_dir.mkdir()
    write_transcript(
        edit_dir,
        words=[
            {"start": 0.5, "end": 1.0, "text": "first."},
            {"start": 10.5, "end": 11.0, "text": "second."},
        ],
    )
    timeline = {
        "sources": {"A001": "raw/clip.mp4"},
        "ranges": [
            {"source": "A001", "source_start": 0.0, "source_end": 2.0, "record_start": 0.0},
            {"source": "A001", "source_start": 10.0, "source_end": 12.0},
        ],
    }
    out_path = edit_dir / "subtitles" / "main.srt"

    build_srt_for_timeline({}, timeline, edit_dir, out_path)

    assert "00:00:02,500 -->" in out_path.read_text(encoding="utf-8")


def test_build_srt_for_timeline_missing_transcript_still_advances_cursor(tmp_path: Path) -> None:
    edit_dir = tmp_path / "edit"
    edit_dir.mkdir()
    write_transcript(edit_dir, stem="clip_b", words=[{"start": 0.5, "end": 1.0, "text": "found."}])
    timeline = {
        "sources": {"A001": "raw/missing.mp4", "B001": "raw/clip_b.mp4"},
        "ranges": [
            {"source": "A001", "source_start": 0.0, "source_end": 2.0, "record_start": 0.0},
            {"source": "B001", "source_start": 0.0, "source_end": 2.0, "record_start": 4.0},
        ],
    }
    out_path = edit_dir / "subtitles" / "main.srt"

    build_srt_for_timeline({}, timeline, edit_dir, out_path)

    assert "00:00:04,500 -->" in out_path.read_text(encoding="utf-8")


def test_main_sanitizes_default_subtitle_filename(tmp_path: Path, monkeypatch) -> None:
    edit_dir = tmp_path / "edit"
    edit_dir.mkdir()
    edl_path = edit_dir / "timeline.json"
    edl_path.write_text(
        json.dumps({"timelines": [{"name": "..\\..\\evil", "sources": {}, "ranges": []}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["export_srt", str(edl_path)])

    export_srt.main()

    assert (edit_dir / "subtitles" / "evil.srt").exists()
    assert not (tmp_path / "evil.srt").exists()


def test_build_srt_for_timeline_caches_transcript_reads(tmp_path: Path, monkeypatch) -> None:
    edit_dir = tmp_path / "edit"
    edit_dir.mkdir()
    write_transcript(
        edit_dir,
        words=[
            {"start": 0.0, "end": 0.2, "text": "one."},
            {"start": 1.0, "end": 1.2, "text": "two."},
            {"start": 2.0, "end": 2.2, "text": "three."},
        ],
    )
    timeline = {
        "sources": {"A001": "raw/clip.mp4"},
        "ranges": [
            {"source": "A001", "source_start": 0.0, "source_end": 0.5, "record_start": 0.0},
            {"source": "A001", "source_start": 1.0, "source_end": 1.5, "record_start": 1.0},
            {"source": "A001", "source_start": 2.0, "source_end": 2.5, "record_start": 2.0},
        ],
    }
    out_path = edit_dir / "subtitles" / "main.srt"
    real_read_json = export_srt.read_json
    calls = 0

    def counting_read_json(path: Path) -> dict:
        nonlocal calls
        calls += 1
        return real_read_json(path)

    monkeypatch.setattr(export_srt, "read_json", counting_read_json)

    build_srt_for_timeline({}, timeline, edit_dir, out_path)

    assert calls == 1


def test_words_in_range_includes_overlaps_and_excludes_fully_outside() -> None:
    words = [
        {"start": 0.0, "end": 0.5, "text": "before"},
        {"start": 0.5, "end": 1.0, "text": "inside"},
        {"start": 1.0, "end": 1.5, "text": "after"},
    ]

    assert words_in_range(words, 0.5, 1.0) == [words[1]]
