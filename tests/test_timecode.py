from __future__ import annotations

import pytest

from helpers.timecode import find_start_timecode, timecode_to_seconds


def test_find_start_timecode_prefers_primary_video_stream() -> None:
    payload = {
        "streams": [
            {"codec_type": "data", "codec_tag_string": "tmcd", "tags": {"timecode": "02:00:00:00"}},
            {"codec_type": "video", "tags": {"timecode": "01:00:00:00"}},
        ],
        "format": {"tags": {"timecode": "03:00:00:00"}},
    }

    assert find_start_timecode(payload) == "01:00:00:00"


def test_find_start_timecode_uses_tmcd_stream_fallback() -> None:
    payload = {
        "streams": [
            {"codec_type": "video", "tags": {}},
            {"codec_type": "data", "codec_tag_string": "tmcd", "tags": {"TIMECODE": "01:00:00:00"}},
        ]
    }

    assert find_start_timecode(payload) == "01:00:00:00"


def test_timecode_to_seconds_converts_non_drop_frame_origin() -> None:
    assert timecode_to_seconds("01:00:00:00", "30/1") == 3600.0
    assert timecode_to_seconds("01:02:03:15", 30) == 3723.5


def test_timecode_to_seconds_converts_drop_frame_origin() -> None:
    assert timecode_to_seconds("01:00:00;00", "30000/1001") == pytest.approx(3599.9964)


def test_timecode_to_seconds_rejects_out_of_range_frame_number() -> None:
    with pytest.raises(ValueError, match="invalid for 30 fps"):
        timecode_to_seconds("01:00:00:30", 30)
