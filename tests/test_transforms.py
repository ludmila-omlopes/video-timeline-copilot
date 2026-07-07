from __future__ import annotations

from helpers.transforms import (
    Rect,
    aspect_fill_crop_rect,
    gameplay_screen_rect,
    layer_transform,
    minimum_zoom_for_position,
    resolve_transform,
    transform_coverage_issue,
    visual_layer_dest_rect,
    visual_layer_source_rect,
)


def test_minimum_zoom_for_position_compensates_pan_and_tilt() -> None:
    assert minimum_zoom_for_position(1920, 1080, 0.0, -151.2) == 1.28
    assert round(minimum_zoom_for_position(1920, 1080, 192.0, 0.0), 3) == 1.2


def test_resolve_transform_bumps_zoom_to_cover_frame() -> None:
    transform = resolve_transform({"zoom": 1.07, "pan": 0.0, "tilt": -151.2}, 1920, 1080)

    assert transform.requested_zoom == 1.07
    assert transform.zoom == 1.28
    assert transform.zoom_was_adjusted is True


def test_gameplay_facecam_preset_focuses_facecam_rect() -> None:
    transform = resolve_transform(
        {
            "preset": "gameplay-facecam",
            "facecam": {"x": 1600, "y": 720, "width": 320, "height": 360},
        },
        1920,
        1080,
    )

    assert transform.zoom == 6.0
    assert transform.pan == -4800.0
    assert transform.tilt == 2160.0


def test_gameplay_screen_preset_excludes_facecam_and_centers_remaining_screen() -> None:
    transform = resolve_transform(
        {
            "preset": "gameplay-screen",
            "facecam": {"x": 0, "y": 720, "width": 320, "height": 360},
        },
        1920,
        1080,
    )

    assert transform.zoom == 1.2
    assert transform.pan == -192.0
    assert transform.tilt == 0.0


def test_gameplay_screen_rect_respects_padding() -> None:
    rect = gameplay_screen_rect(Rect(0.0, 540.0, 384.0, 540.0), 1920, 1080, padding=108.0)

    assert rect.x == 492.0
    assert rect.width == 1428.0


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


def test_visual_layer_rects_support_normalized_coordinates() -> None:
    layer = {
        "source_rect": {"x": 0.0, "y": 0.5, "width": 0.25, "height": 0.25},
        "dest_rect": {"x": 0.0, "y": 0.5, "width": 1.0, "height": 0.25},
    }

    source = visual_layer_source_rect(layer, 1920, 1080)
    dest = visual_layer_dest_rect(layer, 1080, 1920)

    assert source == Rect(0.0, 540.0, 480.0, 270.0)
    assert dest == Rect(0.0, 960.0, 1080.0, 480.0)


def test_aspect_fill_crop_rect_shrinks_taller_source() -> None:
    crop = aspect_fill_crop_rect(Rect(0.0, 270.0, 480.0, 540.0), Rect(0.0, 0.0, 1080.0, 864.0))

    assert crop == Rect(0.0, 348.0, 480.0, 384.0)


def test_aspect_fill_crop_rect_keeps_matching_aspect() -> None:
    source = Rect(10.0, 20.0, 500.0, 400.0)

    assert aspect_fill_crop_rect(source, Rect(0.0, 0.0, 1000.0, 800.0)) == source


def test_layer_transform_maps_crop_center_to_dest_center() -> None:
    position_x, position_y, scale = layer_transform(
        Rect(0.0, 348.0, 480.0, 384.0),
        Rect(0.0, 0.0, 1080.0, 864.0),
        1920,
        1080,
        1080,
        1920,
    )

    assert position_x == 1620.0
    assert position_y == 528.0
    assert scale == 2.25

    identity_x, identity_y, identity_scale = layer_transform(
        Rect(0.0, 0.0, 1920.0, 1080.0),
        Rect(0.0, 0.0, 1920.0, 1080.0),
        1920,
        1080,
        1920,
        1080,
    )
    assert identity_x == 0.0
    assert identity_y == 0.0
    assert identity_scale == 1.0
