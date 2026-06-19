from __future__ import annotations

import argparse
import sys
from pathlib import Path

from helpers.build_resolve_project import connect_resolve, create_timelines_from_edl, fail
from helpers.common import read_json, write_json
from helpers.validate_edl import validate


def project_fps(project) -> float | None:
    value = project.GetSetting("timelineFrameRate")
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def update_timelines(
    edl_path: Path,
    project_name: str | None,
    replace_existing: bool,
    allow_fps_mismatch: bool,
) -> dict:
    validation_errors = validate(edl_path)
    if validation_errors:
        fail("EDL validation failed: " + "; ".join(validation_errors))

    edl = read_json(edl_path)
    footage_root = edl_path.parent.parent
    resolve_out = edl_path.parent / "resolve"
    resolve_out.mkdir(parents=True, exist_ok=True)

    resolve = connect_resolve()
    project_manager = resolve.GetProjectManager()
    target_project = project_name or edl["project_name"]

    project = project_manager.LoadProject(target_project)
    if not project:
        current_project = project_manager.GetCurrentProject()
        if current_project and current_project.GetName() == target_project:
            project = current_project
    if not project:
        fail(f"Could not load Resolve project: {target_project}")

    edl_fps = float(edl["fps"])
    existing_fps = project_fps(project)
    if existing_fps is not None and abs(existing_fps - edl_fps) > 0.001 and not allow_fps_mismatch:
        fail(
            f"Project timeline frame rate is {existing_fps}, but EDL fps is {edl_fps}. "
            "Use --allow-fps-mismatch only if this is intentional."
        )

    created_timelines = create_timelines_from_edl(
        project,
        resolve,
        edl,
        footage_root,
        replace_existing=replace_existing,
    )

    if not project_manager.SaveProject():
        fail("Resolve did not save the project successfully.")

    return {
        "project_name": target_project,
        "project_fps": existing_fps,
        "edl_fps": edl_fps,
        "replace_existing": replace_existing,
        "timelines": created_timelines,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or replace timelines in an existing DaVinci Resolve project")
    parser.add_argument("edl", type=Path)
    parser.add_argument(
        "--project",
        default=None,
        help="Existing Resolve project name. Defaults to project_name from the EDL.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete matching timelines before recreating them. Without this, new unique timeline names are created.",
    )
    parser.add_argument(
        "--allow-fps-mismatch",
        action="store_true",
        help="Proceed even when the existing Resolve project frame rate differs from the EDL fps.",
    )
    args = parser.parse_args()

    edl_path = args.edl.resolve()
    try:
        result = update_timelines(
            edl_path,
            args.project,
            args.replace_existing,
            args.allow_fps_mismatch,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

    log_path = edl_path.parent / "resolve" / "update_log.json"
    write_json(log_path, result)
    print(f"Resolve timelines updated -> {log_path}")


if __name__ == "__main__":
    main()
