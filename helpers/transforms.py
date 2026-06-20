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


def minimum_zoom_for_position(width: int, height: int, pan: float, tilt: float) -> float:
    """Return the minimum center-scaled zoom needed to keep transformed video covering the frame."""
    if width <= 0 or height <= 0:
        return 1.0
    return max(1.0, 1.0 + (2.0 * abs(pan) / width), 1.0 + (2.0 * abs(tilt) / height))


def resolve_transform(transform: dict | None, width: int, height: int) -> ResolvedTransform:
    payload = transform or {}
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
