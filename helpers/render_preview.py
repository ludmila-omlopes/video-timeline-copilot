from __future__ import annotations

import argparse
import math
import subprocess
import tempfile
from pathlib import Path

from helpers.common import ensure_within, read_json, resolve_relative, safe_filename
from helpers.export_fcpxml import timeline_duration
from helpers.media_tools import find_ffmpeg, stream_types, video_dimensions
from helpers.timing import range_source_duration, range_timeline_duration
from helpers.transforms import Rect, resolve_transform, visual_layer_dest_rect, visual_layer_source_rect
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


def _rounded_rect(rect: Rect) -> tuple[int, int, int, int]:
    return (
        max(0, int(round(rect.x))),
        max(0, int(round(rect.y))),
        max(1, int(round(rect.width))),
        max(1, int(round(rect.height))),
    )


def _visual_layer_timing(item: dict, layer: dict) -> tuple[float, float, float]:
    start = float(layer.get("source_start", item["source_start"]))
    end = float(layer.get("source_end", item["source_end"]))
    source_duration = end - start
    if source_duration <= 0:
        raise ValueError("visual layer source_end must be greater than source_start")
    return start, end, source_duration


def _layered_segment_args(
    source: Path,
    start: float,
    source_duration: float,
    record_duration: float,
    width: int,
    height: int,
    fps: float,
    out_path: Path,
    types: set[str],
    item: dict,
    source_paths: dict[str, Path],
    source_dimensions: dict[Path, tuple[int, int]],
) -> list[str]:
    visual_layers = item.get("visual_layers") or []
    if not visual_layers:
        return _segment_args(
            source,
            start,
            source_duration,
            record_duration,
            width,
            height,
            fps,
            out_path,
            types,
            item.get("transform"),
        )

    media_inputs: list[str] = []
    filter_parts: list[str] = []
    input_index = 0

    if "audio" in types:
        audio_index = input_index
        media_inputs.extend(["-ss", f"{start:.6f}", "-t", f"{source_duration:.6f}", "-i", str(source)])
        input_index += 1
        audio_filter = _audio_filter(source_duration / record_duration)
    else:
        audio_index = input_index
        media_inputs.extend(
            [
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=channel_layout=stereo:sample_rate=48000:d={record_duration:.6f}",
            ]
        )
        input_index += 1
        audio_filter = "aresample=48000,apad"

    layer_inputs = []
    for layer_index, layer in enumerate(visual_layers):
        layer_source_id = str(layer.get("source", item["source"]))
        layer_source = source_paths[layer_source_id]
        layer_start, _, layer_source_duration = _visual_layer_timing(item, layer)
        layer_inputs.append((layer_index, input_index, layer, layer_source, layer_source_duration))
        media_inputs.extend(
            ["-ss", f"{layer_start:.6f}", "-t", f"{layer_source_duration:.6f}", "-i", str(layer_source)]
        )
        input_index += 1

    canvas_index = input_index
    media_inputs.extend(["-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}:d={record_duration:.6f}"])

    filter_parts.append(f"[{canvas_index}:v]format=rgba[base0]")
    overlay_base = "base0"
    for layer_index, input_idx, layer, layer_source, layer_source_duration in layer_inputs:
        source_width, source_height = source_dimensions.get(layer_source, (width, height))
        source_rect = visual_layer_source_rect(layer, source_width, source_height)
        dest_rect = visual_layer_dest_rect(layer, width, height)
        crop_x, crop_y, crop_w, crop_h = _rounded_rect(source_rect)
        dest_x, dest_y, dest_w, dest_h = _rounded_rect(dest_rect)
        timeline_scale = record_duration / layer_source_duration
        layer_label = f"layer{layer_index}"
        filter_parts.append(
            (
                f"[{input_idx}:v]setpts={timeline_scale:.12g}*PTS,fps={fps},"
                f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
                f"scale={dest_w}:{dest_h}:force_original_aspect_ratio=increase,"
                f"crop={dest_w}:{dest_h},setsar=1,format=rgba[{layer_label}]"
            )
        )
        next_base = f"base{layer_index + 1}"
        filter_parts.append(
            f"[{overlay_base}][{layer_label}]overlay=x={dest_x}:y={dest_y}:shortest=0:eof_action=pass[{next_base}]"
        )
        overlay_base = next_base

    filter_parts.append(f"[{overlay_base}]format=yuv420p[vout]")
    filter_parts.append(f"[{audio_index}:a]{audio_filter}[aout]")

    return [
        find_ffmpeg(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        *media_inputs,
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[vout]",
        "-map",
        "[aout]",
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
    source_dimensions = {}
    for source_path in source_paths.values():
        dimensions = video_dimensions(source_path)
        if dimensions:
            source_dimensions[source_path] = dimensions
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
            args = (
                _layered_segment_args(
                    source,
                    source_start,
                    source_duration,
                    duration,
                    width,
                    height,
                    fps,
                    segment_path,
                    types,
                    item,
                    source_paths,
                    source_dimensions,
                )
                if item.get("visual_layers")
                else _segment_args(
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
                )
            )
            subprocess.run(args, check=True)
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
