from __future__ import annotations

import argparse
import sys
from pathlib import Path

from helpers.common import ensure_within, read_json, resolve_relative


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


def validate(edl_path: Path) -> list[str]:
    errors = []
    edl = read_json(edl_path)
    root = edl_path.parent.parent

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

    return errors


def cut_quality_warnings(edl_path: Path) -> list[str]:
    warnings = []
    edl = read_json(edl_path)
    root = edl_path.parent.parent
    edit_dir = edl_path.parent

    for timeline_index, timeline in enumerate(edl.get("timelines") or []):
        sources = timeline.get("sources", {})
        words_by_source = {}
        for source_id, source_path in sources.items():
            resolved = resolve_relative(source_path, root)
            words_by_source[source_id] = load_transcript_words(edit_dir, resolved)

        previous_by_track: dict[int, dict] = {}
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

            track = int(item.get("track", 1))
            previous = previous_by_track.get(track)
            if previous is not None:
                gap = float(item.get("record_start", 0)) - (
                    float(previous.get("record_start", 0))
                    + float(previous.get("source_end", 0))
                    - float(previous.get("source_start", 0))
                )
                if 0.0 < gap < 0.08:
                    warnings.append(
                        f"timelines[{timeline_index}].ranges[{range_index}] leaves a very short "
                        f"{gap:.3f}s record gap; consider closing it or making the pause intentional"
                    )
            previous_by_track[track] = item

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
