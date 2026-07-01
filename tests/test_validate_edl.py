from __future__ import annotations

import json
from pathlib import Path

from helpers.validate_edl import cut_inside_word, cut_quality_warnings, transcript_gaps_in_range, validate


def write_edl(
    tmp_path: Path,
    *,
    source_path: str = "raw/clip.mp4",
    fps: float = 30.0,
    range_overrides: dict | None = None,
) -> Path:
    raw_dir = tmp_path / "raw"
    edit_dir = tmp_path / "edit"
    raw_dir.mkdir()
    edit_dir.mkdir()
    (raw_dir / "clip.mp4").write_bytes(b"")
    range_item = {
        "source": "A001",
        "source_start": 0.0,
        "source_end": 2.0,
        "record_start": 0.0,
        "track": 1,
        "beat": "INTRO",
        "quote": "hello",
        "reason": "keep",
    }
    if range_overrides:
        range_item.update(range_overrides)
    edl = {
        "version": 1,
        "project_name": "Example",
        "fps": fps,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": source_path},
                "ranges": [range_item],
            }
        ],
    }
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    return edl_path


def test_validate_accepts_minimal_valid_edl(tmp_path: Path) -> None:
    assert validate(write_edl(tmp_path)) == []


def test_validate_reports_missing_source_file(tmp_path: Path) -> None:
    errors = validate(write_edl(tmp_path, source_path="raw/missing.mp4"))

    assert any("does not exist" in error for error in errors)


def test_validate_reports_source_that_escapes_workspace(tmp_path: Path) -> None:
    errors = validate(write_edl(tmp_path, source_path="../outside.mp4"))

    assert any("escapes workspace" in error for error in errors)


def test_validate_reports_invalid_fps_range_and_media_type(tmp_path: Path) -> None:
    errors = validate(
        write_edl(
            tmp_path,
            fps=0,
            range_overrides={"source_start": 2.0, "source_end": 1.0, "media_type": "audio"},
        )
    )

    assert any("fps must be positive" in error for error in errors)
    assert any("source_end must be greater" in error for error in errors)
    assert any("media_type must be av" in error for error in errors)


def test_validate_reports_record_gap(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path)
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["timelines"][0]["ranges"].append(
        {"source": "A001", "source_start": 3.0, "source_end": 4.0, "record_start": 3.0}
    )
    edl_path.write_text(json.dumps(edl), encoding="utf-8")

    errors = validate(edl_path)

    assert any("record gap" in error for error in errors)


def test_validate_reports_record_overlap(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path)
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["timelines"][0]["ranges"].append(
        {"source": "A001", "source_start": 3.0, "source_end": 4.0, "record_start": 1.5}
    )
    edl_path.write_text(json.dumps(edl), encoding="utf-8")

    errors = validate(edl_path)

    assert any("overlaps the previous clip" in error for error in errors)


def test_validate_reports_half_second_clip(tmp_path: Path) -> None:
    errors = validate(write_edl(tmp_path, range_overrides={"source_start": 0.0, "source_end": 0.5}))

    assert any("shorter than the minimum" in error for error in errors)


def test_validate_uses_speed_for_record_timing(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path, range_overrides={"source_start": 0.0, "source_end": 4.0, "speed": 2.0})
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["timelines"][0]["ranges"].append(
        {"source": "A001", "source_start": 5.0, "source_end": 6.0, "record_start": 2.0}
    )
    edl_path.write_text(json.dumps(edl), encoding="utf-8")

    assert validate(edl_path) == []


def test_validate_rejects_non_positive_speed(tmp_path: Path) -> None:
    errors = validate(write_edl(tmp_path, range_overrides={"speed": 0}))

    assert any("speed must be greater than 0" in error for error in errors)


def test_cut_inside_word_detects_strict_interior_but_not_boundary_tolerance() -> None:
    words = [{"start": 1.0, "end": 2.0, "text": "hello"}]

    assert cut_inside_word(1.5, words) == words[0]
    assert cut_inside_word(1.01, words) is None
    assert cut_inside_word(1.99, words) is None


def test_transcript_gaps_in_range_reports_long_no_word_pause() -> None:
    words = [
        {"start": 0.5, "end": 1.0, "text": "before"},
        {"start": 4.0, "end": 4.5, "text": "after"},
    ]

    assert transcript_gaps_in_range(words, 0.0, 6.0, max_word_gap=0.8) == [
        {"start": 1.0, "end": 4.0, "duration": 3.0}
    ]


def test_cut_quality_warnings_report_long_transcript_gap_inside_kept_range(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path, range_overrides={"source_start": 0.0, "source_end": 6.0})
    transcript_dir = edl_path.parent / "transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "clip.json").write_text(
        json.dumps(
            {
                "words": [
                    {"start": 0.5, "end": 1.0, "text": "before"},
                    {"start": 4.0, "end": 4.5, "text": "after"},
                ]
            }
        ),
        encoding="utf-8",
    )

    warnings = cut_quality_warnings(edl_path)

    assert any("keeps a long 3.000s transcript gap" in warning for warning in warnings)


def test_cut_quality_warnings_report_partial_sentence_kept_at_word_boundary(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path, range_overrides={"source_start": 0.6, "source_end": 1.5})
    transcript_dir = edl_path.parent / "transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "clip.json").write_text(
        json.dumps(
            {
                "words": [
                    {"start": 0.0, "end": 0.2, "text": "Please"},
                    {"start": 0.3, "end": 0.5, "text": "do"},
                    {"start": 0.6, "end": 0.8, "text": "not"},
                    {"start": 0.9, "end": 1.2, "text": "cut"},
                    {"start": 1.3, "end": 1.5, "text": "phrases."},
                ]
            }
        ),
        encoding="utf-8",
    )

    warnings = cut_quality_warnings(edl_path)

    assert any("keeps only part of sentence" in warning for warning in warnings)
    assert any("omitted 2/5 words" in warning for warning in warnings)


def test_cut_quality_warnings_do_not_report_partial_sentence_when_all_words_are_kept(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path, range_overrides={"source_start": 0.0, "source_end": 0.5})
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["timelines"][0]["ranges"].append(
        {"source": "A001", "source_start": 1.0, "source_end": 1.5, "record_start": 0.5}
    )
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    transcript_dir = edl_path.parent / "transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "clip.json").write_text(
        json.dumps(
            {
                "words": [
                    {"start": 0.0, "end": 0.2, "text": "Please"},
                    {"start": 0.3, "end": 0.5, "text": "keep"},
                    {"start": 1.0, "end": 1.2, "text": "this"},
                    {"start": 1.3, "end": 1.5, "text": "sentence."},
                ]
            }
        ),
        encoding="utf-8",
    )

    warnings = cut_quality_warnings(edl_path)

    assert not any("keeps only part of sentence" in warning for warning in warnings)


def test_cut_quality_warnings_use_segments_when_word_punctuation_is_missing(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path, range_overrides={"source_start": 0.6, "source_end": 1.4})
    transcript_dir = edl_path.parent / "transcripts"
    transcript_dir.mkdir()
    words = [
        {"start": 0.0, "end": 0.2, "text": "please"},
        {"start": 0.3, "end": 0.5, "text": "keep"},
        {"start": 0.6, "end": 0.8, "text": "the"},
        {"start": 0.9, "end": 1.4, "text": "phrase"},
    ]
    (transcript_dir / "clip.json").write_text(
        json.dumps(
            {
                "segments": [{"start": 0.0, "end": 1.4, "text": "please keep the phrase", "words": words}],
                "words": words,
            }
        ),
        encoding="utf-8",
    )

    warnings = cut_quality_warnings(edl_path)

    assert any("keeps only part of segment" in warning for warning in warnings)
