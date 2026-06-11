from __future__ import annotations

import json
from pathlib import Path

from helpers.export_srt import build_srt_for_timeline, words_in_range


def write_transcript(edit_dir: Path, stem: str = "clip") -> None:
    transcript_dir = edit_dir / "transcripts"
    transcript_dir.mkdir()
    (transcript_dir / f"{stem}.json").write_text(
        json.dumps(
            {
                "words": [
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


def test_words_in_range_includes_overlaps_and_excludes_fully_outside() -> None:
    words = [
        {"start": 0.0, "end": 0.5, "text": "before"},
        {"start": 0.5, "end": 1.0, "text": "inside"},
        {"start": 1.0, "end": 1.5, "text": "after"},
    ]

    assert words_in_range(words, 0.5, 1.0) == [words[1]]
