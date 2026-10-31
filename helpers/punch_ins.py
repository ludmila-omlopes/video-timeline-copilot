from __future__ import annotations

import argparse
from pathlib import Path

from helpers.common import read_json, resolve_relative, write_json


DEFAULT_LEVELS = (1.0, 1.12)
DEFAULT_EMPHASIS_ZOOM = 1.25
DEFAULT_FOCUS = (0.5, 0.38)
CONTINUITY_TOLERANCE = 0.05
EMPHASIS_MARKS = ("?", "!")


def parse_pair(value: str) -> tuple[float, float]:
    parts = [float(part) for part in value.split(",")]
    if len(parts) != 2 or not all(0.0 <= part <= 1.0 for part in parts):
        raise argparse.ArgumentTypeError("expected two normalized values such as 0.55,0.33")
    return parts[0], parts[1]


def parse_levels(value: str) -> tuple[float, ...]:
    levels = tuple(float(part) for part in value.split(","))
    if len(levels) < 2 or any(level < 1.0 for level in levels):
        raise argparse.ArgumentTypeError("expected at least two zoom levels >= 1.0, such as 1.0,1.12")
    return levels


def focus_transform(zoom: float, focus: tuple[float, float], width: int, height: int) -> dict:
    """Zoom while keeping the focus point (eyes/face, normalized from top-left) where it was.

    Pan/tilt follow this repo's convention: timeline pixels, positive pan moves the
    image right, positive tilt moves it up.
    """
    focus_x, focus_y = focus
    return {
        "zoom": round(zoom, 4),
        "pan": round(-(focus_x - 0.5) * (zoom - 1.0) * width, 1),
        "tilt": round((focus_y - 0.5) * (zoom - 1.0) * height, 1),
    }


def range_text(item: dict, words_by_source: dict[str, list[dict]]) -> str:
    if item.get("quote"):
        return str(item["quote"])
    start = float(item["source_start"])
    end = float(item["source_end"])
    words = words_by_source.get(item["source"], [])
    return " ".join(
        str(word.get("text") or "").strip()
        for word in words
        if word.get("start") is not None and start <= (float(word["start"]) + float(word["end"])) / 2 < end
    )


def load_words(edit_dir: Path, sources: dict[str, str], root: Path) -> dict[str, list[dict]]:
    words: dict[str, list[dict]] = {}
    for source_id, source_path in sources.items():
        transcript = edit_dir / "transcripts" / f"{resolve_relative(source_path, root).stem}.json"
        if transcript.exists():
            words[source_id] = read_json(transcript).get("words", [])
    return words


def is_emphasis(item: dict, text: str, max_seconds: float) -> bool:
    if "emphasis" in item:
        return bool(item["emphasis"])
    duration = float(item["source_end"]) - float(item["source_start"])
    return duration <= max_seconds and any(mark in text for mark in EMPHASIS_MARKS)


def continues_previous(previous: dict | None, item: dict) -> bool:
    return (
        previous is not None
        and previous["source"] == item["source"]
        and abs(float(item["source_start"]) - float(previous["source_end"])) <= CONTINUITY_TOLERANCE
    )


def plan_punch_ins(
    ranges: list[dict],
    *,
    texts: list[str],
    levels: tuple[float, ...] = DEFAULT_LEVELS,
    emphasis_zoom: float = DEFAULT_EMPHASIS_ZOOM,
    emphasis_max_seconds: float = 9.0,
) -> list[float]:
    """Pick one zoom level per range so no jump cut keeps the same framing.

    Levels cycle at every cut; short emphatic ranges (questions, exclamations,
    or ranges marked "emphasis") get a closer punch-in. A range that continues
    the previous one in the same source without a cut keeps its zoom.
    """
    plan: list[float] = []
    cycle = 0
    previous = None
    for item, text in zip(ranges, texts):
        if continues_previous(previous, item):
            zoom = plan[-1]
        elif plan and is_emphasis(item, text, emphasis_max_seconds) and plan[-1] != emphasis_zoom:
            zoom = emphasis_zoom
        else:
            zoom = levels[cycle % len(levels)]
            if plan and zoom == plan[-1]:
                cycle += 1
                zoom = levels[cycle % len(levels)]
            cycle += 1
        plan.append(zoom)
        previous = item
    return plan


def lua_command(transforms: list[dict]) -> str:
    """One console line that applies the plan to the open Resolve timeline, by clip order."""
    table = ",".join(f"{{{t['zoom']},{t['pan']},{t['tilt']}}}" for t in transforms)
    return (
        f"Z={{{table}}}; tl=resolve:GetProjectManager():GetCurrentProject():GetCurrentTimeline(); "
        "local V={}; for _,v in pairs(tl:GetItemListInTrack('video',1)) do if type(v)~='number' then V[#V+1]=v end end; "
        "table.sort(V,function(a,b) return a:GetStart()<b:GetStart() end); "
        "if #V~=#Z then print('clip count differs', #V, #Z) else local n=0; for i,v in ipairs(V) do local z=Z[i]; "
        "if v:SetProperty('ZoomX',z[1]) and v:SetProperty('ZoomY',z[1]) and v:SetProperty('Pan',z[2]) "
        "and v:SetProperty('Tilt',z[3]) then n=n+1 end end; print(tl:GetName(), 'punch-ins set', n) end"
    )


def apply_punch_ins(
    edl_path: Path,
    *,
    out_path: Path | None = None,
    timeline_name: str | None = None,
    focus: tuple[float, float] = DEFAULT_FOCUS,
    levels: tuple[float, ...] = DEFAULT_LEVELS,
    emphasis_zoom: float = DEFAULT_EMPHASIS_ZOOM,
    overwrite: bool = False,
    allow_vertical: bool = False,
    lua_path: Path | None = None,
) -> dict:
    edl_path = edl_path.resolve()
    edl = read_json(edl_path)
    root = edl_path.parent.parent
    summary = []
    for timeline in edl.get("timelines") or []:
        if timeline_name and timeline.get("name") != timeline_name:
            continue
        width, height = (int(value) for value in timeline["resolution"])
        if height > width and not allow_vertical:
            summary.append({"timeline": timeline.get("name"), "skipped": "vertical timeline; use Shorts framing instead"})
            continue
        ranges = sorted(timeline.get("ranges") or [], key=lambda item: float(item.get("record_start", 0.0)))
        words = load_words(edl_path.parent, timeline.get("sources") or {}, root)
        texts = [range_text(item, words) for item in ranges]
        plan = plan_punch_ins(ranges, texts=texts, levels=levels, emphasis_zoom=emphasis_zoom)
        transforms = []
        changed = 0
        for item, zoom in zip(ranges, plan):
            transform = focus_transform(zoom, focus, width, height)
            transforms.append(transform)
            if item.get("visual_layers") or (item.get("transform") and not overwrite):
                continue
            item["transform"] = transform
            changed += 1
        counts: dict[str, int] = {}
        for zoom in plan:
            counts[f"{zoom:g}"] = counts.get(f"{zoom:g}", 0) + 1
        summary.append({"timeline": timeline.get("name"), "ranges": len(ranges), "changed": changed, "zoom_counts": counts})
        if lua_path is not None:
            lua_path.parent.mkdir(parents=True, exist_ok=True)
            lua_path.write_text(lua_command(transforms) + "\n", encoding="utf-8")

    write_json((out_path or edl_path).resolve(), edl)
    return {"edl": str((out_path or edl_path).resolve()), "timelines": summary}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add alternating punch-in zooms to talking-head ranges so jump cuts change framing"
    )
    parser.add_argument("edl", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="Output EDL; defaults to updating the input EDL")
    parser.add_argument("--timeline", default=None)
    parser.add_argument(
        "--focus",
        type=parse_pair,
        default=DEFAULT_FOCUS,
        help="Normalized x,y of the speaker's eyes in the frame (default 0.5,0.38); kept in place while zooming",
    )
    parser.add_argument("--levels", type=parse_levels, default=DEFAULT_LEVELS, help="Zoom levels cycled at cuts")
    parser.add_argument("--emphasis-zoom", type=float, default=DEFAULT_EMPHASIS_ZOOM)
    parser.add_argument("--overwrite", action="store_true", help="Replace existing range transforms")
    parser.add_argument("--allow-vertical", action="store_true", help="Also apply to vertical (9:16) timelines")
    parser.add_argument(
        "--lua",
        type=Path,
        default=None,
        help="Also write a one-line Resolve Console command that applies the plan to the open timeline",
    )
    args = parser.parse_args()

    result = apply_punch_ins(
        args.edl,
        out_path=args.out,
        timeline_name=args.timeline,
        focus=args.focus,
        levels=args.levels,
        emphasis_zoom=args.emphasis_zoom,
        overwrite=args.overwrite,
        allow_vertical=args.allow_vertical,
        lua_path=args.lua,
    )
    for timeline in result["timelines"]:
        print(timeline)
    print(f"punch-ins -> {result['edl']}")


if __name__ == "__main__":
    main()
