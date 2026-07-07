from __future__ import annotations

from helpers.common import write_json
from helpers.pack_transcripts import build_packed_lines, group_words, normalize_text, repeated_delivery_note


def make_words(tokens: list[str], *, extra_gaps: dict[int, float] | None = None) -> list[dict]:
    words = []
    cursor = 0.0
    extra_gaps = extra_gaps or {}
    for index, token in enumerate(tokens):
        end = cursor + 0.24
        words.append({"start": round(cursor, 3), "end": round(end, 3), "text": token})
        cursor = end + 0.06 + extra_gaps.get(index, 0.0)
    return words


def packed_text_for_words(tmp_path, words: list[dict]) -> str:
    edit_dir = tmp_path / "edit"
    write_json(
        edit_dir / "transcripts" / "clip.json",
        {
            "duration": words[-1]["end"] if words else 0.0,
            "words": words,
        },
    )
    return "\n".join(
        build_packed_lines(
            edit_dir,
            silence_threshold=0.5,
            repeat_window=45.0,
            similarity_threshold=0.82,
            min_words=3,
            include_video_analysis=False,
        )
    )


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


def test_build_packed_lines_flags_tail_correction_inside_phrase(tmp_path) -> None:
    text = packed_text_for_words(
        tmp_path,
        make_words(["a", "gente", "vai", "publicar", "na", "terça", "na", "quinta-feira"]),
    )

    assert "possible self-correction/restart" in text
    assert "keep only the corrected delivery" in text


def test_build_packed_lines_flags_tail_correction_across_phrase_split(tmp_path) -> None:
    text = packed_text_for_words(
        tmp_path,
        make_words(["esse", "arquivo", "fica", "em", "docs", "em", "helpers", "docs"], extra_gaps={4: 0.55}),
    )

    assert "[000.00-001.44] esse arquivo fica em docs" in text
    assert "em helpers docs  [NOTE: possible self-correction/restart" in text


def test_build_packed_lines_flags_restart_after_interruption(tmp_path) -> None:
    text = packed_text_for_words(
        tmp_path,
        make_words(
            ["eu", "acho", "que", "esse", "trecho", "esse", "trecho", "precisa", "sair"],
            extra_gaps={4: 0.55},
        ),
    )

    assert "esse trecho precisa sair  [NOTE: possible self-correction/restart" in text


def test_build_packed_lines_does_not_flag_enumeration(tmp_path) -> None:
    text = packed_text_for_words(
        tmp_path,
        make_words(["primeiro", "a", "gente", "grava", "depois", "a", "gente", "corta", "depois", "a", "gente", "publica"]),
    )

    assert "possible self-correction/restart" not in text


def test_build_packed_lines_does_not_flag_short_emphasis(tmp_path) -> None:
    text = packed_text_for_words(tmp_path, make_words(["muito", "muito", "bom"]))

    assert "possible self-correction/restart" not in text


def test_build_packed_lines_does_not_flag_distinct_topic_phrases(tmp_path) -> None:
    text = packed_text_for_words(
        tmp_path,
        make_words(
            ["vamos", "abrir", "o", "arquivo", "agora", "o", "arquivo", "final", "aparece"],
            extra_gaps={3: 0.55},
        ),
    )

    assert "possible self-correction/restart" not in text


def test_build_packed_lines_includes_cached_video_analysis(tmp_path) -> None:
    edit_dir = tmp_path / "edit"
    write_json(
        edit_dir / "transcripts" / "clip.json",
        {
            "duration": 3.0,
            "words": [{"start": 0.0, "end": 0.5, "text": "Look"}],
        },
    )
    write_json(
        edit_dir / "video_analysis" / "clip.json",
        {
            "sampled_frames": [{"time": 0.0, "path": "video_frames/clip/frame_000001.jpg"}],
            "scene_changes": [{"time": 1.5}],
            "limitations": ["No OCR by default."],
        },
    )

    text = "\n".join(
        build_packed_lines(
            edit_dir,
            silence_threshold=0.5,
            repeat_window=45.0,
            similarity_threshold=0.82,
            min_words=3,
        )
    )

    assert "### Visual context" in text
    assert "video_frames/clip/frame_000001.jpg" in text
    assert "Scene-change signals: 001.50" in text
    assert "### Transcript phrases" in text


def test_build_packed_lines_explains_transcript_only_fallback(tmp_path) -> None:
    edit_dir = tmp_path / "edit"
    write_json(
        edit_dir / "transcripts" / "clip.json",
        {
            "duration": 1.0,
            "words": [{"start": 0.0, "end": 0.5, "text": "Hello"}],
        },
    )

    text = "\n".join(
        build_packed_lines(
            edit_dir,
            silence_threshold=0.5,
            repeat_window=45.0,
            similarity_threshold=0.82,
            min_words=3,
        )
    )

    assert "No cached video analysis found" in text
    assert "continue transcript-only" in text
