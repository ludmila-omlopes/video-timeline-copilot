from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from helpers.common import read_json, safe_filename, write_json
from helpers.inventory import ffprobe
from helpers.media_tools import find_ffmpeg


STYLE_DEFAULTS = {
    "social": {"padding": 0.12, "min_silence": 0.35, "min_segment": 0.45, "merge_gap": 0.18},
    "documentary": {"padding": 0.25, "min_silence": 0.7, "min_segment": 0.8, "merge_gap": 0.35},
    "highlight": {"padding": 0.18, "min_silence": 0.5, "min_segment": 0.6, "merge_gap": 0.25},
    "longform": {"padding": 0.35, "min_silence": 0.9, "min_segment": 1.0, "merge_gap": 0.5},
}


def parse_frame_rate(value: str | None) -> float:
    if not value:
        return 30.0
    if "/" not in value:
        return float(value)
    numerator, denominator = value.split("/", 1)
    den = float(denominator)
    return float(numerator) / den if den else 30.0


def source_path_for_edl(video: Path, footage_root: Path) -> str:
    try:
        return video.resolve().relative_to(footage_root.resolve()).as_posix()
    except ValueError:
        return str(video.resolve())


def detect_silences(video: Path, noise: str, duration: float) -> list[dict]:
    cmd = [
        find_ffmpeg(),
        "-hide_banner",
        "-nostats",
        "-i",
        str(video),
        "-af",
        f"silencedetect=noise={noise}:duration={duration}",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"ffmpeg silencedetect failed with exit code {proc.returncode}")

    silences: list[dict] = []
    current_start: float | None = None
    for line in proc.stderr.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            current_start = float(start_match.group(1))
            continue

        end_match = re.search(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", line)
        if end_match:
            end = float(end_match.group(1))
            detected_duration = float(end_match.group(2))
            start = current_start if current_start is not None else max(0.0, end - detected_duration)
            silences.append({"start": start, "end": end, "duration": detected_duration})
            current_start = None
    return silences


def complement_silences(silences: list[dict], total_duration: float) -> list[dict]:
    speech = []
    cursor = 0.0
    for silence in sorted(silences, key=lambda item: item["start"]):
        start = max(0.0, min(total_duration, float(silence["start"])))
        end = max(0.0, min(total_duration, float(silence["end"])))
        if start > cursor:
            speech.append({"start": cursor, "end": start})
        cursor = max(cursor, end)
    if cursor < total_duration:
        speech.append({"start": cursor, "end": total_duration})
    return speech


def load_words(edit_dir: Path, video: Path) -> list[dict]:
    transcript = edit_dir / "transcripts" / f"{video.stem}.json"
    if not transcript.exists():
        return []
    data = read_json(transcript)
    words = []
    for word in data.get("words", []):
        start = word.get("start")
        end = word.get("end")
        if start is None or end is None:
            continue
        words.append({"start": float(start), "end": float(end), "text": word.get("text", "")})
    return words


def snap_to_words(ranges: list[dict], words: list[dict], padding: float, total_duration: float) -> list[dict]:
    if not words:
        return ranges

    snapped = []
    for item in ranges:
        overlapped = [w for w in words if w["end"] >= item["start"] and w["start"] <= item["end"]]
        if not overlapped:
            snapped.append(item)
            continue
        start = max(0.0, overlapped[0]["start"] - padding)
        end = min(total_duration, overlapped[-1]["end"] + padding)
        if end > start:
            snapped.append({"start": start, "end": end})
    return snapped


def pad_ranges(ranges: list[dict], padding: float, total_duration: float) -> list[dict]:
    return [
        {"start": max(0.0, item["start"] - padding), "end": min(total_duration, item["end"] + padding)}
        for item in ranges
        if item["end"] > item["start"]
    ]


def merge_ranges(ranges: list[dict], merge_gap: float, min_segment: float) -> list[dict]:
    merged: list[dict] = []
    for item in sorted(ranges, key=lambda value: value["start"]):
        if item["end"] - item["start"] < min_segment:
            continue
        if merged and item["start"] - merged[-1]["end"] <= merge_gap:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        else:
            merged.append(dict(item))
    return merged


def draft_ranges(
    video: Path,
    edit_dir: Path,
    *,
    noise: str,
    min_silence: float,
    padding: float,
    min_segment: float,
    merge_gap: float,
    word_snap: bool,
) -> tuple[list[dict], list[dict], float]:
    media_info = ffprobe(video)
    total_duration = float(media_info.get("duration") or 0.0)
    silences = detect_silences(video, noise, min_silence)
    ranges = complement_silences(silences, total_duration)
    ranges = pad_ranges(ranges, padding, total_duration)
    if word_snap:
        ranges = snap_to_words(ranges, load_words(edit_dir, video), padding, total_duration)
    ranges = merge_ranges(ranges, merge_gap, min_segment)
    return ranges, silences, total_duration


def build_edl(
    video: Path,
    footage_root: Path,
    edit_dir: Path,
    ranges: list[dict],
    *,
    project_name: str,
    timeline_name: str,
    style: str,
    settings: dict,
) -> dict:
    media_info = ffprobe(video)
    fps = parse_frame_rate(media_info.get("avg_frame_rate"))
    width = int(media_info.get("width") or 1920)
    height = int(media_info.get("height") or 1080)
    record_start = 0.0
    edl_ranges = []
    for index, item in enumerate(ranges, start=1):
        start = round(float(item["start"]), 3)
        end = round(float(item["end"]), 3)
        edl_ranges.append(
            {
                "source": "A001",
                "source_start": start,
                "source_end": end,
                "record_start": round(record_start, 3),
                "track": 1,
                "beat": f"SPEECH_{index:03d}",
                "quote": "",
                "reason": "Draft silence cut kept this range as likely speech/audio activity.",
            }
        )
        record_start += end - start

    return {
        "version": 1,
        "project_name": project_name,
        "fps": fps,
        "archive_project": True,
        "metadata": {
            "draft_helper": "draft-silence-cut",
            "cut_style": style,
            "silence_cut_settings": settings,
        },
        "timelines": [
            {
                "name": timeline_name,
                "resolution": [width, height],
                "sources": {"A001": source_path_for_edl(video, footage_root)},
                "ranges": edl_ranges,
                "subtitles": {
                    "mode": "srt",
                    "path": f"edit/subtitles/{safe_filename(timeline_name, 'Silence_Cut')}.srt",
                },
                "markers": True,
            }
        ],
    }


def normalize_negative_noise_arg(argv: list[str]) -> list[str]:
    normalized = []
    index = 0
    while index < len(argv):
        if argv[index] == "--noise" and index + 1 < len(argv) and argv[index + 1].startswith("-"):
            normalized.append(f"--noise={argv[index + 1]}")
            index += 2
            continue
        normalized.append(argv[index])
        index += 1
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a deterministic draft EDL by removing detected silence")
    parser.add_argument("video", type=Path, help="Source video/audio file")
    parser.add_argument("--edit-dir", type=Path, default=None, help="Output edit directory")
    parser.add_argument("--out", type=Path, default=None, help="Output EDL path")
    parser.add_argument("--style", choices=sorted(STYLE_DEFAULTS), default="documentary")
    parser.add_argument("--noise", default="-35dB", help="FFmpeg silencedetect noise threshold, e.g. -35dB")
    parser.add_argument("--min-silence", type=float, default=None, help="Minimum silence duration in seconds")
    parser.add_argument("--padding", type=float, default=None, help="Pre/post roll kept around speech in seconds")
    parser.add_argument("--min-segment", type=float, default=None, help="Drop kept ranges shorter than this many seconds")
    parser.add_argument("--merge-gap", type=float, default=None, help="Merge kept ranges separated by this many seconds or less")
    parser.add_argument("--no-word-snap", action="store_true", help="Do not use transcript word timings to adjust cut points")
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--timeline-name", default=None)
    args = parser.parse_args(normalize_negative_noise_arg(sys.argv[1:]))

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"source not found: {video}")

    default_edit_dir = video.parent.parent / "edit" if video.parent.name == "raw" else video.parent / "edit"
    edit_dir = (args.edit_dir or default_edit_dir).resolve()
    footage_root = edit_dir.parent.resolve()
    defaults = STYLE_DEFAULTS[args.style]
    settings = {
        "detector": "ffmpeg silencedetect",
        "noise": args.noise,
        "min_silence": args.min_silence if args.min_silence is not None else defaults["min_silence"],
        "padding": args.padding if args.padding is not None else defaults["padding"],
        "min_segment": args.min_segment if args.min_segment is not None else defaults["min_segment"],
        "merge_gap": args.merge_gap if args.merge_gap is not None else defaults["merge_gap"],
        "word_snap": not args.no_word_snap,
    }
    ranges, silences, total_duration = draft_ranges(
        video,
        edit_dir,
        noise=settings["noise"],
        min_silence=settings["min_silence"],
        padding=settings["padding"],
        min_segment=settings["min_segment"],
        merge_gap=settings["merge_gap"],
        word_snap=settings["word_snap"],
    )
    if not ranges:
        sys.exit("no kept ranges were detected; lower --noise or --min-silence and retry")

    project_name = args.project_name or f"{video.stem}_Silence_Cut"
    timeline_name = args.timeline_name or f"Silence Cut - {args.style}"
    edl = build_edl(
        video,
        footage_root,
        edit_dir,
        ranges,
        project_name=project_name,
        timeline_name=timeline_name,
        style=args.style,
        settings=settings,
    )
    out_path = (args.out or edit_dir / "edl.json").resolve()
    write_json(out_path, edl)
    kept_duration = sum(item["end"] - item["start"] for item in ranges)
    print(
        f"wrote draft silence-cut EDL -> {out_path} "
        f"({len(ranges)} kept ranges, {kept_duration:0.1f}s kept from {total_duration:0.1f}s, {len(silences)} silences)"
    )


if __name__ == "__main__":
    main()
