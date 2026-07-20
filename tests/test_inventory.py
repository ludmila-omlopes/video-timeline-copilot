from __future__ import annotations

from pathlib import Path

from helpers.inventory import ffprobe, iter_source_videos


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_iter_source_videos_excludes_edit_outputs(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "clip.mp4"
    touch(source)
    touch(tmp_path / "edit" / "previews" / "proj_preview.mp4")
    touch(tmp_path / "edit" / "clip2.mp4")

    assert iter_source_videos(tmp_path, tmp_path / "edit") == [source]


def test_iter_source_videos_honors_custom_edit_dir(tmp_path: Path) -> None:
    regular_edit_folder = tmp_path / "edit" / "x.mp4"
    touch(regular_edit_folder)
    touch(tmp_path / "custom_edit" / "preview.mp4")

    assert iter_source_videos(tmp_path, tmp_path / "custom_edit") == [regular_edit_folder]


def test_iter_source_videos_filters_extensions_case_insensitively(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "clip.MOV"
    touch(source)
    touch(tmp_path / "raw" / "notes.txt")

    assert iter_source_videos(tmp_path, tmp_path / "edit") == [source]


def test_iter_source_videos_skips_hidden_directories(tmp_path: Path) -> None:
    touch(tmp_path / ".cache" / "clip.mp4")

    assert iter_source_videos(tmp_path, tmp_path / "edit") == []


def test_iter_source_videos_allows_edit_dir_outside_root(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "clip.mp4"
    touch(source)
    edit_dir = tmp_path.parent / f"{tmp_path.name}_edit"

    assert iter_source_videos(tmp_path, edit_dir) == [source]


def test_ffprobe_includes_embedded_start_timecode(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "format": {"duration": "12.5"},
        "streams": [
            {
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
            },
            {"codec_type": "audio", "channels": 2, "sample_rate": "48000"},
            {
                "codec_type": "data",
                "codec_tag_string": "tmcd",
                "tags": {"timecode": "01:00:00:00"},
            },
        ],
    }
    monkeypatch.setattr("helpers.inventory.ffprobe_json", lambda path: payload)

    item = ffprobe(tmp_path / "clip.mov")

    assert item["start_timecode"] == "01:00:00:00"
    assert item["timecode_rate"] == "30000/1001"
