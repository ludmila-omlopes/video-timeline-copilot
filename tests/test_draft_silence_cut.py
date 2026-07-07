from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from helpers.draft_silence_cut import (
    complement_silences,
    detect_silences,
    draft_ranges,
    merge_ranges,
    merge_ranges_preserving_word_gaps,
    normalize_negative_noise_arg,
    pad_ranges,
    parse_silencedetect_output,
    parse_frame_rate,
    split_ranges_on_word_gaps,
    snap_to_words,
)


def test_parse_frame_rate_handles_ratios_numbers_and_defaults() -> None:
    assert parse_frame_rate("30000/1001") == pytest.approx(29.97002997)
    assert parse_frame_rate("25") == 25.0
    assert parse_frame_rate(None) == 30.0
    assert parse_frame_rate("0/0") == 30.0


def test_parse_silencedetect_extracts_paired_silences() -> None:
    stderr = """
[silencedetect @ 0000021c4f4a1b40] silence_start: 1.30245
frame=  120 fps= 60 q=-0.0 size=N/A time=00:00:04.00 bitrate=N/A speed=  30x
[silencedetect @ 0000021c4f4a1b40] silence_end: 3.5045 | silence_duration: 2.20205
[silencedetect @ 0000021c4f4a1b40] silence_start: 6.0
[silencedetect @ 0000021c4f4a1b40] silence_end: 7.25 | silence_duration: 1.25
"""

    assert parse_silencedetect_output(stderr) == [
        {"start": 1.30245, "end": 3.5045, "duration": 2.20205},
        {"start": 6.0, "end": 7.25, "duration": 1.25},
    ]


def test_parse_silencedetect_ignores_unrelated_lines() -> None:
    stderr = """
Stream mapping:
  Stream #0:0 -> #0:0 (aac (native) -> pcm_s16le (native))
[silencedetect @ 0000021c4f4a1b40] silence_start: 0.75
frame=   42 fps=0.0 q=-0.0 size=N/A time=00:00:01.40 bitrate=N/A speed=2.78x
[silencedetect @ 0000021c4f4a1b40] silence_end: 2.0 | silence_duration: 1.25
video:0kB audio:512kB subtitle:0kB other streams:0kB global headers:0kB
"""

    assert parse_silencedetect_output(stderr) == [{"start": 0.75, "end": 2.0, "duration": 1.25}]


def test_parse_silencedetect_derives_start_from_duration_when_missing() -> None:
    stderr = "[silencedetect @ 0000021c4f4a1b40] silence_end: 5.0 | silence_duration: 2.0"

    assert parse_silencedetect_output(stderr) == [{"start": 3.0, "end": 5.0, "duration": 2.0}]


def test_parse_silencedetect_drops_trailing_unclosed_silence() -> None:
    stderr = """
[silencedetect @ 0000021c4f4a1b40] silence_start: 1.0
[silencedetect @ 0000021c4f4a1b40] silence_end: 2.0 | silence_duration: 1.0
[silencedetect @ 0000021c4f4a1b40] silence_start: 8.0
"""

    assert parse_silencedetect_output(stderr) == [{"start": 1.0, "end": 2.0, "duration": 1.0}]


def test_parse_silencedetect_returns_empty_for_empty_stderr() -> None:
    assert parse_silencedetect_output("") == []


def test_complement_silences_returns_full_range_without_silence() -> None:
    assert complement_silences([], 10.0) == [{"start": 0.0, "end": 10.0}]


def test_complement_silences_clamps_and_fills_gaps() -> None:
    silences = [
        {"start": -1.0, "end": 1.0},
        {"start": 3.0, "end": 4.0},
        {"start": 8.0, "end": 12.0},
    ]

    assert complement_silences(silences, 10.0) == [
        {"start": 1.0, "end": 3.0},
        {"start": 4.0, "end": 8.0},
    ]


def test_pad_ranges_clamps_and_drops_zero_length_input() -> None:
    ranges = [{"start": 0.1, "end": 0.4}, {"start": 1.0, "end": 1.0}, {"start": 9.8, "end": 10.0}]

    assert pad_ranges(ranges, padding=0.25, total_duration=10.0) == [
        {"start": 0.0, "end": 0.65},
        {"start": 9.55, "end": 10.0},
    ]


def test_merge_ranges_sorts_merges_close_ranges_and_drops_short_segments() -> None:
    ranges = [
        {"start": 3.0, "end": 3.2},
        {"start": 1.35, "end": 2.0},
        {"start": 0.0, "end": 1.0},
    ]

    assert merge_ranges(ranges, merge_gap=0.4, min_segment=0.5) == [{"start": 0.0, "end": 2.0}]


def test_merge_ranges_preserving_word_gaps_keeps_long_transcript_pause_cut() -> None:
    words = [
        {"start": 0.5, "end": 1.0, "text": "before"},
        {"start": 1.84, "end": 2.1, "text": "after"},
    ]

    assert merge_ranges_preserving_word_gaps(
        [{"start": 0.3, "end": 1.25}, {"start": 1.59, "end": 2.3}],
        words,
        merge_gap=0.35,
        min_segment=0.1,
        max_word_gap=0.8,
    ) == [{"start": 0.3, "end": 1.25}, {"start": 1.59, "end": 2.3}]


def test_merge_ranges_preserving_word_gaps_still_merges_short_transcript_pause() -> None:
    words = [
        {"start": 0.5, "end": 1.0, "text": "before"},
        {"start": 1.6, "end": 2.0, "text": "after"},
    ]

    assert merge_ranges_preserving_word_gaps(
        [{"start": 0.3, "end": 1.2}, {"start": 1.4, "end": 2.2}],
        words,
        merge_gap=0.35,
        min_segment=0.1,
        max_word_gap=0.8,
    ) == [{"start": 0.3, "end": 2.2}]


def test_snap_to_words_returns_ranges_unchanged_without_words() -> None:
    ranges = [{"start": 1.0, "end": 2.0}]
    assert snap_to_words(ranges, [], padding=0.1, total_duration=5.0) == ranges


def test_snap_to_words_uses_overlapping_word_boundaries_with_padding() -> None:
    words = [
        {"start": 0.9, "end": 1.1, "text": "hello"},
        {"start": 1.5, "end": 1.8, "text": "world"},
        {"start": 3.0, "end": 3.2, "text": "later"},
    ]

    assert snap_to_words([{"start": 1.0, "end": 1.6}], words, padding=0.2, total_duration=5.0) == [
        {"start": 0.7, "end": 2.0}
    ]


def test_snap_to_words_keeps_range_when_no_word_overlaps() -> None:
    assert snap_to_words(
        [{"start": 2.0, "end": 2.5}],
        [{"start": 0.0, "end": 1.0, "text": "before"}],
        padding=0.1,
        total_duration=5.0,
    ) == [{"start": 2.0, "end": 2.5}]


def test_split_ranges_on_word_gaps_removes_long_transcript_pause() -> None:
    words = [
        {"start": 0.5, "end": 1.0, "text": "before"},
        {"start": 4.0, "end": 4.5, "text": "after"},
    ]

    assert split_ranges_on_word_gaps(
        [{"start": 0.0, "end": 6.0}],
        words,
        max_word_gap=0.8,
        padding=0.2,
        total_duration=6.0,
    ) == [{"start": 0.3, "end": 1.2}, {"start": 3.8, "end": 4.7}]


def test_split_ranges_on_word_gaps_keeps_short_transcript_gap() -> None:
    words = [
        {"start": 0.5, "end": 1.0, "text": "before"},
        {"start": 1.6, "end": 2.0, "text": "after"},
    ]

    assert split_ranges_on_word_gaps(
        [{"start": 0.0, "end": 3.0}],
        words,
        max_word_gap=0.8,
        padding=0.2,
        total_duration=3.0,
    ) == [{"start": 0.3, "end": 2.2}]


def test_split_ranges_on_word_gaps_preserves_padding_without_transcript_words() -> None:
    assert split_ranges_on_word_gaps(
        [{"start": 1.0, "end": 2.0}],
        [],
        max_word_gap=0.8,
        padding=0.2,
        total_duration=5.0,
    ) == [{"start": 0.8, "end": 2.2}]


def test_split_ranges_on_word_gaps_preserves_padding_when_range_has_no_words() -> None:
    assert split_ranges_on_word_gaps(
        [{"start": 1.0, "end": 2.0}],
        [{"start": 3.0, "end": 3.2, "text": "later"}],
        max_word_gap=0.8,
        padding=0.2,
        total_duration=5.0,
    ) == [{"start": 0.8, "end": 2.2}]


def test_draft_ranges_uses_transcript_gaps_even_when_audio_is_not_silent(tmp_path, monkeypatch) -> None:
    video = tmp_path / "raw" / "clip.mp4"
    video.parent.mkdir()
    video.write_bytes(b"")
    edit_dir = tmp_path / "edit"
    edit_dir.mkdir()
    words = [
        {"start": 0.5, "end": 1.0, "text": "before"},
        {"start": 4.0, "end": 4.5, "text": "after"},
    ]
    monkeypatch.setattr("helpers.draft_silence_cut.ffprobe", lambda path: {"duration": 6.0})
    monkeypatch.setattr("helpers.draft_silence_cut.detect_silences", lambda video, noise, duration: [])
    monkeypatch.setattr("helpers.draft_silence_cut.load_words", lambda edit_dir, video: words)

    ranges, silences, total_duration = draft_ranges(
        video,
        edit_dir,
        noise="-35dB",
        min_silence=0.7,
        padding=0.2,
        min_segment=0.1,
        merge_gap=0.1,
        max_word_gap=0.8,
        word_snap=True,
    )

    assert silences == []
    assert total_duration == 6.0
    assert ranges == [{"start": 0.3, "end": 1.2}, {"start": 3.8, "end": 4.7}]


def test_draft_ranges_does_not_remerge_trimmed_word_gap(tmp_path, monkeypatch) -> None:
    video = tmp_path / "raw" / "clip.mp4"
    video.parent.mkdir()
    video.write_bytes(b"")
    edit_dir = tmp_path / "edit"
    edit_dir.mkdir()
    words = [
        {"start": 0.5, "end": 1.0, "text": "before"},
        {"start": 1.84, "end": 2.1, "text": "after"},
    ]
    monkeypatch.setattr("helpers.draft_silence_cut.ffprobe", lambda path: {"duration": 3.0})
    monkeypatch.setattr("helpers.draft_silence_cut.detect_silences", lambda video, noise, duration: [])
    monkeypatch.setattr("helpers.draft_silence_cut.load_words", lambda edit_dir, video: words)

    ranges, _, _ = draft_ranges(
        video,
        edit_dir,
        noise="-35dB",
        min_silence=0.7,
        padding=0.25,
        min_segment=0.1,
        merge_gap=0.35,
        max_word_gap=0.8,
        word_snap=True,
    )

    assert ranges == [{"start": 0.25, "end": 1.25}, {"start": 1.59, "end": 2.35}]


def test_detect_silences_raises_on_ffmpeg_failure(monkeypatch) -> None:
    monkeypatch.setattr("helpers.draft_silence_cut.find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        "helpers.draft_silence_cut.subprocess.run",
        lambda cmd, capture_output, text: SimpleNamespace(returncode=1, stderr="boom"),
    )

    with pytest.raises(RuntimeError, match="boom"):
        detect_silences(Path("x.mp4"), "-35dB", 0.7)


def test_normalize_negative_noise_arg_joins_negative_noise_value() -> None:
    assert normalize_negative_noise_arg(["--noise", "-35dB", "--style", "social"]) == [
        "--noise=-35dB",
        "--style",
        "social",
    ]
    assert normalize_negative_noise_arg(["--noise", "0.1", "--style", "social"]) == [
        "--noise",
        "0.1",
        "--style",
        "social",
    ]
