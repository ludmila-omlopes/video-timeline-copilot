from __future__ import annotations

from array import array
import json
from pathlib import Path

import pytest

from helpers.audio_refine import (
    audio_activity_segments,
    default_report_path,
    parse_threshold_db,
    refine_edl_audio_cuts,
    refine_range_with_audio,
)
from helpers.cli import COMMANDS


def write_edl(tmp_path: Path) -> Path:
    raw_dir = tmp_path / "raw"
    edit_dir = tmp_path / "edit"
    raw_dir.mkdir()
    edit_dir.mkdir()
    (raw_dir / "clip.mp4").write_bytes(b"")
    edl = {
        "version": 1,
        "project_name": "Audio Refine Test",
        "fps": 30,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": [
                    {"source": "A001", "source_start": 0.0, "source_end": 1.0, "record_start": 0.0},
                    {"source": "A001", "source_start": 2.0, "source_end": 3.0, "record_start": 1.0},
                ],
            }
        ],
    }
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(json.dumps(edl), encoding="utf-8")
    return edl_path


def test_refine_audio_cuts_command_is_registered() -> None:
    assert COMMANDS["refine-audio-cuts"] == ("helpers.audio_refine", "Refine EDL cut boundaries using source audio")


def test_parse_threshold_db_accepts_db_suffixes() -> None:
    assert parse_threshold_db("-45") == -45.0
    assert parse_threshold_db("-45dB") == -45.0
    assert parse_threshold_db("-45 dbfs") == -45.0


def test_audio_activity_segments_detects_active_pcm_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    samples = array("h", [0] * 160 + [12000] * 160 + [0] * 160)
    monkeypatch.setattr("helpers.audio_refine.decode_audio_window", lambda *args, **kwargs: samples)

    segments = audio_activity_segments(
        Path("clip.mp4"),
        1.0,
        1.03,
        threshold_db=-40.0,
        frame_ms=10.0,
        sample_rate=16_000,
    )

    assert segments == [{"start": pytest.approx(1.01), "end": pytest.approx(1.02)}]


def test_refine_range_with_audio_extends_boundaries_outward(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_segments(source: Path, start: float, end: float, **kwargs) -> list[dict]:
        if start < 1.0 < end:
            return [{"start": 0.94, "end": 1.02}]
        if start < 2.0 < end:
            return [{"start": 1.96, "end": 2.08}]
        return []

    monkeypatch.setattr("helpers.audio_refine.audio_activity_segments", fake_segments)

    refined = refine_range_with_audio(
        Path("clip.mp4"),
        {"source_start": 1.0, "source_end": 2.0, "record_start": 0.0},
        source_duration=3.0,
        search_window=0.35,
        bridge_seconds=0.08,
        guard_seconds=0.04,
    )

    assert refined["source_start"] == 0.9
    assert refined["source_end"] == 2.12


def test_refine_range_with_audio_ignores_audio_after_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_segments(source: Path, start: float, end: float, **kwargs) -> list[dict]:
        if start < 2.0 < end:
            return [{"start": 2.12, "end": 2.3}]
        return []

    monkeypatch.setattr("helpers.audio_refine.audio_activity_segments", fake_segments)

    refined = refine_range_with_audio(
        Path("clip.mp4"),
        {"source_start": 1.0, "source_end": 2.0, "record_start": 0.0},
        source_duration=3.0,
        search_window=0.35,
        bridge_seconds=0.08,
        guard_seconds=0.04,
    )

    assert refined["source_start"] == 1.0
    assert refined["source_end"] == 2.0


def test_refine_edl_audio_cuts_writes_report_and_retimes_record_starts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    edl_path = write_edl(tmp_path)

    def fake_refine(source: Path, item: dict, **kwargs) -> dict:
        refined = dict(item)
        if refined["source_start"] == 0.0:
            refined["source_end"] = 1.1
        return refined

    monkeypatch.setattr("helpers.audio_refine.media_duration", lambda path: 10.0)
    monkeypatch.setattr("helpers.audio_refine.refine_range_with_audio", fake_refine)

    out_path = edl_path.parent / "edl.refined.json"
    report = refine_edl_audio_cuts(edl_path, out_path=out_path)
    refined_edl = json.loads(out_path.read_text(encoding="utf-8"))

    assert report["change_count"] == 1
    assert report["validation_errors"] == []
    assert default_report_path(edl_path).exists()
    assert refined_edl["timelines"][0]["ranges"][0]["source_end"] == 1.1
    assert refined_edl["timelines"][0]["ranges"][1]["record_start"] == 1.1
