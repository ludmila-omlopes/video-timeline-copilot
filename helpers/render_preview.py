from __future__ import annotations

import argparse
import math
import subprocess
import tempfile
from pathlib import Path

from helpers.common import ensure_within, read_json, resolve_relative, safe_filename
from helpers.export_fcpxml import timeline_duration
from helpers.media_tools import find_ffmpeg, stream_types
from helpers.timing import range_source_duration, range_timeline_duration
from helpers.transforms import resolve_transform
from helpers.validate_edl import validate


def preview_path(edl_path: Path, edl: dict | None = None, timeline: dict | None = None) -> Path:
    payload = edl or read_json(edl_path)
    timelines = payload.get("timelines") or []
    selected = timeline or (timelines[0] if timelines else {})
    suffix = ""
    if len(timelines) > 1 and selected.get("name"):
        suffix = f"_{safe_filename(str(selected['name']), 'timeline')}"
    name = f"{safe_filename(payload.get('project_name', 'timeline'), 'timeline')}{suffix}_preview.mp4"
    return edl_path.parent / "previews" / name


def _even_ceiling(value: float) -> int:
    rounded = int(math.ceil(value))
    return rounded if rounded % 2 == 0 else rounded + 1


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _video_filter(width: int, height: int, fps: float, transform: dict | None = None, timeline_scale: float = 1.0) -> str:
    filters = []
    if abs(timeline_scale - 1.0) > 1e-6:
        filters.append(f"setpts={timeline_scale:.12g}*PTS")
    filters.extend(
        [
            f"fps={fps}",
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}",
        ]
    )
    resolved = resolve_transform(transform, width, height)
    if resolved.zoom != 1.0 or resolved.pan != 0.0 or resolved.tilt != 0.0:
        scaled_width = _even_ceiling(width * resolved.zoom)
        scaled_height = _even_ceiling(height * resolved.zoom)
        extra_x = scaled_width - width
        extra_y = scaled_height - height
        crop_x = _clamp((extra_x / 2.0) - resolved.pan, 0.0, float(extra_x))
        crop_y = _clamp((extra_y / 2.0) + resolved.tilt, 0.0, float(extra_y))
        filters.extend(
            [
                f"scale={scaled_width}:{scaled_height}",
                f"crop={width}:{height}:{crop_x:.3f}:{crop_y:.3f}",
            ]
        )
    filters.extend(["setsar=1", "format=yuv420p"])
    return ",".join(filters)


def _atempo_filters(speed: float) -> list[str]:
    factors = []
    remaining = speed
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(remaining)
    return [f"atempo={factor:.12g}" for factor in factors if abs(factor - 1.0) > 1e-6]


def _audio_filter(speed: float) -> str:
    filters = ["aresample=48000"]
    filters.extend(_atempo_filters(speed))
    filters.append("apad")
    return ",".join(filters)


def _segment_args(
    source: Path,
    start: float,
    source_duration: float,
    record_duration: float,
    width: int,
    height: int,
    fps: float,
    out_path: Path,
    types: set[str],
    transform: dict | None = None,
) -> list[str]:
    if "video" in types and "audio" in types:
        media_inputs = [
            "-ss",
            f"{start:.6f}",
            "-t",
            f"{source_duration:.6f}",
            "-i",
            str(source),
        ]
        maps = ["-map", "0:v:0", "-map", "0:a:0"]
    elif "video" in types:
        media_inputs = [
            "-ss",
            f"{start:.6f}",
            "-t",
            f"{source_duration:.6f}",
            "-i",
            str(source),
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=stereo:sample_rate=48000:d={record_duration:.6f}",
        ]
        maps = ["-map", "0:v:0", "-map", "1:a:0"]
    elif "audio" in types:
        media_inputs = [
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={width}x{height}:r={fps}:d={record_duration:.6f}",
            "-ss",
            f"{start:.6f}",
            "-t",
            f"{source_duration:.6f}",
            "-i",
            str(source),
        ]
        maps = ["-map", "0:v:0", "-map", "1:a:0"]
    else:
        raise ValueError(f"source has no audio or video streams: {source}")

    return [
        find_ffmpeg(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        *media_inputs,
        *maps,
        "-vf",
        _video_filter(width, height, fps, transform, record_duration / source_duration),
        "-af",
        _audio_filter(source_duration / record_duration),
        "-t",
        f"{record_duration:.6f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(out_path),
    ]


def _gap_args(duration: float, width: int, height: int, fps: float, out_path: Path) -> list[str]:
    return [
        find_ffmpeg(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={width}x{height}:r={fps}:d={duration:.6f}",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=channel_layout=stereo:sample_rate=48000:d={duration:.6f}",
        "-t",
        f"{duration:.6f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        str(out_path),
    ]


def _concat_args(segment_paths: list[Path], list_path: Path, out_path: Path) -> list[str]:
    lines = []
    for segment_path in segment_paths:
        escaped = segment_path.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [
        find_ffmpeg(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(out_path),
    ]


def render_preview(edl_path: Path, out_path: Path | None = None, timeline_name: str | None = None) -> Path:
    validation_errors = validate(edl_path)
    if validation_errors:
        raise ValueError("EDL validation failed: " + "; ".join(validation_errors))

    edl = read_json(edl_path)
    root = edl_path.parent.parent
    fps = float(edl["fps"])
    timelines = edl.get("timelines") or []
    if not timelines:
        raise ValueError("EDL has no timelines")
    timeline = next((item for item in timelines if item.get("name") == timeline_name), timelines[0]) if timeline_name else timelines[0]
    if timeline_name and timeline.get("name") != timeline_name:
        raise ValueError(f"timeline not found: {timeline_name}")

    width, height = [int(value) for value in timeline["resolution"]]
    destination = (out_path or preview_path(edl_path, edl, timeline)).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    source_paths = {
        source_id: ensure_within(resolve_relative(source_path, root), root)
        for source_id, source_path in timeline.get("sources", {}).items()
    }
    ranges = sorted(timeline.get("ranges") or [], key=lambda item: float(item.get("record_start", 0.0)))
    if not ranges:
        raise ValueError("timeline has no ranges")

    with tempfile.TemporaryDirectory(prefix="vtc-preview-") as tmp:
        tmp_dir = Path(tmp)
        segments: list[Path] = []
        cursor = 0.0
        frame_tolerance = 0.5 / fps
        stream_types_by_source: dict[str, set[str]] = {}
        for index, item in enumerate(ranges):
            record_start = float(item.get("record_start", cursor))
            if record_start - cursor > frame_tolerance:
                raise ValueError(f"range {index + 1} creates a record gap; validate the EDL before rendering")
            if cursor - record_start > frame_tolerance:
                raise ValueError(f"range {index + 1} overlaps the previous clip; validate the EDL before rendering")

            source_start = float(item["source_start"])
            source_duration = range_source_duration(item)
            duration = range_timeline_duration(item)
            if source_duration <= 0 or duration <= 0:
                raise ValueError(f"range {index + 1} duration must be positive")
            source_id = item["source"]
            source = source_paths[source_id]
            types = stream_types_by_source.get(source_id)
            if types is None:
                types = stream_types(source)
                stream_types_by_source[source_id] = types
            segment_path = tmp_dir / f"{index:04d}_clip.mp4"
            subprocess.run(
                _segment_args(
                    source,
                    source_start,
                    source_duration,
                    duration,
                    width,
                    height,
                    fps,
                    segment_path,
                    types,
                    item.get("transform"),
                ),
                check=True,
            )
            segments.append(segment_path)
            cursor = max(cursor, record_start + duration)

        expected = timeline_duration(timeline)
        if expected - cursor > max(0.1, 1 / fps):
            raise ValueError("timeline duration extends beyond the last clip; validate the EDL before rendering")

        subprocess.run(_concat_args(segments, tmp_dir / "concat.txt", destination), check=True)

    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Render an MP4 preview from a video-timeline-copilot EDL")
    parser.add_argument("edl", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="Output preview .mp4 path")
    parser.add_argument("--timeline", default=None, help="Timeline name to render; defaults to the first timeline")
    args = parser.parse_args()

    result = render_preview(args.edl.resolve(), args.out, args.timeline)
    print(f"preview -> {result}")


if __name__ == "__main__":
    main()
