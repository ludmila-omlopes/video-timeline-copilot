from __future__ import annotations


def range_source_duration(item: dict) -> float:
    return float(item["source_end"]) - float(item["source_start"])


def range_playback_speed(item: dict) -> float:
    raw = item.get("speed", item.get("playback_speed"))
    if raw is None and item.get("speed_percent") is not None:
        raw = float(item["speed_percent"]) / 100.0
    if raw is None:
        return 1.0
    return float(raw)


def range_timeline_duration(item: dict) -> float:
    override = item.get("record_duration", item.get("timeline_duration"))
    if override is not None:
        return float(override)
    return range_source_duration(item) / range_playback_speed(item)


def range_effective_speed(item: dict) -> float:
    return range_source_duration(item) / range_timeline_duration(item)


def source_time_to_record_time(item: dict, source_time: float, record_start: float | None = None) -> float:
    source_duration = range_source_duration(item)
    if source_duration <= 0:
        return float(record_start if record_start is not None else item.get("record_start", 0.0))
    source_offset = float(source_time) - float(item["source_start"])
    timeline_offset = source_offset * (range_timeline_duration(item) / source_duration)
    effective_record_start = float(record_start if record_start is not None else item.get("record_start", 0.0))
    return effective_record_start + timeline_offset
