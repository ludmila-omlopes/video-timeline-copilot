from __future__ import annotations

from helpers.transforms import minimum_zoom_for_position, resolve_transform, transform_coverage_issue


def test_minimum_zoom_for_position_compensates_pan_and_tilt() -> None:
    assert minimum_zoom_for_position(1920, 1080, 0.0, -151.2) == 1.28
    assert round(minimum_zoom_for_position(1920, 1080, 192.0, 0.0), 3) == 1.2


def test_resolve_transform_bumps_zoom_to_cover_frame() -> None:
    transform = resolve_transform({"zoom": 1.07, "pan": 0.0, "tilt": -151.2}, 1920, 1080)

    assert transform.requested_zoom == 1.07
    assert transform.zoom == 1.28
    assert transform.zoom_was_adjusted is True


def test_transform_coverage_issue_reports_empty_space_risk() -> None:
    issue = transform_coverage_issue(
        0,
        2,
        {"source": "A001", "transform": {"zoom": 1.07, "pan": 0.0, "tilt": -151.2}},
        1920,
        1080,
    )

    assert issue is not None
    assert issue["range_index"] == 2
    assert issue["requested_zoom"] == 1.07
    assert issue["minimum_zoom"] == 1.28
