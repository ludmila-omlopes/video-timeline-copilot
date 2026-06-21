from __future__ import annotations

import argparse
import copy
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from helpers.common import read_json, resolve_relative, write_json
from helpers.export_fcpxml import RANGE_ID_METADATA_KEY, range_id_for
from helpers.validate_edl import validate


def local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if local_name(child.tag) == name]


def first_child(element: ET.Element, name: str) -> ET.Element | None:
    matches = children(element, name)
    return matches[0] if matches else None


def descendants(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element.iter() if local_name(child.tag) == name]


def parse_fcpx_time(value: str) -> float:
    if not value.endswith("s"):
        raise ValueError(f"unsupported FCPXML time value: {value}")
    raw = value[:-1]
    if "/" in raw:
        numerator, denominator = raw.split("/", maxsplit=1)
        return float(Fraction(int(numerator), int(denominator)))
    return float(Fraction(raw))


def path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def path_from_src(src: str) -> Path:
    parsed = urlparse(src)
    if parsed.scheme == "file":
        return Path(url2pathname(parsed.path)).resolve()
    if parsed.scheme:
        raise ValueError(f"unsupported media src scheme: {parsed.scheme}")
    return Path(src).resolve()


def default_out_path(base_edl_path: Path) -> Path:
    return base_edl_path.with_name(f"{base_edl_path.stem}.imported{base_edl_path.suffix}")


def default_report_path(base_edl_path: Path) -> Path:
    return base_edl_path.parent / "qa" / "fcpxml_import_report.json"


def format_dimensions(root: ET.Element) -> dict[str, list[int]]:
    formats = {}
    for item in descendants(root, "format"):
        format_id = item.attrib.get("id")
        width = item.attrib.get("width")
        height = item.attrib.get("height")
        if format_id and width and height:
            formats[format_id] = [int(width), int(height)]
    return formats


def asset_paths(root: ET.Element) -> dict[str, Path]:
    assets = {}
    for item in descendants(root, "asset"):
        asset_id = item.attrib.get("id")
        media_rep = first_child(item, "media-rep")
        src = media_rep.attrib.get("src") if media_rep is not None else None
        if asset_id and src:
            assets[asset_id] = path_from_src(src)
    return assets


def source_maps(base_edl: dict, footage_root: Path) -> tuple[dict[str, str], dict[str, str]]:
    source_id_by_path = {}
    source_path_by_id = {}
    for timeline in base_edl.get("timelines") or []:
        for source_id, source_path in (timeline.get("sources") or {}).items():
            resolved = resolve_relative(source_path, footage_root)
            source_id_by_path[path_key(resolved)] = str(source_id)
            source_path_by_id[str(source_id)] = str(source_path)
    return source_id_by_path, source_path_by_id


def clip_range_id(clip: ET.Element) -> str | None:
    metadata = first_child(clip, "metadata")
    if metadata is None:
        return None
    for item in children(metadata, "md"):
        if item.attrib.get("key") == RANGE_ID_METADATA_KEY:
            return item.attrib.get("value")
    return None


def base_range_records(timeline_index: int, timeline: dict) -> list[dict]:
    records = []
    for range_index, item in enumerate(timeline.get("ranges") or []):
        source_start = float(item.get("source_start", 0.0))
        source_end = float(item.get("source_end", source_start))
        records.append(
            {
                "id": range_id_for(timeline_index, range_index, item),
                "item": item,
                "index": range_index,
                "source": item.get("source"),
                "source_start": source_start,
                "source_end": source_end,
                "duration": source_end - source_start,
                "record_start": float(item.get("record_start", 0.0)),
            }
        )
    return records


def best_base_match(
    records: list[dict],
    *,
    source_id: str,
    source_start: float,
    duration: float,
    record_start: float,
    used_range_ids: set[str],
) -> dict | None:
    candidates = [item for item in records if item["id"] not in used_range_ids and item["source"] == source_id]
    if not candidates:
        return None
    scored = []
    for item in candidates:
        score = (
            abs(source_start - item["source_start"]) * 2.0
            + abs(duration - item["duration"])
            + abs(record_start - item["record_start"]) * 0.25
        )
        scored.append((score, item))
    score, match = min(scored, key=lambda pair: pair[0])
    return match if score <= 2.0 else None


def describe_trim(range_id: str, old_item: dict, new_item: dict) -> dict | None:
    old_start = float(old_item.get("source_start", 0.0))
    old_end = float(old_item.get("source_end", old_start))
    new_start = float(new_item.get("source_start", 0.0))
    new_end = float(new_item.get("source_end", new_start))
    if abs(old_start - new_start) < 0.001 and abs(old_end - new_end) < 0.001:
        return None
    return {
        "id": range_id,
        "old_source_start": old_start,
        "old_source_end": old_end,
        "new_source_start": new_start,
        "new_source_end": new_end,
    }


def import_project(
    project: ET.Element,
    *,
    project_index: int,
    base_edl: dict,
    asset_path_by_id: dict[str, Path],
    source_id_by_path: dict[str, str],
    source_path_by_id: dict[str, str],
    dimensions_by_format: dict[str, list[int]],
    strict: bool,
) -> tuple[int | None, dict | None, dict]:
    base_timelines = base_edl.get("timelines") or []
    project_name = project.attrib.get("name") or f"Imported Timeline {project_index + 1}"
    base_index = next((index for index, item in enumerate(base_timelines) if item.get("name") == project_name), None)
    if base_index is None and project_index < len(base_timelines):
        base_index = project_index
    report = {
        "name": project_name,
        "matched_ranges": [],
        "unmatched_xml_clips": [],
        "deleted_base_ranges": [],
        "trimmed_ranges": [],
        "reordered_ranges": [],
        "warnings": [],
        "errors": [],
    }
    if base_index is None:
        message = f"no matching base timeline for XML project {project_name!r}"
        (report["errors"] if strict else report["warnings"]).append(message)
        return None, None, report

    base_timeline = base_timelines[base_index]
    sequence = first_child(project, "sequence")
    spine = first_child(sequence, "spine") if sequence is not None else None
    if spine is None:
        report["errors"].append(f"XML project {project_name!r} has no sequence spine")
        return base_index, None, report

    resolution = copy.deepcopy(base_timeline.get("resolution", [1920, 1080]))
    format_id = sequence.attrib.get("format") if sequence is not None else None
    if format_id and format_id in dimensions_by_format:
        resolution = dimensions_by_format[format_id]

    imported_timeline = copy.deepcopy(base_timeline)
    imported_timeline["name"] = project_name
    imported_timeline["resolution"] = resolution
    imported_timeline["sources"] = copy.deepcopy(base_timeline.get("sources") or {})
    imported_ranges = []
    records = base_range_records(base_index, base_timeline)
    records_by_id = {item["id"]: item for item in records}
    used_range_ids: set[str] = set()
    cursor = 0.0

    for child in list(spine):
        child_name = local_name(child.tag)
        if child_name == "gap":
            duration = child.attrib.get("duration")
            gap_duration = parse_fcpx_time(duration) if duration else 0.0
            cursor += gap_duration
            report["warnings"].append(
                f"timeline {project_name!r} contains a {gap_duration:.3f}s gap; EDL validation may fail"
            )
            continue
        if child_name != "asset-clip":
            report["warnings"].append(f"skipped unsupported FCPXML element in spine: {child_name}")
            continue

        ref = child.attrib.get("ref")
        duration_value = child.attrib.get("duration")
        if not ref or not duration_value:
            message = f"asset-clip {child.attrib.get('name', '<unnamed>')!r} is missing ref or duration"
            (report["errors"] if strict else report["warnings"]).append(message)
            continue

        asset_path = asset_path_by_id.get(ref)
        source_id = source_id_by_path.get(path_key(asset_path)) if asset_path is not None else None
        if source_id is None:
            message = {
                "name": child.attrib.get("name"),
                "ref": ref,
                "offset": child.attrib.get("offset"),
                "reason": "source path is not present in the base EDL",
            }
            report["unmatched_xml_clips"].append(message)
            if strict:
                report["errors"].append(f"unknown source for XML clip {child.attrib.get('name', '<unnamed>')!r}")
            continue

        record_start = parse_fcpx_time(child.attrib["offset"]) if child.attrib.get("offset") else cursor
        source_start = parse_fcpx_time(child.attrib.get("start", "0s"))
        duration = parse_fcpx_time(duration_value)
        source_end = source_start + duration
        imported_timeline["sources"].setdefault(source_id, source_path_by_id[source_id])

        range_id = clip_range_id(child)
        base_match = records_by_id.get(range_id) if range_id else None
        if base_match is None:
            base_match = best_base_match(
                records,
                source_id=source_id,
                source_start=source_start,
                duration=duration,
                record_start=record_start,
                used_range_ids=used_range_ids,
            )
            range_id = base_match["id"] if base_match else range_id

        if base_match is not None:
            used_range_ids.add(base_match["id"])
            new_item = copy.deepcopy(base_match["item"])
            range_id = base_match["id"]
            report["matched_ranges"].append(range_id)
        else:
            new_item = {"track": 1}
            range_id = range_id or f"xml-{len(imported_ranges) + 1:04d}"
            report["warnings"].append(f"imported XML clip {child.attrib.get('name', '<unnamed>')!r} without base metadata")

        new_item.update(
            {
                "id": range_id,
                "source": source_id,
                "source_start": round(source_start, 6),
                "source_end": round(source_end, 6),
                "record_start": round(record_start, 6),
                "track": int(new_item.get("track", 1) or 1),
            }
        )
        trim = describe_trim(range_id, base_match["item"], new_item) if base_match is not None else None
        if trim:
            report["trimmed_ranges"].append(trim)
        imported_ranges.append(new_item)
        cursor = max(cursor, record_start + duration)

    imported_timeline["ranges"] = sorted(imported_ranges, key=lambda item: float(item.get("record_start", 0.0)))
    base_ids = [item["id"] for item in records]
    imported_ids = [item.get("id") for item in imported_timeline["ranges"]]
    report["deleted_base_ranges"] = [range_id for range_id in base_ids if range_id not in used_range_ids]
    base_used_order = [range_id for range_id in base_ids if range_id in used_range_ids]
    imported_used_order = [range_id for range_id in imported_ids if range_id in used_range_ids]
    if imported_used_order != base_used_order:
        report["reordered_ranges"] = imported_used_order

    return base_index, imported_timeline, report


def import_fcpxml(
    fcpxml_path: Path,
    base_edl_path: Path,
    out_path: Path | None = None,
    *,
    report_path: Path | None = None,
    strict: bool = False,
    timeline_name: str | None = None,
    replace: bool = False,
) -> dict:
    base_edl_path = base_edl_path.resolve()
    fcpxml_path = fcpxml_path.resolve()
    destination = base_edl_path if replace else (out_path or default_out_path(base_edl_path)).resolve()
    candidate_path = (
        base_edl_path.with_name(f"{base_edl_path.stem}.imported.tmp{base_edl_path.suffix}")
        if replace
        else destination
    )
    report_file = (report_path or default_report_path(base_edl_path)).resolve()
    base_edl = read_json(base_edl_path)
    imported_edl = copy.deepcopy(base_edl)
    footage_root = base_edl_path.parent.parent
    root = ET.parse(fcpxml_path).getroot()
    source_id_by_path, source_path_by_id = source_maps(base_edl, footage_root)
    assets = asset_paths(root)
    dimensions = format_dimensions(root)
    reports = []

    projects = descendants(root, "project")
    if timeline_name:
        projects = [project for project in projects if project.attrib.get("name") == timeline_name]

    replaced_indices = set()
    for project_index, project in enumerate(projects):
        base_index, imported_timeline, timeline_report = import_project(
            project,
            project_index=project_index,
            base_edl=base_edl,
            asset_path_by_id=assets,
            source_id_by_path=source_id_by_path,
            source_path_by_id=source_path_by_id,
            dimensions_by_format=dimensions,
            strict=strict,
        )
        reports.append(timeline_report)
        if base_index is not None and imported_timeline is not None:
            imported_edl["timelines"][base_index] = imported_timeline
            replaced_indices.add(base_index)

    warnings = []
    errors = []
    if not projects:
        if timeline_name:
            errors.append(f"timeline not found in FCPXML: {timeline_name}")
        else:
            errors.append("no FCPXML projects/timelines were found to import")
    for report in reports:
        warnings.extend(report["warnings"])
        errors.extend(report["errors"])
        if strict and report["unmatched_xml_clips"]:
            errors.append(f"timeline {report['name']!r} contains unmapped XML clips")

    write_json(candidate_path, imported_edl)
    validation_errors = validate(candidate_path)

    status = "pass"
    if validation_errors or errors:
        status = "failed"
    elif warnings:
        status = "needs_attention"

    backup_path = None
    final_out = candidate_path
    if replace and status != "failed":
        backup_path = base_edl_path.with_name(f"{base_edl_path.stem}.bak{base_edl_path.suffix}")
        shutil.copy2(base_edl_path, backup_path)
        shutil.move(str(candidate_path), str(base_edl_path))
        final_out = base_edl_path

    report = {
        "status": status,
        "fcpxml": str(fcpxml_path),
        "base_edl": str(base_edl_path),
        "out": str(final_out),
        "backup": str(backup_path) if backup_path else None,
        "strict": strict,
        "timeline": timeline_name,
        "replaced_timeline_indices": sorted(replaced_indices),
        "timelines": reports,
        "warnings": warnings,
        "errors": errors,
        "validation_errors": validation_errors,
    }
    write_json(report_file, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Import an edited FCPXML back into a video-timeline-copilot EDL")
    parser.add_argument("fcpxml", type=Path, help="Edited .fcpxml exported from the NLE")
    parser.add_argument("--base-edl", required=True, type=Path, help="Original EDL used to create the FCPXML")
    parser.add_argument("--out", type=Path, default=None, help="Output EDL path; defaults to edl.imported.json")
    parser.add_argument("--report", type=Path, default=None, help="Import report path")
    parser.add_argument("--timeline", default=None, help="Import only a named FCPXML project/timeline")
    parser.add_argument("--strict", action="store_true", help="Fail when XML clips cannot be mapped to the base EDL")
    parser.add_argument("--replace", action="store_true", help="Replace --base-edl after writing a .bak.json backup")
    args = parser.parse_args()

    if args.replace and args.out is not None:
        print("ERROR: --replace cannot be combined with --out", file=sys.stderr)
        raise SystemExit(2)

    report = import_fcpxml(
        args.fcpxml,
        args.base_edl,
        args.out,
        report_path=args.report,
        strict=args.strict,
        timeline_name=args.timeline,
        replace=args.replace,
    )
    print(f"FCPXML import {report['status']} -> {report['out']}")
    print(f"Import report -> {args.report or default_report_path(args.base_edl.resolve())}")
    if report["status"] == "failed":
        for error in report["errors"] + report["validation_errors"]:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
