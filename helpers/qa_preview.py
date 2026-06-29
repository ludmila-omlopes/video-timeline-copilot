from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from helpers.common import ensure_within, read_json, resolve_relative, write_json
from helpers.export_fcpxml import timeline_duration
from helpers.media_tools import find_ffmpeg, media_duration, stream_types
from helpers.render_preview import preview_path
from helpers.timing import range_timeline_duration
from helpers.transforms import transform_coverage_issue
from helpers.validate_edl import minimum_clip_duration, timeline_timing_issues


def default_report_path(edl_path: Path) -> Path:
    return edl_path.parent / "qa" / "preview_report.json"


def default_contact_sheet_path(edl_path: Path) -> Path:
    return edl_path.parent / "qa" / "contact_sheet.jpg"


def build_contact_sheet(preview: Path, out_path: Path, samples: int = 12) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = media_duration(preview) or 0.0
    if duration <= 0:
        return False
    interval = max(duration / samples, 0.001)
    cmd = [
        find_ffmpeg(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(preview),
        "-vf",
        f"fps=1/{interval},scale=320:-1,tile=4x3",
        "-frames:v",
        "1",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return True


def qa_preview(
    edl_path: Path,
    preview: Path | None = None,
    report_path: Path | None = None,
    contact_sheet_path: Path | None = None,
    timeline_name: str | None = None,
) -> dict:
    edl = read_json(edl_path)
    root = edl_path.parent.parent
    timelines = edl.get("timelines") or []
    if not timelines:
        raise ValueError("EDL has no timelines")
    timeline = next((item for item in timelines if item.get("name") == timeline_name), timelines[0]) if timeline_name else timelines[0]
    if timeline_name and timeline.get("name") != timeline_name:
        raise ValueError(f"timeline not found: {timeline_name}")

    preview_file = (preview or preview_path(edl_path, edl, timeline)).resolve()
    report_file = (report_path or default_report_path(edl_path)).resolve()
    sheet_file = (contact_sheet_path or default_contact_sheet_path(edl_path)).resolve()

    expected_duration = timeline_duration(timeline)
    actual_duration = media_duration(preview_file) if preview_file.exists() else None
    duration_delta = actual_duration - expected_duration if actual_duration is not None else None

    audio_only_regions = []
    video_only_regions = []
    source_stream_cache: dict[str, set[str]] = {}
    min_clip_duration = minimum_clip_duration(edl)
    timing_issues = timeline_timing_issues(timeline, float(edl["fps"]), min_clip_duration)
    gaps = timing_issues["gaps"]
    overlaps = timing_issues["overlaps"]
    short_clips = timing_issues["short_clips"]
    transform_coverage_issues = []
    width, height = [int(value) for value in timeline["resolution"]]
    timeline_index = next(index for index, item in enumerate(timelines) if item is timeline)
    cursor = 0.0
    for index, item in enumerate(sorted(timeline.get("ranges") or [], key=lambda value: float(value.get("record_start", 0.0)))):
        record_start = float(item.get("record_start", cursor))
        source_start = float(item["source_start"])
        source_end = float(item["source_end"])
        duration = range_timeline_duration(item)

        source_id = item.get("source")
        source_path = ensure_within(resolve_relative(timeline["sources"][source_id], root), root)
        cache_key = str(source_path)
        if cache_key not in source_stream_cache:
            source_stream_cache[cache_key] = stream_types(source_path)
        types = source_stream_cache[cache_key]
        region = {
            "range_index": index,
            "source": source_id,
            "record_start": record_start,
            "record_end": record_start + duration,
            "source_start": source_start,
            "source_end": source_end,
        }
        media_type = item.get("media_type", item.get("kind", "av"))
        if media_type in {"audio", "audio-only", "audio_only"} or "video" not in types:
            audio_only_regions.append(region)
        if media_type in {"video", "video-only", "video_only"} or "audio" not in types:
            video_only_regions.append(region)
        coverage_issue = transform_coverage_issue(timeline_index, index, item, width, height)
        if coverage_issue is not None:
            transform_coverage_issues.append(coverage_issue)
        cursor = max(cursor, record_start + duration)

    contact_sheet_created = False
    if preview_file.exists():
        contact_sheet_created = build_contact_sheet(preview_file, sheet_file)

    checks = {
        "preview_exists": preview_file.exists(),
        "duration_matches_edl": duration_delta is not None and abs(duration_delta) <= max(0.1, 1 / float(edl["fps"])),
        "audio_only_regions_found": bool(audio_only_regions),
        "video_only_regions_found": bool(video_only_regions),
        "record_gaps_found": bool(gaps),
        "record_overlaps_found": bool(overlaps),
        "short_clips_found": bool(short_clips),
        "transform_coverage_ok": not transform_coverage_issues,
        "empty_space_risk_found": bool(transform_coverage_issues),
        "contact_sheet_created": contact_sheet_created,
    }
    report = {
        "edl": str(edl_path),
        "timeline": timeline.get("name"),
        "preview": str(preview_file),
        "contact_sheet": str(sheet_file) if contact_sheet_created else None,
        "expected_duration": expected_duration,
        "actual_duration": actual_duration,
        "duration_delta": duration_delta,
        "checks": checks,
        "audio_only_regions": audio_only_regions,
        "video_only_regions": video_only_regions,
        "transform_coverage_issues": transform_coverage_issues,
        "gaps": gaps,
        "overlaps": overlaps,
        "short_clips": short_clips,
        "minimum_clip_duration": min_clip_duration,
        "cut_count": len(timeline.get("ranges") or []),
        "source_count": len(timeline.get("sources") or {}),
    }
    write_json(report_file, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run automated QA checks for an EDL preview render")
    parser.add_argument("edl", type=Path)
    parser.add_argument("--preview", type=Path, default=None, help="Preview MP4 path; defaults to edit/previews")
    parser.add_argument("--report", type=Path, default=None, help="Output QA JSON path")
    parser.add_argument("--contact-sheet", type=Path, default=None, help="Output contact sheet JPG path")
    parser.add_argument("--timeline", default=None, help="Timeline name to check; defaults to the first timeline")
    args = parser.parse_args()

    report = qa_preview(args.edl.resolve(), args.preview, args.report, args.contact_sheet, args.timeline)
    print(f"QA report -> {default_report_path(args.edl.resolve()) if args.report is None else args.report.resolve()}")
    if report["contact_sheet"]:
        print(f"contact sheet -> {report['contact_sheet']}")


if __name__ == "__main__":
    main()
