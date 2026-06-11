from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from helpers.common import ensure_within, read_json, resolve_relative, safe_filename
from helpers.export_fcpxml import timeline_duration
from helpers.inventory import find_ffprobe


def find_ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found

    candidates = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.extend((Path(local_app_data) / "Microsoft" / "WinGet" / "Packages").glob("**/ffmpeg.exe"))
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if root:
            candidates.extend(Path(root).glob("**/ffmpeg.exe"))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    raise FileNotFoundError(
        "ffmpeg was not found on PATH or in common FFmpeg install locations. "
        "Install FFmpeg or add its bin directory to PATH."
    )


def stream_types(path: Path) -> set[str]:
    proc = subprocess.run(
        [
            find_ffprobe(),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    return {stream.get("codec_type") for stream in payload.get("streams", [])}


def preview_path(edl_path: Path, edl: dict | None = None, timeline: dict | None = None) -> Path:
    payload = edl or read_json(edl_path)
    timelines = payload.get("timelines") or []
    selected = timeline or (timelines[0] if timelines else {})
    suffix = ""
    if len(timelines) > 1 and selected.get("name"):
        suffix = f"_{safe_filename(str(selected['name']), 'timeline')}"
    name = f"{safe_filename(payload.get('project_name', 'timeline'), 'timeline')}{suffix}_preview.mp4"
    return edl_path.parent / "previews" / name


def _segment_args(
    source: Path,
    start: float,
    duration: float,
    width: int,
    height: int,
    fps: float,
    out_path: Path,
    types: set[str],
) -> list[str]:
    if "video" in types and "audio" in types:
        media_inputs = [
            "-ss",
            f"{start:.6f}",
            "-t",
            f"{duration:.6f}",
            "-i",
            str(source),
        ]
        maps = ["-map", "0:v:0", "-map", "0:a:0"]
    elif "video" in types:
        media_inputs = [
            "-ss",
            f"{start:.6f}",
            "-t",
            f"{duration:.6f}",
            "-i",
            str(source),
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=stereo:sample_rate=48000:d={duration:.6f}",
        ]
        maps = ["-map", "0:v:0", "-map", "1:a:0"]
    elif "audio" in types:
        media_inputs = [
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={width}x{height}:r={fps}:d={duration:.6f}",
            "-ss",
            f"{start:.6f}",
            "-t",
            f"{duration:.6f}",
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
        (
            f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
        ),
        "-af",
        "aresample=48000,apad",
        "-t",
        f"{duration:.6f}",
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
        for index, item in enumerate(ranges):
            record_start = float(item.get("record_start", cursor))
            if record_start > cursor:
                gap_duration = record_start - cursor
                gap_path = tmp_dir / f"{index:04d}_gap.mp4"
                subprocess.run(_gap_args(gap_duration, width, height, fps, gap_path), check=True)
                segments.append(gap_path)
                cursor = record_start

            source_start = float(item["source_start"])
            source_end = float(item["source_end"])
            duration = source_end - source_start
            if duration <= 0:
                raise ValueError(f"range {index + 1} duration must be positive")
            source = source_paths[item["source"]]
            segment_path = tmp_dir / f"{index:04d}_clip.mp4"
            subprocess.run(
                _segment_args(source, source_start, duration, width, height, fps, segment_path, stream_types(source)),
                check=True,
            )
            segments.append(segment_path)
            cursor = max(cursor, record_start + duration)

        expected = timeline_duration(timeline)
        if expected > cursor:
            gap_path = tmp_dir / f"{len(segments):04d}_tail_gap.mp4"
            subprocess.run(_gap_args(expected - cursor, width, height, fps, gap_path), check=True)
            segments.append(gap_path)

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
