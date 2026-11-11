from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from helpers.common import clock, read_json, safe_filename
from helpers.contact_sheet import sheets_for_source
from helpers.project_context import load_context


VIDEO_ARTIFACTS = ("transcript", "analysis", "contact_sheet", "summary")
READY_VIDEO_ARTIFACTS = ("transcript", "contact_sheet", "summary")
IMAGE_ARTIFACTS = ("summary",)
SUMMARY_REQUIRED_HEADINGS = ("## Overview", "## Visuals")


def summary_path(edit_dir: Path, stem: str) -> Path:
    return edit_dir / "summaries" / f"{safe_filename(stem)}.md"


def summary_is_complete(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return all(heading in text for heading in SUMMARY_REQUIRED_HEADINGS)


def summary_overview(path: Path, limit: int = 320) -> str:
    """The Overview paragraph of a summary, for the one-page library index."""
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    collected: list[str] = []
    inside = False
    for line in lines:
        if line.strip().lower().startswith("## overview"):
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside and line.strip():
            collected.append(line.strip())
    text = " ".join(collected)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _first_existing(*paths: Path) -> Path | None:
    return next((path for path in paths if path.exists()), None)


def video_status(edit_dir: Path, item: dict) -> dict:
    path = Path(item["path"])
    stem = path.stem
    safe = safe_filename(stem)
    transcript = _first_existing(edit_dir / "transcripts" / f"{stem}.json", edit_dir / "transcripts" / f"{safe}.json")
    analysis = _first_existing(edit_dir / "video_analysis" / f"{safe}.json", edit_dir / "video_analysis" / f"{stem}.json")
    sheets = sheets_for_source(edit_dir, stem)
    summary = summary_path(edit_dir, stem)
    artifacts = {
        "transcript": transcript is not None,
        "analysis": analysis is not None,
        "contact_sheet": any(sheet.stem.endswith("_full") for sheet in sheets),
        "summary": summary_is_complete(summary),
    }
    return {
        "kind": "video",
        "name": path.name,
        "stem": stem,
        "path": str(path),
        "exists": path.exists(),
        "duration": float(item.get("duration") or 0.0),
        "resolution": [int(item.get("width") or 0), int(item.get("height") or 0)],
        "frame_rate": item.get("avg_frame_rate"),
        "artifacts": artifacts,
        "missing": [name for name in VIDEO_ARTIFACTS if not artifacts[name]],
        "contact_sheets": [str(sheet) for sheet in sheets],
        "summary_path": str(summary),
        "error": item.get("error"),
    }


def image_status(edit_dir: Path, item: dict) -> dict:
    path = Path(item["path"])
    # Images keep their extension in the key so photo.png never collides with photo.mp4.
    summary = summary_path(edit_dir, path.name)
    artifacts = {"summary": summary_is_complete(summary)}
    return {
        "kind": "image",
        "name": path.name,
        "stem": path.stem,
        "path": str(path),
        "exists": path.exists(),
        "resolution": [int(item.get("width") or 0), int(item.get("height") or 0)],
        "artifacts": artifacts,
        "missing": [name for name in IMAGE_ARTIFACTS if not artifacts[name]],
        "summary_path": str(summary),
        "error": item.get("error"),
    }


def build_status(edit_dir: Path) -> dict:
    index_path = edit_dir / "media_index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"media index not found: {index_path}; run `vtc inventory` first")
    index = read_json(index_path)
    sources = [video_status(edit_dir, item) for item in index.get("media") or [] if item.get("path")]
    sources.extend(image_status(edit_dir, item) for item in index.get("images") or [] if item.get("path"))

    stems = Counter(source["stem"] for source in sources if source["kind"] == "video")
    warnings = [
        f"{count} videos share the name {stem!r}; their transcripts and analysis would overwrite each other. Rename one."
        for stem, count in stems.items()
        if count > 1
    ]
    warnings.extend(f"source file is missing: {source['path']}" for source in sources if not source["exists"])
    warnings.extend(f"could not read {source['name']}: {source['error']}" for source in sources if source.get("error"))

    not_ready = []
    for source in sources:
        required = READY_VIDEO_ARTIFACTS if source["kind"] == "video" else IMAGE_ARTIFACTS
        lacking = [name for name in required if not source["artifacts"][name]]
        if lacking or not source["exists"]:
            not_ready.append({"name": source["name"], "missing": lacking, "exists": source["exists"]})

    videos = [source for source in sources if source["kind"] == "video"]
    return {
        "edit_dir": str(edit_dir),
        "root": index.get("root"),
        "video_count": len(videos),
        "image_count": len(sources) - len(videos),
        "total_duration": round(sum(source["duration"] for source in videos), 3),
        "ready": not not_ready and not any("share the name" in warning for warning in warnings),
        "not_ready": not_ready,
        "warnings": warnings,
        "sources": sources,
    }


def pending(status: dict, artifact: str) -> list[str]:
    return [
        source["path"]
        for source in status["sources"]
        if artifact in source["artifacts"] and not source["artifacts"][artifact]
    ]


def library_index_lines(status: dict, context: dict, edit_dir: Path) -> list[str]:
    lines = ["# Library index", ""]
    lines.append(
        f"{status['video_count']} video(s), {status['image_count']} image(s), "
        f"{clock(status['total_duration'])} of footage. "
        + ("Everything is analyzed." if status["ready"] else f"{len(status['not_ready'])} source(s) still need analysis.")
    )
    if context.get("footage_summary"):
        lines.extend(["", f"Footage: {context['footage_summary']}"])
    if context.get("user_context"):
        lines.extend(["", f"User: {context['user_context']}"])
    terms = [str(item.get("term")) for item in context.get("glossary") or [] if item.get("term")]
    if terms:
        lines.extend(["", "Names and terms: " + ", ".join(terms)])
    for note in context.get("notes") or []:
        lines.append(f"- Note ({note.get('date', '')}): {note.get('text', '')}")
    lines.append("")
    for source in status["sources"]:
        if source["kind"] == "video":
            width, height = source["resolution"]
            header = f"## {source['name']} ({clock(source['duration'])}, {width}x{height})"
        else:
            header = f"## {source['name']} (still image)"
        lines.append(header)
        overview = summary_overview(Path(source["summary_path"]))
        lines.append(overview or "No summary yet.")
        if source["missing"]:
            lines.append("Missing: " + ", ".join(source["missing"]))
        lines.append("")
    return lines


def write_library_index(status: dict, edit_dir: Path) -> Path:
    out = edit_dir / "library.md"
    out.write_text("\n".join(library_index_lines(status, load_context(edit_dir), edit_dir)), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show which sources have transcripts, contact sheets, and summaries, and refresh edit/library.md"
    )
    parser.add_argument("--edit-dir", type=Path, required=True)
    parser.add_argument("--ready", action="store_true", help="Exit non-zero unless every source is ready to cut from")
    parser.add_argument("--pending", choices=VIDEO_ARTIFACTS, default=None, help="List the sources still missing one artifact")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    try:
        status = build_status(edit_dir)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    index = write_library_index(status, edit_dir)

    if args.pending:
        print(json.dumps(pending(status, args.pending), indent=2, ensure_ascii=False))
    elif args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print(
            f"{status['video_count']} video(s), {status['image_count']} image(s), "
            f"{clock(status['total_duration'])} total -> {'ready' if status['ready'] else 'not ready'}"
        )
        blocked = {item["name"] for item in status["not_ready"]}
        for source in status["sources"]:
            mark = "..." if source["name"] in blocked else "ok "
            needed = [name for name in source["missing"] if name != "analysis"]
            detail = "  missing: " + ", ".join(needed) if needed else ""
            if "analysis" in source["missing"]:
                detail += "  (optional motion analysis not run)"
            print(f" {mark} {source['name']}{detail}")
        for warning in status["warnings"]:
            print(f"WARNING: {warning}")
        print(f"library index -> {index}")

    if args.ready and not status["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
