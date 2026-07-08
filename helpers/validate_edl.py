from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from helpers.common import ensure_within, read_json, resolve_relative, seconds_to_frames
from helpers.timing import range_playback_speed, range_timeline_duration


MIN_CLIP_DURATION_SECONDS = 0.8
SENTENCE_END_RE = re.compile(r"[.!?][\"')\]]*$")
PARTIAL_SPAN_TOLERANCE_SECONDS = 0.035
MAX_WARNING_TEXT_CHARS = 96


def _rect_payload_size(payload: dict) -> tuple[float, float] | None:
    if {"left", "top", "right", "bottom"}.issubset(payload):
        return float(payload["right"]) - float(payload["left"]), float(payload["bottom"]) - float(payload["top"])
    width = payload.get("width", payload.get("w"))
    height = payload.get("height", payload.get("h"))
    if width is None or height is None:
        return None
    return float(width), float(height)


def _validate_rect_payload(payload: object, prefix: str) -> list[str]:
    errors = []
    if not isinstance(payload, dict):
        return [f"{prefix} must be an object"]
    try:
        size = _rect_payload_size(payload)
    except (TypeError, ValueError):
        return [f"{prefix} values must be numeric"]
    if size is None:
        errors.append(f"{prefix} must include x/y/width/height or left/top/right/bottom")
    elif size[0] <= 0 or size[1] <= 0:
        errors.append(f"{prefix} width and height must be greater than 0")
    return errors


def _coerce_word(word: dict) -> dict | None:
    start = word.get("start")
    end = word.get("end")
    if start is None or end is None:
        return None
    return {"start": float(start), "end": float(end), "text": word.get("text", "")}


def load_transcript(edit_dir: Path, source_path: Path) -> dict:
    transcript_path = edit_dir / "transcripts" / f"{source_path.stem}.json"
    if not transcript_path.exists():
        return {"words": [], "segments": []}
    try:
        payload = read_json(transcript_path)
    except Exception:
        return {"words": [], "segments": []}

    words = []
    for word in payload.get("words", []):
        coerced = _coerce_word(word)
        if coerced:
            words.append(coerced)

    segments = []
    for segment in payload.get("segments", []):
        start = segment.get("start")
        end = segment.get("end")
        if start is None or end is None:
            continue
        segment_words = []
        for word in segment.get("words") or []:
            coerced = _coerce_word(word)
            if coerced:
                segment_words.append(coerced)
        if not segment_words:
            segment_words = [
                word
                for word in words
                if word["end"] > float(start) - PARTIAL_SPAN_TOLERANCE_SECONDS
                and word["start"] < float(end) + PARTIAL_SPAN_TOLERANCE_SECONDS
            ]
        segments.append(
            {
                "start": float(start),
                "end": float(end),
                "text": segment.get("text", ""),
                "words": segment_words,
            }
        )
    return {"words": words, "segments": segments}


def load_transcript_words(edit_dir: Path, source_path: Path) -> list[dict]:
    return load_transcript(edit_dir, source_path)["words"]


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


def sentence_ending_word(text: str) -> bool:
    return bool(SENTENCE_END_RE.search((text or "").strip()))


def _span_text(words: list[dict], fallback: str = "") -> str:
    text = " ".join((word.get("text") or "").strip() for word in words).strip() or fallback.strip()
    if len(text) <= MAX_WARNING_TEXT_CHARS:
        return text
    return f"{text[: MAX_WARNING_TEXT_CHARS - 3].rstrip()}..."


def _make_span(kind: str, words: list[dict], fallback_text: str = "") -> dict | None:
    if len(words) < 2:
        return None
    return {
        "kind": kind,
        "start": float(words[0]["start"]),
        "end": float(words[-1]["end"]),
        "text": _span_text(words, fallback_text),
        "words": words,
    }


def sentence_spans_from_words(words: list[dict]) -> list[dict]:
    """Return punctuation-backed sentence spans for partial-phrase QA.

    Whisper word timings usually preserve sentence punctuation on word text.
    If punctuation is absent, this returns no spans and segment spans are used
    instead to avoid treating an entire transcript as one sentence.
    """
    if not any(sentence_ending_word(word.get("text", "")) for word in words):
        return []

    spans = []
    current: list[dict] = []
    for word in words:
        current.append(word)
        if sentence_ending_word(word.get("text", "")):
            span = _make_span("sentence", current)
            if span:
                spans.append(span)
            current = []
    return spans


def segment_spans_from_transcript(segments: list[dict]) -> list[dict]:
    spans = []
    for segment in segments:
        span = _make_span("segment", segment.get("words") or [], segment.get("text", ""))
        if span:
            spans.append(span)
    return spans


def transcript_phrase_spans(words: list[dict], segments: list[dict]) -> list[dict]:
    sentence_spans = sentence_spans_from_words(words)
    if sentence_spans:
        return sentence_spans
    return segment_spans_from_transcript(segments)


def word_is_fully_covered(word: dict, ranges: list[dict], tolerance: float = PARTIAL_SPAN_TOLERANCE_SECONDS) -> bool:
    word_start = float(word["start"])
    word_end = float(word["end"])
    for item in ranges:
        range_start = float(item.get("source_start", 0))
        range_end = float(item.get("source_end", 0))
        if range_start - tolerance <= word_start and word_end <= range_end + tolerance:
            return True
    return False


def partial_phrase_warnings(
    spans: list[dict],
    ranges: list[dict],
    *,
    timeline_index: int,
    source_id: str,
) -> list[str]:
    warnings = []
    for span in spans:
        words = span.get("words") or []
        covered_words = [word for word in words if word_is_fully_covered(word, ranges)]
        omitted_words = [word for word in words if not word_is_fully_covered(word, ranges)]
        if not covered_words or not omitted_words:
            continue
        warnings.append(
            f"timelines[{timeline_index}].sources.{source_id} keeps only part of {span['kind']} "
            f"{span.get('text', '').strip()!r} ({span['start']:.3f}-{span['end']:.3f}); "
            f"omitted {len(omitted_words)}/{len(words)} words"
        )
    return warnings


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
        duration = range_timeline_duration(item)
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
            speed = range_playback_speed(item)
            if start < 0:
                errors.append(f"{item_prefix}.source_start must be >= 0")
            if end <= start:
                errors.append(f"{item_prefix}.source_end must be greater than source_start")
            if speed <= 0:
                errors.append(f"{item_prefix}.speed must be greater than 0")
            record_duration = item.get("record_duration", item.get("timeline_duration"))
            if record_duration is not None and float(record_duration) <= 0:
                errors.append(f"{item_prefix}.record_duration must be greater than 0")
            if float(item.get("record_start", 0)) < 0:
                errors.append(f"{item_prefix}.record_start must be >= 0")
            visual_layers = item.get("visual_layers")
            if visual_layers is not None:
                if not isinstance(visual_layers, list) or not visual_layers:
                    errors.append(f"{item_prefix}.visual_layers must be a non-empty list")
                else:
                    seen_lanes: set[int] = set()
                    for layer_index, layer in enumerate(visual_layers):
                        layer_prefix = f"{item_prefix}.visual_layers[{layer_index}]"
                        if not isinstance(layer, dict):
                            errors.append(f"{layer_prefix} must be an object")
                            continue
                        layer_source = layer.get("source", item.get("source"))
                        if layer_source not in sources:
                            errors.append(f"{layer_prefix}.source must reference a known source")
                        if layer.get("source_rect") is not None:
                            errors.extend(_validate_rect_payload(layer["source_rect"], f"{layer_prefix}.source_rect"))
                        if layer.get("crop") is not None:
                            errors.extend(_validate_rect_payload(layer["crop"], f"{layer_prefix}.crop"))
                        if layer.get("dest_rect") is None:
                            errors.append(f"{layer_prefix}.dest_rect is required")
                        else:
                            errors.extend(_validate_rect_payload(layer["dest_rect"], f"{layer_prefix}.dest_rect"))
                        lane_value = layer.get("lane", layer.get("track", layer_index + 1))
                        try:
                            lane_float = float(lane_value)
                            lane = int(lane_float)
                            if lane < 1 or lane != lane_float:
                                raise ValueError
                        except (TypeError, ValueError):
                            errors.append(f"{layer_prefix}.lane must be a positive integer")
                            continue
                        if lane in seen_lanes:
                            errors.append(f"{layer_prefix}.lane duplicates lane {lane} in the same range")
                        seen_lanes.add(lane)
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
        transcripts_by_source = {}
        for source_id, source_path in sources.items():
            resolved = resolve_relative(source_path, root)
            transcripts_by_source[source_id] = load_transcript(edit_dir, resolved)

        ranges = sorted(timeline.get("ranges") or [], key=lambda item: float(item.get("record_start", 0)))
        ranges_by_source: dict[str, list[dict]] = {}
        for range_index, item in enumerate(ranges):
            source_id = item.get("source")
            if source_id:
                ranges_by_source.setdefault(source_id, []).append(item)
            transcript = transcripts_by_source.get(source_id, {})
            words = transcript.get("words", [])
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
        for source_id, source_ranges in ranges_by_source.items():
            transcript = transcripts_by_source.get(source_id, {})
            spans = transcript_phrase_spans(transcript.get("words", []), transcript.get("segments", []))
            warnings.extend(
                partial_phrase_warnings(
                    spans,
                    source_ranges,
                    timeline_index=timeline_index,
                    source_id=source_id,
                )
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
