from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from helpers.common import read_json, safe_filename, write_json
from helpers.inventory import ffprobe
from helpers.media_tools import find_ffmpeg


SCENE_TIME_RE = re.compile(r"pts_time:(?P<time>-?\d+(?:\.\d+)?)")
FREEZE_RE = re.compile(r"lavfi\.freezedetect\.(?P<key>freeze_start|freeze_end|freeze_duration): (?P<time>-?\d+(?:\.\d+)?)")


def fmt(seconds: float) -> str:
    return f"{seconds:06.2f}"


def relative_to_edit(path: Path, edit_dir: Path) -> str:
    try:
        return path.resolve().relative_to(edit_dir.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def parse_scene_times(log: str) -> list[float]:
    times = {round(float(match.group("time")), 3) for match in SCENE_TIME_RE.finditer(log)}
    return sorted(time for time in times if time >= 0)


def parse_freeze_ranges(log: str) -> list[dict]:
    ranges: list[dict] = []
    current_start: float | None = None
    current_duration: float | None = None

    for match in FREEZE_RE.finditer(log):
        key = match.group("key")
        value = float(match.group("time"))
        if key == "freeze_start":
            current_start = value
            current_duration = None
        elif key == "freeze_duration":
            current_duration = value
        elif key == "freeze_end" and current_start is not None:
            end = value
            duration = current_duration if current_duration is not None else end - current_start
            ranges.append(
                {
                    "type": "low_motion",
                    "start": round(current_start, 3),
                    "end": round(end, 3),
                    "duration": round(max(0.0, duration), 3),
                    "label": "freeze or near-static visual range",
                }
            )
            current_start = None
            current_duration = None

    return ranges


def run_ffmpeg(args: list[str]) -> str:
    proc = subprocess.run(
        [find_ffmpeg(), "-hide_banner", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return "\n".join(part for part in (proc.stdout, proc.stderr) if part)


def detect_scene_changes(video: Path, threshold: float) -> list[float]:
    log = run_ffmpeg(
        [
            "-i",
            str(video),
            "-vf",
            f"select=gt(scene\\,{threshold}),showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    return parse_scene_times(log)


def detect_freeze_ranges(video: Path, noise_db: float, min_duration: float) -> list[dict]:
    log = run_ffmpeg(
        [
            "-i",
            str(video),
            "-vf",
            f"freezedetect=n={noise_db}dB:d={min_duration}",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    return parse_freeze_ranges(log)


def extract_sample_frames(video: Path, frames_dir: Path, sample_interval: float, max_frames: int, width: int) -> list[Path]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old_frame in frames_dir.glob("frame_*.jpg"):
        old_frame.unlink()

    pattern = frames_dir / "frame_%06d.jpg"
    subprocess.run(
        [
            find_ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            f"fps=1/{sample_interval},scale={width}:-2",
            "-frames:v",
            str(max_frames),
            str(pattern),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(frames_dir.glob("frame_*.jpg"))


def active_ranges_from_freezes(duration: float, freezes: list[dict]) -> list[dict]:
    active: list[dict] = []
    cursor = 0.0
    for freeze in sorted(freezes, key=lambda item: float(item["start"])):
        start = max(0.0, float(freeze["start"]))
        end = min(duration, float(freeze["end"]))
        if start > cursor:
            active.append(
                {
                    "type": "visual_activity",
                    "start": round(cursor, 3),
                    "end": round(start, 3),
                    "duration": round(start - cursor, 3),
                    "label": "visual changes or motion detected between static ranges",
                }
            )
        cursor = max(cursor, end)
    if duration > cursor:
        active.append(
            {
                "type": "visual_activity",
                "start": round(cursor, 3),
                "end": round(duration, 3),
                "duration": round(duration - cursor, 3),
                "label": "visual changes or motion detected between static ranges",
            }
        )
    return active


def build_analysis(
    video: Path,
    edit_dir: Path,
    *,
    sample_interval: float,
    max_frames: int,
    frame_width: int,
    scene_threshold: float,
    freeze_noise_db: float,
    freeze_min_duration: float,
) -> dict:
    video = video.resolve()
    edit_dir = edit_dir.resolve()
    stem = safe_filename(video.stem)
    metadata = ffprobe(video)

    frames = extract_sample_frames(
        video,
        edit_dir / "video_frames" / stem,
        sample_interval=sample_interval,
        max_frames=max_frames,
        width=frame_width,
    )
    scene_times = detect_scene_changes(video, scene_threshold)
    freezes = detect_freeze_ranges(video, freeze_noise_db, freeze_min_duration)
    duration = float(metadata.get("duration") or 0.0)

    sampled_frames = [
        {
            "time": round((index - 1) * sample_interval, 3),
            "path": relative_to_edit(path, edit_dir),
            "label": "sampled frame for visual inspection",
        }
        for index, path in enumerate(frames, start=1)
    ]
    scene_changes = [
        {
            "type": "scene_change",
            "time": time,
            "label": "FFmpeg scene-change signal",
        }
        for time in scene_times
    ]

    return {
        "version": 1,
        "source": str(video),
        "source_name": video.stem,
        "duration": duration,
        "method": "ffmpeg-signal-analysis",
        "settings": {
            "sample_interval": sample_interval,
            "max_frames": max_frames,
            "frame_width": frame_width,
            "scene_threshold": scene_threshold,
            "freeze_noise_db": freeze_noise_db,
            "freeze_min_duration": freeze_min_duration,
        },
        "sampled_frames": sampled_frames,
        "scene_changes": scene_changes,
        "motion_ranges": active_ranges_from_freezes(duration, freezes),
        "low_motion_ranges": freezes,
        "observations": [],
        "limitations": [
            "No OCR, face recognition, object detection, or hosted vision model is run by default.",
            "Use sampled frames and optional observations for visible text, people, objects, and prompt-specific events.",
        ],
    }


def analysis_to_lines(data: dict, *, max_frames: int = 8, max_events: int = 16) -> list[str]:
    lines = [
        "Visual signals: FFmpeg scene/freeze detection with sampled frames. "
        "Use these alongside transcript text; inspect frame paths for visible events and on-screen text."
    ]

    observations = data.get("observations") or []
    if observations:
        lines.append("Observations:")
        for item in observations[:max_events]:
            start = float(item.get("start", item.get("time", 0.0)) or 0.0)
            end = item.get("end")
            prefix = f"[{fmt(start)}-{fmt(float(end))}]" if end is not None else f"[{fmt(start)}]"
            text = item.get("text") or item.get("label") or item.get("type") or "visual observation"
            lines.append(f" {prefix} {text}")

    frames = data.get("sampled_frames") or []
    if frames:
        lines.append("Sampled frames:")
        for frame in frames[:max_frames]:
            time = float(frame.get("time", 0.0) or 0.0)
            lines.append(f" [{fmt(time)}] frame {frame.get('path')}")
        if len(frames) > max_frames:
            lines.append(f" ... {len(frames) - max_frames} more sampled frame(s) in video analysis JSON")

    scenes = data.get("scene_changes") or []
    if scenes:
        times = ", ".join(fmt(float(scene.get("time", 0.0) or 0.0)) for scene in scenes[:max_events])
        suffix = f" (+{len(scenes) - max_events} more)" if len(scenes) > max_events else ""
        lines.append(f"Scene-change signals: {times}{suffix}")

    low_motion = data.get("low_motion_ranges") or []
    if low_motion:
        lines.append("Low-motion/static ranges:")
        for item in low_motion[:max_events]:
            lines.append(f" [{fmt(float(item['start']))}-{fmt(float(item['end']))}] {item.get('label', 'low motion')}")

    motion = data.get("motion_ranges") or []
    if motion:
        lines.append("Visual activity ranges:")
        for item in motion[:max_events]:
            lines.append(f" [{fmt(float(item['start']))}-{fmt(float(item['end']))}] {item.get('label', 'visual activity')}")

    if data.get("limitations"):
        lines.append(f"Limitations: {data['limitations'][0]}")

    return lines


def write_analysis_markdown(edit_dir: Path, analyses: list[dict]) -> Path:
    lines = ["# Video analysis", ""]
    for data in analyses:
        lines.append(f"## {data.get('source_name', 'source')}")
        lines.extend(analysis_to_lines(data, max_frames=12, max_events=24))
        lines.append("")
    out = edit_dir / "video_analysis.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def source_videos_from_media_index(edit_dir: Path) -> list[Path]:
    index_path = edit_dir / "media_index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"no videos provided and media index not found: {index_path}")
    media_index = read_json(index_path)
    videos = []
    for item in media_index.get("media") or []:
        if item.get("error"):
            continue
        path = item.get("path")
        if path:
            videos.append(Path(path))
    return videos


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze source video context into edit/video_analysis/*.json")
    parser.add_argument("videos", nargs="*", type=Path, help="Source video(s). Defaults to edit/media_index.json entries.")
    parser.add_argument("--edit-dir", type=Path, required=True)
    parser.add_argument("--sample-interval", type=float, default=5.0, help="Seconds between sampled frames")
    parser.add_argument("--max-frames", type=int, default=24, help="Maximum sampled frames per source")
    parser.add_argument("--frame-width", type=int, default=480, help="Width of sampled JPEG frames")
    parser.add_argument("--scene-threshold", type=float, default=0.35, help="FFmpeg scene threshold")
    parser.add_argument("--freeze-noise-db", type=float, default=-60.0, help="FFmpeg freezedetect noise threshold")
    parser.add_argument("--freeze-min-duration", type=float, default=2.0, help="Minimum static range duration")
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    videos = [path.resolve() for path in args.videos] if args.videos else source_videos_from_media_index(edit_dir)
    if not videos:
        raise SystemExit("no source videos found for analysis")

    analyses = []
    for video in videos:
        analysis = build_analysis(
            video,
            edit_dir,
            sample_interval=args.sample_interval,
            max_frames=args.max_frames,
            frame_width=args.frame_width,
            scene_threshold=args.scene_threshold,
            freeze_noise_db=args.freeze_noise_db,
            freeze_min_duration=args.freeze_min_duration,
        )
        out = edit_dir / "video_analysis" / f"{safe_filename(video.stem)}.json"
        write_json(out, analysis)
        analyses.append(analysis)
        print(f"analyzed {video.name} -> {out}")

    markdown = write_analysis_markdown(edit_dir, analyses)
    print(f"video analysis summary -> {markdown}")


if __name__ == "__main__":
    main()
