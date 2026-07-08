from __future__ import annotations

from pathlib import Path

import pytest

from helpers import media_tools


@pytest.fixture(autouse=True)
def clear_tool_caches():
    media_tools.find_ffmpeg.cache_clear()
    media_tools.find_ffprobe.cache_clear()
    yield
    media_tools.find_ffmpeg.cache_clear()
    media_tools.find_ffprobe.cache_clear()


def test_find_ffmpeg_uses_path_hit_without_scanning(monkeypatch) -> None:
    monkeypatch.setattr("helpers.media_tools.shutil.which", lambda name: f"/fake/{name}")

    assert media_tools.find_ffmpeg() == "/fake/ffmpeg"


def test_find_ffmpeg_caches_tool_discovery(monkeypatch) -> None:
    calls = 0

    def fake_which(name: str) -> str:
        nonlocal calls
        calls += 1
        return f"/fake/{name}"

    monkeypatch.setattr("helpers.media_tools.shutil.which", fake_which)

    assert media_tools.find_ffmpeg() == "/fake/ffmpeg"
    assert media_tools.find_ffmpeg() == "/fake/ffmpeg"
    assert media_tools.find_ffmpeg() == "/fake/ffmpeg"
    assert calls == 1


def test_find_ffmpeg_not_found_mentions_path(monkeypatch) -> None:
    monkeypatch.setattr("helpers.media_tools.shutil.which", lambda name: None)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)

    with pytest.raises(FileNotFoundError, match="PATH"):
        media_tools.find_ffmpeg()


def test_stream_types_and_media_duration_parse_ffprobe_payload(monkeypatch) -> None:
    payload = {
        "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
        "format": {"duration": "12.5"},
    }
    monkeypatch.setattr("helpers.media_tools.ffprobe_json", lambda path: payload)

    assert media_tools.stream_types(Path("clip.mp4")) == {"video", "audio"}
    assert media_tools.media_duration(Path("clip.mp4")) == 12.5
    assert media_tools.video_dimensions(Path("clip.mp4")) is None


def test_video_dimensions_reads_first_video_stream(monkeypatch) -> None:
    payload = {
        "streams": [
            {"codec_type": "audio"},
            {"codec_type": "video", "width": 1080, "height": 1920},
        ],
        "format": {},
    }
    monkeypatch.setattr("helpers.media_tools.ffprobe_json", lambda path: payload)

    assert media_tools.video_dimensions(Path("clip.mp4")) == (1080, 1920)
