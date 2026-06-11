from __future__ import annotations

import pytest

from helpers.common import ensure_within, safe_filename, seconds_to_frames, srt_timestamp


def test_safe_filename_replaces_illegal_characters_and_strips_edges() -> None:
    assert safe_filename("a/b:c") == "a_b_c"
    assert safe_filename("...valid---") == "valid"


def test_safe_filename_uses_fallback_for_empty_result() -> None:
    assert safe_filename("///", fallback="fallback") == "fallback"


def test_srt_timestamp_formats_and_clamps() -> None:
    assert srt_timestamp(0.0) == "00:00:00,000"
    assert srt_timestamp(3661.5) == "01:01:01,500"
    assert srt_timestamp(-10.0) == "00:00:00,000"
    assert srt_timestamp(1.9995) == "00:00:02,000"


def test_ensure_within_returns_resolved_inside_path(tmp_path) -> None:
    inside = tmp_path / "folder" / "file.txt"
    inside.parent.mkdir()
    inside.write_text("ok", encoding="utf-8")

    assert ensure_within(inside, tmp_path) == inside.resolve()


def test_ensure_within_rejects_escaped_path(tmp_path) -> None:
    with pytest.raises(ValueError, match="escapes workspace"):
        ensure_within(tmp_path / ".." / "escape", tmp_path)


def test_seconds_to_frames_rounds_seconds() -> None:
    assert seconds_to_frames(1.0, 30) == 30
    assert seconds_to_frames(0.5, 30) == 15
    assert seconds_to_frames(0.016, 30) == 0
