from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from helpers.common import ensure_within, read_json, resolve_relative, safe_filename, seconds_to_frames, write_json


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


def build_project(edl_path: Path) -> dict:
    edl = read_json(edl_path)
    footage_root = edl_path.parent.parent
    resolve_out = edl_path.parent / "resolve"
    resolve_out.mkdir(parents=True, exist_ok=True)

    dvr = load_resolve_module()
    resolve = dvr.scriptapp("Resolve")
    if not resolve:
        fail("Could not connect to DaVinci Resolve. Open Resolve and try again.")

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

    media_storage = resolve.GetMediaStorage()
    media_pool = project.GetMediaPool()
    imported: dict[str, object] = {}
    created_timelines = []

    for timeline_spec in edl["timelines"]:
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

        timeline = media_pool.CreateTimelineFromClips(timeline_spec["name"], clip_infos)
        if not timeline:
            fail(f"Could not create timeline: {timeline_spec['name']}")
        project.SetCurrentTimeline(timeline)
        created_timelines.append(timeline_spec["name"])

        video_items = timeline.GetItemListInTrack("video", 1) or []
        for index, timeline_item in enumerate(video_items):
            if index >= len(timeline_spec["ranges"]):
                break
            transform = timeline_spec["ranges"][index].get("transform") or {}
            zoom = float(transform.get("zoom", 1.0))
            timeline_item.SetProperty(
                {
                    "ZoomX": zoom,
                    "ZoomY": zoom,
                    "Pan": float(transform.get("pan", 0)),
                    "Tilt": float(transform.get("tilt", 0)),
                }
            )

        if timeline_spec.get("markers"):
            for item in timeline_spec["ranges"]:
                frame = seconds_to_frames(float(item.get("record_start", 0)), fps)
                name = item.get("beat") or item.get("quote") or "Edit"
                note = item.get("reason") or item.get("quote") or ""
                timeline.AddMarker(frame, "Blue", name, note, 1)

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
