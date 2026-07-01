from __future__ import annotations

import argparse
from array import array
import math
from pathlib import Path
import subprocess
import sys

from helpers.common import ensure_within, read_json, resolve_relative, write_json
from helpers.media_tools import find_ffmpeg, media_duration
from helpers.timing import range_playback_speed, range_timeline_duration
from helpers.validate_edl import validate


DEFAULT_THRESHOLD_DB = -45.0
DEFAULT_SEARCH_WINDOW_SECONDS = 0.35
DEFAULT_BOUNDARY_BRIDGE_SECONDS = 0.08
DEFAULT_GUARD_SECONDS = 0.06
DEFAULT_FRAME_MS = 10.0
DEFAULT_SAMPLE_RATE = 16_000


def default_report_path(edl_path: Path) -> Path:
    return edl_path.parent / "qa" / "audio_refine_report.json"


def default_output_path(edl_path: Path) -> Path:
    return edl_path.with_name(f"{edl_path.stem}.audio-refined{edl_path.suffix}")


def parse_threshold_db(value: str | float | int) -> float:
    if isinstance(value, int | float):
        return float(value)
    normalized = value.strip().lower().replace("dbfs", "").replace("db", "")
    return float(normalized)


def decode_audio_window(source: Path, start: float, end: float, *, sample_rate: int = DEFAULT_SAMPLE_RATE) -> array:
    duration = max(0.0, end - start)
    if duration <= 0:
        return array("h")

    cmd = [
        find_ffmpeg(),
        "-v",
        "error",
        "-ss",
        f"{max(0.0, start):.6f}",
        "-t",
        f"{duration:.6f}",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace").strip() or "ffmpeg audio decode failed")

    samples = array("h")
    samples.frombytes(proc.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def frame_rms(samples: array, start: int, end: int) -> float:
    frame = samples[start:end]
    if not frame:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in frame) / len(frame)) / 32768.0


def audio_activity_segments(
    source: Path,
    start: float,
    end: float,
    *,
    threshold_db: float = DEFAULT_THRESHOLD_DB,
    frame_ms: float = DEFAULT_FRAME_MS,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    merge_gap_seconds: float = 0.02,
) -> list[dict]:
    samples = decode_audio_window(source, start, end, sample_rate=sample_rate)
    if not samples:
        return []

    threshold = 10 ** (threshold_db / 20.0)
    frame_size = max(1, int(sample_rate * frame_ms / 1000.0))
    segments = []
    current_start: float | None = None
    current_end: float | None = None

    for frame_start in range(0, len(samples), frame_size):
        frame_end = min(len(samples), frame_start + frame_size)
        if frame_rms(samples, frame_start, frame_end) < threshold:
            continue

        absolute_start = start + frame_start / sample_rate
        absolute_end = start + frame_end / sample_rate
        if current_start is None:
            current_start = absolute_start
            current_end = absolute_end
            continue
        if current_end is not None and absolute_start - current_end > merge_gap_seconds:
            segments.append({"start": current_start, "end": current_end})
            current_start = absolute_start
        current_end = absolute_end

    if current_start is not None and current_end is not None:
        segments.append({"start": current_start, "end": current_end})
    return segments


def segment_near_boundary(segments: list[dict], boundary: float, bridge_seconds: float) -> dict | None:
    for segment in segments:
        if float(segment["start"]) <= boundary + bridge_seconds and float(segment["end"]) >= boundary - bridge_seconds:
            return segment
    return None


def refine_range_with_audio(
    source: Path,
    item: dict,
    *,
    source_duration: float,
    threshold_db: float = DEFAULT_THRESHOLD_DB,
    search_window: float = DEFAULT_SEARCH_WINDOW_SECONDS,
    bridge_seconds: float = DEFAULT_BOUNDARY_BRIDGE_SECONDS,
    guard_seconds: float = DEFAULT_GUARD_SECONDS,
) -> dict:
    start = float(item["source_start"])
    end = float(item["source_end"])
    refined_start = start
    refined_end = end

    start_segments = audio_activity_segments(
        source,
        max(0.0, start - search_window),
        min(source_duration, start + bridge_seconds),
        threshold_db=threshold_db,
    )
    start_segment = segment_near_boundary(start_segments, start, bridge_seconds)
    if start_segment and float(start_segment["start"]) < start:
        refined_start = max(0.0, float(start_segment["start"]) - guard_seconds)

    end_segments = audio_activity_segments(
        source,
        max(0.0, end - bridge_seconds),
        min(source_duration, end + search_window),
        threshold_db=threshold_db,
    )
    end_segment = segment_near_boundary(end_segments, end, bridge_seconds)
    if end_segment and float(end_segment["end"]) > end:
        refined_end = min(source_duration, float(end_segment["end"]) + guard_seconds)

    if refined_end <= refined_start:
        return dict(item)

    refined = dict(item)
    refined["source_start"] = round(refined_start, 3)
    refined["source_end"] = round(refined_end, 3)
    if "record_duration" in refined:
        refined["record_duration"] = round((refined["source_end"] - refined["source_start"]) / range_playback_speed(refined), 3)
    if "timeline_duration" in refined:
        refined["timeline_duration"] = round((refined["source_end"] - refined["source_start"]) / range_playback_speed(refined), 3)
    return refined


def retime_record_starts(timeline: dict) -> None:
    record_start = 0.0
    for item in sorted(timeline.get("ranges") or [], key=lambda value: float(value.get("record_start", 0.0))):
        item["record_start"] = round(record_start, 3)
        record_start += range_timeline_duration(item)


def refine_edl_audio_cuts(
    edl_path: Path,
    *,
    out_path: Path | None = None,
    report_path: Path | None = None,
    threshold_db: float = DEFAULT_THRESHOLD_DB,
    search_window: float = DEFAULT_SEARCH_WINDOW_SECONDS,
    bridge_seconds: float = DEFAULT_BOUNDARY_BRIDGE_SECONDS,
    guard_seconds: float = DEFAULT_GUARD_SECONDS,
) -> dict:
    edl_path = edl_path.resolve()
    output = (out_path or default_output_path(edl_path)).resolve()
    report_output = (report_path or default_report_path(edl_path)).resolve()
    root = edl_path.parent.parent
    edl = read_json(edl_path)
    duration_cache: dict[Path, float] = {}
    changes = []

    for timeline_index, timeline in enumerate(edl.get("timelines") or []):
        sources = timeline.get("sources") or {}
        resolved_sources: dict[str, Path] = {}
        for source_id, source_path in sources.items():
            resolved = resolve_relative(source_path, root)
            ensure_within(resolved, root)
            resolved_sources[source_id] = resolved

        for range_index, item in enumerate(timeline.get("ranges") or []):
            source_id = item.get("source")
            source = resolved_sources.get(source_id)
            if source is None:
                continue
            if source not in duration_cache:
                duration_cache[source] = float(media_duration(source) or 0.0)
            source_duration = duration_cache[source]
            if source_duration <= 0:
                continue

            old_start = float(item["source_start"])
            old_end = float(item["source_end"])
            refined = refine_range_with_audio(
                source,
                item,
                source_duration=source_duration,
                threshold_db=threshold_db,
                search_window=search_window,
                bridge_seconds=bridge_seconds,
                guard_seconds=guard_seconds,
            )
            item.update(refined)
            if float(item["source_start"]) != old_start or float(item["source_end"]) != old_end:
                changes.append(
                    {
                        "timeline_index": timeline_index,
                        "range_index": range_index,
                        "source": source_id,
                        "old_source_start": old_start,
                        "new_source_start": item["source_start"],
                        "old_source_end": old_end,
                        "new_source_end": item["source_end"],
                    }
                )
        retime_record_starts(timeline)

    write_json(output, edl)
    validation_errors = validate(output)
    report = {
        "edl": str(edl_path),
        "output": str(output),
        "threshold_db": threshold_db,
        "search_window": search_window,
        "bridge_seconds": bridge_seconds,
        "guard_seconds": guard_seconds,
        "changes": changes,
        "change_count": len(changes),
        "validation_errors": validation_errors,
    }
    write_json(report_output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Refine EDL cut boundaries using source audio activity")
    parser.add_argument("edl", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="Output EDL path; defaults to edl.audio-refined.json")
    parser.add_argument("--replace", action="store_true", help="Overwrite the input EDL")
    parser.add_argument("--report", type=Path, default=None, help="QA report path; defaults to edit/qa/audio_refine_report.json")
    parser.add_argument("--threshold-db", default=str(DEFAULT_THRESHOLD_DB), help="RMS activity threshold in dBFS")
    parser.add_argument("--search-window", type=float, default=DEFAULT_SEARCH_WINDOW_SECONDS)
    parser.add_argument("--bridge-seconds", type=float, default=DEFAULT_BOUNDARY_BRIDGE_SECONDS)
    parser.add_argument("--guard-seconds", type=float, default=DEFAULT_GUARD_SECONDS)
    args = parser.parse_args()

    if args.replace and args.out:
        raise SystemExit("--replace and --out are mutually exclusive")

    edl_path = args.edl.resolve()
    out_path = edl_path if args.replace else args.out
    report = refine_edl_audio_cuts(
        edl_path,
        out_path=out_path,
        report_path=args.report,
        threshold_db=parse_threshold_db(args.threshold_db),
        search_window=args.search_window,
        bridge_seconds=args.bridge_seconds,
        guard_seconds=args.guard_seconds,
    )
    print(f"audio-refined EDL -> {report['output']} ({report['change_count']} changed ranges)")
    if report["validation_errors"]:
        for error in report["validation_errors"]:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
