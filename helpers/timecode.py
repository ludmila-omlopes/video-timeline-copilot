from __future__ import annotations

from fractions import Fraction
import re


TIMECODE_PATTERN = re.compile(
    r"^(?P<hours>\d{2,}):(?P<minutes>[0-5]\d):(?P<seconds>[0-5]\d)(?P<separator>[:;.])(?P<frames>\d{2,3})$"
)


def _tag_value(tags: dict | None, key: str) -> str | None:
    for name, value in (tags or {}).items():
        if str(name).lower() == key and value is not None:
            text = str(value).strip()
            return text or None
    return None


def find_start_timecode(ffprobe_payload: dict) -> str | None:
    """Return the embedded media timecode, preferring the primary video stream."""
    streams = ffprobe_payload.get("streams") or []
    candidates = [stream for stream in streams if stream.get("codec_type") == "video"]
    candidates.extend(
        stream
        for stream in streams
        if stream.get("codec_type") == "data"
        or str(stream.get("codec_tag_string", "")).lower() == "tmcd"
    )
    candidates.extend(stream for stream in streams if stream not in candidates)
    candidates.append(ffprobe_payload.get("format") or {})

    for candidate in candidates:
        value = _tag_value(candidate.get("tags"), "timecode")
        if value and TIMECODE_PATTERN.match(value):
            return value
    return None


def frame_rate_fraction(value: str | float | int) -> Fraction:
    if isinstance(value, str) and "/" in value:
        numerator, denominator = value.split("/", maxsplit=1)
        rate = Fraction(int(numerator), int(denominator))
    else:
        rate = Fraction(str(value)).limit_denominator(100000)
    if rate <= 0:
        raise ValueError("frame rate must be positive")
    return rate


def timecode_to_seconds(timecode: str, frame_rate: str | float | int) -> float:
    """Convert an HH:MM:SS:FF timecode origin to elapsed rational seconds."""
    match = TIMECODE_PATTERN.match(timecode.strip())
    if match is None:
        raise ValueError(f"unsupported timecode: {timecode}")

    rate = frame_rate_fraction(frame_rate)
    nominal_fps = round(float(rate))
    if nominal_fps <= 0:
        raise ValueError("frame rate must round to at least one frame per second")

    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    frames = int(match.group("frames"))
    if frames >= nominal_fps:
        raise ValueError(f"timecode frame number {frames} is invalid for {nominal_fps} fps")

    frame_number = ((hours * 3600 + minutes * 60 + seconds) * nominal_fps) + frames
    if match.group("separator") in {";", "."}:
        drop_frames = round(nominal_fps * 0.06666666666666667)
        total_minutes = hours * 60 + minutes
        frame_number -= drop_frames * (total_minutes - total_minutes // 10)

    return float(Fraction(frame_number * rate.denominator, rate.numerator))
