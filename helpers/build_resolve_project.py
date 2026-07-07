from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from helpers.common import ensure_within, read_json, resolve_relative, safe_filename, seconds_to_frames, write_json
from helpers.timing import range_effective_speed
from helpers.transforms import resolve_transform
from helpers.validate_edl import minimum_clip_duration, timeline_timing_issues, validate


def load_resolve_module():
    try:
        return importlib.import_module("DaVinciResolveScript")
    except ImportError as exc:
        raise RuntimeError(
            "Could not import DaVinciResolveScript. Configure RESOLVE_SCRIPT_API, "
            "RESOLVE_SCRIPT_LIB, and PYTHONPATH for your DaVinci Resolve install."
        ) from exc


def fail(message: str) -> None:
    raise RuntimeError(message)


def connect_resolve():
    dvr = load_resolve_module()
    resolve = dvr.scriptapp("Resolve")
    if not resolve:
        fail("Could not connect to DaVinci Resolve. Open Resolve and try again.")
    return resolve


def find_timeline(project, name: str):
    count = int(project.GetTimelineCount() or 0)
    for index in range(1, count + 1):
        timeline = project.GetTimelineByIndex(index)
        if timeline and timeline.GetName() == name:
            return timeline
    return None


def unique_timeline_name(project, base_name: str) -> str:
    if not find_timeline(project, base_name):
        return base_name
    index = 2
    while find_timeline(project, f"{base_name} {index}"):
        index += 1
    return f"{base_name} {index}"


def delete_timeline(project, media_pool, name: str) -> bool:
    timeline = find_timeline(project, name)
    if not timeline:
        return False
    deleted = media_pool.DeleteTimelines([timeline])
    if not deleted:
        fail(f"Could not delete existing Resolve timeline: {name}")
    return True


def create_timelines_from_edl(project, resolve, edl: dict, footage_root: Path, *, replace_existing: bool = False) -> list[str]:
    fps = float(edl["fps"])
    min_clip_duration = minimum_clip_duration(edl)
    media_storage = resolve.GetMediaStorage()
    media_pool = project.GetMediaPool()
    imported: dict[str, object] = {}
    created_timelines = []

    for timeline_index, timeline_spec in enumerate(edl["timelines"]):
        timing_issues = timeline_timing_issues(timeline_spec, fps, min_clip_duration)
        if timing_issues["gaps"]:
            fail(f"Timeline {timeline_index} contains record gaps; validate the EDL before creating Resolve timelines.")
        if timing_issues["overlaps"]:
            fail(f"Timeline {timeline_index} contains overlapping clips; validate the EDL before creating Resolve timelines.")
        if timing_issues["short_clips"]:
            fail(f"Timeline {timeline_index} contains clips shorter than {min_clip_duration:.3f}s.")
        if any(abs(range_effective_speed(item) - 1.0) > 1e-6 for item in timeline_spec.get("ranges") or []):
            fail("Resolve scripting backend does not support retimed ranges yet; export FCPXML instead.")
        if any(item.get("visual_layers") for item in timeline_spec.get("ranges") or []):
            fail("Resolve scripting backend does not support visual_layers yet; export FCPXML instead.")

        requested_name = timeline_spec["name"]
        timeline_name = requested_name
        if replace_existing:
            delete_timeline(project, media_pool, requested_name)
        else:
            timeline_name = unique_timeline_name(project, requested_name)

        width, height = timeline_spec["resolution"]
        project.SetSetting("timelineResolutionWidth", str(width))
        project.SetSetting("timelineResolutionHeight", str(height))

        clip_infos = []
        source_paths = {
            source_id: resolve_relative(path, footage_root)
            for source_id, path in timeline_spec["sources"].items()
        }

        for item in timeline_spec["ranges"]:
            source_id = item["source"]
            source_path = ensure_within(source_paths[source_id], footage_root)
            if not source_path.exists():
                fail(f"Missing source media: {source_path}")

            key = str(source_path)
            if key not in imported:
                media_items = media_storage.AddItemListToMediaPool([key])
                if not media_items:
                    fail(f"Could not import media into Resolve: {source_path}")
                imported[key] = media_items[0]

            clip_infos.append(
                {
                    "mediaPoolItem": imported[key],
                    "startFrame": seconds_to_frames(float(item["source_start"]), fps),
                    "endFrame": seconds_to_frames(float(item["source_end"]), fps),
                    "recordFrame": seconds_to_frames(float(item.get("record_start", 0)), fps),
                    "trackIndex": int(item.get("track", 1)),
                }
            )

        timeline = media_pool.CreateTimelineFromClips(timeline_name, clip_infos)
        if not timeline:
            fail(f"Could not create timeline: {timeline_name}")
        project.SetCurrentTimeline(timeline)
        created_timelines.append(timeline_name)

        video_items = timeline.GetItemListInTrack("video", 1) or []
        for index, timeline_item in enumerate(video_items):
            if index >= len(timeline_spec["ranges"]):
                break
            transform = resolve_transform(timeline_spec["ranges"][index].get("transform"), int(width), int(height))
            timeline_item.SetProperty(
                {
                    "ZoomX": transform.zoom,
                    "ZoomY": transform.zoom,
                    "Pan": transform.pan,
                    "Tilt": transform.tilt,
                }
            )

        if timeline_spec.get("markers"):
            for item in timeline_spec["ranges"]:
                frame = seconds_to_frames(float(item.get("record_start", 0)), fps)
                name = item.get("beat") or item.get("quote") or "Edit"
                note = item.get("reason") or item.get("quote") or ""
                timeline.AddMarker(frame, "Blue", name, note, 1)

    return created_timelines


def build_project(edl_path: Path) -> dict:
    validation_errors = validate(edl_path)
    if validation_errors:
        fail("EDL validation failed: " + "; ".join(validation_errors))

    edl = read_json(edl_path)
    footage_root = edl_path.parent.parent
    resolve_out = edl_path.parent / "resolve"
    resolve_out.mkdir(parents=True, exist_ok=True)

    resolve = connect_resolve()

    project_manager = resolve.GetProjectManager()
    project_name = edl["project_name"]

    existing = project_manager.LoadProject(project_name)
    if existing:
        fail(f"Project already exists or is loaded: {project_name}. Rename it or delete it manually.")

    project = project_manager.CreateProject(project_name)
    if not project:
        fail(f"Could not create project: {project_name}")

    fps = float(edl["fps"])
    project.SetSetting("timelineFrameRate", str(int(fps) if fps.is_integer() else fps))

    created_timelines = create_timelines_from_edl(project, resolve, edl, footage_root, replace_existing=False)

    if not project_manager.SaveProject():
        fail("Resolve did not save the project successfully.")

    output_name = safe_filename(project_name, "resolve_project")
    drp_path = resolve_out / f"{output_name}.drp"
    if not project_manager.ExportProject(project_name, str(drp_path)):
        fail(f"Could not export project: {drp_path}")

    dra_path = None
    if edl.get("archive_project", True):
        dra_path = resolve_out / f"{output_name}.dra"
        if not project_manager.ArchiveProject(project_name, str(dra_path), True, False, True):
            fail(f"Could not archive project: {dra_path}")

    return {
        "project_name": project_name,
        "timelines": created_timelines,
        "drp": str(drp_path),
        "dra": str(dra_path) if dra_path else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a DaVinci Resolve project from video-timeline-copilot EDL")
    parser.add_argument("edl", type=Path)
    args = parser.parse_args()

    try:
        result = build_project(args.edl.resolve())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

    log_path = args.edl.resolve().parent / "resolve" / "build_log.json"
    write_json(log_path, result)
    print(f"Resolve project built -> {log_path}")


if __name__ == "__main__":
    main()
