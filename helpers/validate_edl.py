from __future__ import annotations

import argparse
import sys
from pathlib import Path

from helpers.common import ensure_within, read_json, resolve_relative, seconds_to_frames


MIN_CLIP_DURATION_SECONDS = 0.8


def load_transcript_words(edit_dir: Path, source_path: Path) -> list[dict]:
    transcript_path = edit_dir / "transcripts" / f"{source_path.stem}.json"
    if not transcript_path.exists():
        return []
    try:
        payload = read_json(transcript_path)
    except Exception:
        return []
    words = []
    for word in payload.get("words", []):
        start = word.get("start")
        end = word.get("end")
        if start is None or end is None:
            continue
        words.append({"start": float(start), "end": float(end), "text": word.get("text", "")})
    return words


def cut_inside_word(cut_time: float, words: list[dict], tolerance: float = 0.025) -> dict | None:
    for word in words:
        if word["start"] + tolerance < cut_time < word["end"] - tolerance:
            return word
    return None


def transcript_gaps_in_range(words: list[dict], start: float, end: float, max_word_gap: float) -> list[dict]:
    overlapped = sorted(
        [word for word in words if word["end"] > start and word["start"] < end],
        key=lambda word: float(word["start"]),
    )
    gaps = []
    for previous, current in zip(overlapped, overlapped[1:]):
        gap_start = float(previous["end"])
        gap_end = float(current["start"])
        duration = gap_end - gap_start
        if duration > max_word_gap:
            gaps.append({"start": gap_start, "end": gap_end, "duration": duration})
    return gaps


def minimum_clip_duration(edl: dict) -> float:
    metadata = edl.get("metadata") or {}
    settings = metadata.get("silence_cut_settings") or {}
    configured = metadata.get("min_clip_duration", settings.get("min_segment", MIN_CLIP_DURATION_SECONDS))
    return max(MIN_CLIP_DURATION_SECONDS, float(configured))


def timeline_timing_issues(timeline: dict, fps: float, min_clip_duration: float) -> dict[str, list[dict]]:
    cursor_frames = 0
    cursor_seconds = 0.0
    min_clip_frames = max(1, seconds_to_frames(min_clip_duration, fps))
    issues: dict[str, list[dict]] = {"gaps": [], "overlaps": [], "short_clips": []}

    ranges = sorted(
        enumerate(timeline.get("ranges") or []),
        key=lambda pair: float(pair[1].get("record_start", 0.0)),
    )
    for original_index, item in ranges:
        record_start = float(item.get("record_start", cursor_seconds))
        record_start_frames = seconds_to_frames(record_start, fps)
        source_start = float(item["source_start"])
        source_end = float(item["source_end"])
        duration = source_end - source_start
        duration_frames = seconds_to_frames(duration, fps)

        if duration_frames < min_clip_frames:
            issues["short_clips"].append(
                {
                    "range_index": original_index,
                    "record_start": record_start,
                    "source_start": source_start,
                    "source_end": source_end,
                    "duration": duration,
                    "minimum_duration": min_clip_duration,
                }
            )

        if record_start_frames > cursor_frames:
            gap_frames = record_start_frames - cursor_frames
            issues["gaps"].append(
                {
                    "range_index": original_index,
                    "record_start": cursor_frames / fps,
                    "record_end": record_start_frames / fps,
                    "duration": gap_frames / fps,
                    "frames": gap_frames,
                }
            )
        elif record_start_frames < cursor_frames:
            overlap_frames = cursor_frames - record_start_frames
            issues["overlaps"].append(
                {
                    "range_index": original_index,
                    "record_start": record_start,
                    "record_end": cursor_frames / fps,
                    "duration": overlap_frames / fps,
                    "frames": overlap_frames,
                }
            )

        cursor_frames = max(cursor_frames, record_start_frames + max(0, duration_frames))
        cursor_seconds = cursor_frames / fps

    return issues


def validate(edl_path: Path) -> list[str]:
    errors = []
    edl = read_json(edl_path)
    root = edl_path.parent.parent
    fps = float(edl.get("fps", 0) or 0)
    min_clip_duration = minimum_clip_duration(edl)

    if edl.get("version") != 1:
        errors.append("version must be 1")
    if not edl.get("project_name"):
        errors.append("project_name is required")
    if any(sep in str(edl.get("project_name", "")) for sep in ("/", "\\")):
        errors.append("project_name must not contain path separators")
    if float(edl.get("fps", 0)) <= 0:
        errors.append("fps must be positive")

    timelines = edl.get("timelines")
    if not isinstance(timelines, list) or not timelines:
        errors.append("timelines must be a non-empty list")
        return errors

    for timeline_index, timeline in enumerate(timelines):
        prefix = f"timelines[{timeline_index}]"
        resolution = timeline.get("resolution")
        if not isinstance(resolution, list) or len(resolution) != 2:
            errors.append(f"{prefix}.resolution must be [width, height]")
        sources = timeline.get("sources", {})
        if not isinstance(sources, dict) or not sources:
            errors.append(f"{prefix}.sources must be a non-empty object")
        for source_id, source_path in sources.items():
            resolved = resolve_relative(source_path, root)
            try:
                ensure_within(resolved, root)
            except ValueError as exc:
                errors.append(f"{prefix}.sources.{source_id} {exc}")
                continue
            if not resolved.exists():
                errors.append(f"{prefix}.sources.{source_id} does not exist: {resolved}")
        subtitle_path = (timeline.get("subtitles") or {}).get("path")
        if subtitle_path:
            try:
                ensure_within(resolve_relative(subtitle_path, root), root)
            except ValueError as exc:
                errors.append(f"{prefix}.subtitles.path {exc}")
        ranges = timeline.get("ranges")
        if not isinstance(ranges, list) or not ranges:
            errors.append(f"{prefix}.ranges must be a non-empty list")
            continue
        for range_index, item in enumerate(ranges):
            item_prefix = f"{prefix}.ranges[{range_index}]"
            media_type = item.get("media_type", item.get("kind", "av"))
            if media_type not in ("av", "audio_video", None):
                errors.append(f"{item_prefix}.media_type must be av; audio-only/video-only ranges are not supported")
            if item.get("source") not in sources:
                errors.append(f"{item_prefix}.source must reference a known source")
            start = float(item.get("source_start", -1))
            end = float(item.get("source_end", -1))
            if start < 0:
                errors.append(f"{item_prefix}.source_start must be >= 0")
            if end <= start:
                errors.append(f"{item_prefix}.source_end must be greater than source_start")
            if float(item.get("record_start", 0)) < 0:
                errors.append(f"{item_prefix}.record_start must be >= 0")
        if fps > 0 and not any(error.startswith(prefix) for error in errors):
            timing_issues = timeline_timing_issues(timeline, fps, min_clip_duration)
            for gap in timing_issues["gaps"]:
                errors.append(
                    f"{prefix}.ranges[{gap['range_index']}] leaves a {gap['duration']:.3f}s record gap "
                    f"({gap['record_start']:.3f}-{gap['record_end']:.3f}); record_start must be contiguous"
                )
            for overlap in timing_issues["overlaps"]:
                errors.append(
                    f"{prefix}.ranges[{overlap['range_index']}] overlaps the previous clip by "
                    f"{overlap['duration']:.3f}s; record_start must be contiguous"
                )
            for short_clip in timing_issues["short_clips"]:
                errors.append(
                    f"{prefix}.ranges[{short_clip['range_index']}] duration {short_clip['duration']:.3f}s "
                    f"is shorter than the minimum {short_clip['minimum_duration']:.3f}s"
                )

    return errors


def cut_quality_warnings(edl_path: Path) -> list[str]:
    warnings = []
    edl = read_json(edl_path)
    root = edl_path.parent.parent
    edit_dir = edl_path.parent
    settings = ((edl.get("metadata") or {}).get("silence_cut_settings") or {})
    max_word_gap = float(settings.get("max_word_gap", 0.8))

    for timeline_index, timeline in enumerate(edl.get("timelines") or []):
        sources = timeline.get("sources", {})
        words_by_source = {}
        for source_id, source_path in sources.items():
            resolved = resolve_relative(source_path, root)
            words_by_source[source_id] = load_transcript_words(edit_dir, resolved)

        ranges = sorted(timeline.get("ranges") or [], key=lambda item: float(item.get("record_start", 0)))
        for range_index, item in enumerate(ranges):
            source_id = item.get("source")
            words = words_by_source.get(source_id, [])
            if words:
                for key in ("source_start", "source_end"):
                    cut = float(item.get(key, 0))
                    word = cut_inside_word(cut, words)
                    if word:
                        warnings.append(
                            f"timelines[{timeline_index}].ranges[{range_index}].{key} cuts inside word "
                            f"{word.get('text', '').strip()!r} ({word['start']:.3f}-{word['end']:.3f})"
                        )
                for gap in transcript_gaps_in_range(
                    words,
                    float(item.get("source_start", 0)),
                    float(item.get("source_end", 0)),
                    max_word_gap,
                ):
                    warnings.append(
                        f"timelines[{timeline_index}].ranges[{range_index}] keeps a long "
                        f"{gap['duration']:.3f}s transcript gap ({gap['start']:.3f}-{gap['end']:.3f}); "
                        "split or trim the range when removing silence"
                    )

    return warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate video-timeline-copilot EDL JSON")
    parser.add_argument("edl", type=Path)
    args = parser.parse_args()

    errors = validate(args.edl.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    for warning in cut_quality_warnings(args.edl.resolve()):
        print(f"WARNING: {warning}")
    print(f"valid EDL: {args.edl}")


if __name__ == "__main__":
    main()
