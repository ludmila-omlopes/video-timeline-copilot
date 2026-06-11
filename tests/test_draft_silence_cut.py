from __future__ import annotations

import pytest

from helpers.draft_silence_cut import (
    complement_silences,
    merge_ranges,
    normalize_negative_noise_arg,
    pad_ranges,
    parse_frame_rate,
    snap_to_words,
)


def test_parse_frame_rate_handles_ratios_numbers_and_defaults() -> None:
    assert parse_frame_rate("30000/1001") == pytest.approx(29.97002997)
    assert parse_frame_rate("25") == 25.0
    assert parse_frame_rate(None) == 30.0
    assert parse_frame_rate("0/0") == 30.0


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
