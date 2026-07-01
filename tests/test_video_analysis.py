from __future__ import annotations

from helpers.video_analysis import active_ranges_from_freezes, analysis_to_lines, parse_freeze_ranges, parse_scene_times


def test_parse_scene_times_deduplicates_showinfo_output() -> None:
    log = """
    [Parsed_showinfo_1 @ 000] n: 0 pts:0 pts_time:1.234 pos:0
    [Parsed_showinfo_1 @ 000] n: 1 pts:0 pts_time:1.234 pos:0
    [Parsed_showinfo_1 @ 000] n: 2 pts:0 pts_time:5 pos:0
    """

    assert parse_scene_times(log) == [1.234, 5.0]


def test_parse_freeze_ranges_pairs_start_duration_and_end() -> None:
    log = """
    [freezedetect @ 000] lavfi.freezedetect.freeze_start: 10
    [freezedetect @ 000] lavfi.freezedetect.freeze_duration: 2.5
    [freezedetect @ 000] lavfi.freezedetect.freeze_end: 12.5
    """

    assert parse_freeze_ranges(log) == [
        {
            "type": "low_motion",
            "start": 10.0,
            "end": 12.5,
            "duration": 2.5,
            "label": "freeze or near-static visual range",
        }
    ]


def test_active_ranges_from_freezes_returns_complement() -> None:
    assert active_ranges_from_freezes(
        10.0,
        [
            {"start": 2.0, "end": 4.0},
            {"start": 8.0, "end": 9.0},
        ],
    ) == [
        {
            "type": "visual_activity",
            "start": 0.0,
            "end": 2.0,
            "duration": 2.0,
            "label": "visual changes or motion detected between static ranges",
        },
        {
            "type": "visual_activity",
            "start": 4.0,
            "end": 8.0,
            "duration": 4.0,
            "label": "visual changes or motion detected between static ranges",
        },
        {
            "type": "visual_activity",
            "start": 9.0,
            "end": 10.0,
            "duration": 1.0,
            "label": "visual changes or motion detected between static ranges",
        },
    ]


def test_analysis_to_lines_includes_frames_scenes_observations_and_limits() -> None:
    lines = analysis_to_lines(
        {
            "sampled_frames": [{"time": 0.0, "path": "video_frames/clip/frame_000001.jpg"}],
            "scene_changes": [{"time": 4.2}],
            "low_motion_ranges": [{"start": 7.0, "end": 9.0, "label": "static title card"}],
            "motion_ranges": [{"start": 0.0, "end": 7.0, "label": "visible activity"}],
            "observations": [{"start": 1.0, "end": 2.0, "text": "speaker points at chart"}],
            "limitations": ["No OCR by default."],
        }
    )

    text = "\n".join(lines)
    assert "speaker points at chart" in text
    assert "video_frames/clip/frame_000001.jpg" in text
    assert "Scene-change signals: 004.20" in text
    assert "static title card" in text
    assert "visible activity" in text
    assert "No OCR by default." in text
