from __future__ import annotations

from helpers.pack_transcripts import group_words, normalize_text, repeated_delivery_note


def test_group_words_splits_on_gap_and_skips_missing_timings() -> None:
    words = [
        {"start": 0.0, "end": 0.2, "text": "Hello"},
        {"text": "skip"},
        {"start": 0.3, "end": 0.5, "text": "there"},
        {"start": 1.2, "end": 1.5, "text": "again"},
    ]

    assert group_words(words, silence_threshold=0.5) == [
        {"start": 0.0, "end": 0.5, "text": "Hello there"},
        {"start": 1.2, "end": 1.5, "text": "again"},
    ]


def test_normalize_text_lowercases_punctuation_and_whitespace() -> None:
    assert normalize_text("  Hello,   WORLD!!\nAgain. ") == "hello world again"


def test_repeated_delivery_note_detects_near_identical_recent_phrase() -> None:
    note = repeated_delivery_note(
        {"start": 10.0, "end": 12.0, "text": "This is the clean delivery"},
        [{"start": 1.0, "end": 3.0, "text": "this is the clean delivery"}],
        repeat_window=15.0,
        similarity_threshold=0.8,
        min_words=3,
    )

    assert note is not None
    assert "possible repeated take" in note


def test_repeated_delivery_note_ignores_short_phrase() -> None:
    assert (
        repeated_delivery_note(
            {"start": 10.0, "end": 11.0, "text": "too short"},
            [{"start": 1.0, "end": 2.0, "text": "too short"}],
            repeat_window=15.0,
            similarity_threshold=0.8,
            min_words=3,
        )
        is None
    )


def test_repeated_delivery_note_ignores_phrase_outside_window() -> None:
    assert (
        repeated_delivery_note(
            {"start": 100.0, "end": 101.0, "text": "repeat this usable phrase"},
            [{"start": 1.0, "end": 2.0, "text": "repeat this usable phrase"}],
            repeat_window=15.0,
            similarity_threshold=0.8,
            min_words=3,
        )
        is None
    )
