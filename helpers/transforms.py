from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedTransform:
    requested_zoom: float
    zoom: float
    pan: float
    tilt: float
    minimum_zoom: float

    @property
    def zoom_was_adjusted(self) -> bool:
        return self.zoom > self.requested_zoom + 1e-6


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2.0

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)


def minimum_zoom_for_position(width: int, height: int, pan: float, tilt: float) -> float:
    """Return the minimum center-scaled zoom needed to keep transformed video covering the frame."""
    if width <= 0 or height <= 0:
        return 1.0
    return max(1.0, 1.0 + (2.0 * abs(pan) / width), 1.0 + (2.0 * abs(tilt) / height))


def _is_normalized_rect(values: list[float]) -> bool:
    return all(0.0 <= value <= 1.0 for value in values)


def _rect_from_payload(payload: dict, width: int, height: int) -> Rect:
    if {"left", "top", "right", "bottom"}.issubset(payload):
        left = float(payload["left"])
        top = float(payload["top"])
        right = float(payload["right"])
        bottom = float(payload["bottom"])
        values = [left, top, right, bottom]
        if _is_normalized_rect(values):
            left *= width
            right *= width
            top *= height
            bottom *= height
        return Rect(left, top, max(0.0, right - left), max(0.0, bottom - top))

    x = float(payload.get("x", 0.0))
    y = float(payload.get("y", 0.0))
    rect_width = float(payload.get("width", payload.get("w", width)))
    rect_height = float(payload.get("height", payload.get("h", height)))
    values = [x, y, rect_width, rect_height]
    if _is_normalized_rect(values):
        x *= width
        rect_width *= width
        y *= height
        rect_height *= height
    return Rect(x, y, max(0.0, rect_width), max(0.0, rect_height))


def _padding_pixels(value: float, width: int, height: int) -> float:
    if 0.0 <= value <= 1.0:
        return value * min(width, height)
    return value


def _clamped_rect(rect: Rect, width: int, height: int) -> Rect:
    x = min(max(0.0, rect.x), float(width))
    y = min(max(0.0, rect.y), float(height))
    right = min(max(x, rect.right), float(width))
    bottom = min(max(y, rect.bottom), float(height))
    return Rect(x, y, max(0.0, right - x), max(0.0, bottom - y))


def _expanded_rect(rect: Rect, padding: float, width: int, height: int) -> Rect:
    return _clamped_rect(
        Rect(rect.x - padding, rect.y - padding, rect.width + 2.0 * padding, rect.height + 2.0 * padding),
        width,
        height,
    )


def gameplay_screen_rect(facecam: Rect, width: int, height: int, padding: float = 0.0) -> Rect:
    """Return the largest source region that excludes the facecam overlay."""
    facecam = _expanded_rect(facecam, padding, width, height)
    candidates = [
        Rect(facecam.right, 0.0, width - facecam.right, float(height)),
        Rect(0.0, 0.0, facecam.x, float(height)),
        Rect(0.0, facecam.bottom, float(width), height - facecam.bottom),
        Rect(0.0, 0.0, float(width), facecam.y),
    ]
    valid = [candidate for candidate in candidates if candidate.width > 0 and candidate.height > 0]
    if not valid:
        return Rect(0.0, 0.0, float(width), float(height))
    return max(valid, key=lambda candidate: candidate.area)


def transform_for_focus_rect(rect: Rect, width: int, height: int) -> ResolvedTransform:
    rect = _clamped_rect(rect, width, height)
    if width <= 0 or height <= 0 or rect.width <= 0 or rect.height <= 0:
        return ResolvedTransform(1.0, 1.0, 0.0, 0.0, 1.0)

    zoom = max(width / rect.width, height / rect.height)
    pan = zoom * (width / 2.0 - rect.center_x)
    tilt = zoom * (rect.center_y - height / 2.0)
    minimum_zoom = minimum_zoom_for_position(width, height, pan, tilt)
    resolved_zoom = max(zoom, minimum_zoom)
    return ResolvedTransform(
        requested_zoom=round(zoom, 6),
        zoom=round(resolved_zoom, 6),
        pan=round(pan, 6),
        tilt=round(tilt, 6),
        minimum_zoom=round(minimum_zoom, 6),
    )


def resolve_transform(transform: dict | None, width: int, height: int) -> ResolvedTransform:
    payload = transform or {}
    preset = str(payload.get("preset", payload.get("mode", ""))).strip().lower().replace("_", "-")
    if preset in {"gameplay-facecam", "facecam"}:
        facecam = _rect_from_payload(payload.get("facecam", payload.get("rect", {})), width, height)
        padding = _padding_pixels(float(payload.get("padding", 0.0)), width, height)
        return transform_for_focus_rect(_expanded_rect(facecam, padding, width, height), width, height)
    if preset in {"gameplay-screen", "screen-without-facecam"}:
        facecam = _rect_from_payload(payload.get("facecam", {}), width, height)
        padding = _padding_pixels(float(payload.get("padding", 0.0)), width, height)
        return transform_for_focus_rect(gameplay_screen_rect(facecam, width, height, padding), width, height)
    if payload.get("focus_rect"):
        return transform_for_focus_rect(_rect_from_payload(payload["focus_rect"], width, height), width, height)

    requested_zoom = max(float(payload.get("zoom", 1.0)), 1.0)
    pan = float(payload.get("pan", 0.0))
    tilt = float(payload.get("tilt", 0.0))
    minimum_zoom = minimum_zoom_for_position(width, height, pan, tilt)
    return ResolvedTransform(
        requested_zoom=requested_zoom,
        zoom=max(requested_zoom, minimum_zoom),
        pan=pan,
        tilt=tilt,
        minimum_zoom=minimum_zoom,
    )


def transform_coverage_issue(timeline_index: int, range_index: int, item: dict, width: int, height: int) -> dict | None:
    transform = item.get("transform") or {}
    resolved = resolve_transform(transform, width, height)
    if not resolved.zoom_was_adjusted:
        return None
    return {
        "timeline_index": timeline_index,
        "range_index": range_index,
        "source": item.get("source"),
        "requested_zoom": round(resolved.requested_zoom, 6),
        "minimum_zoom": round(resolved.minimum_zoom, 6),
        "pan": round(resolved.pan, 6),
        "tilt": round(resolved.tilt, 6),
        "message": (
            f"range {range_index} transform can expose empty frame area: "
            f"zoom {resolved.requested_zoom:.3f} is below minimum {resolved.minimum_zoom:.3f} "
            f"for pan {resolved.pan:.3f}, tilt {resolved.tilt:.3f}"
        ),
    }
