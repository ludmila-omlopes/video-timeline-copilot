from __future__ import annotations

import argparse
from fractions import Fraction
from pathlib import Path
import xml.etree.ElementTree as ET

from helpers.common import ensure_within, read_json, resolve_relative, safe_filename


def fcpx_time(seconds: float, fps: float) -> str:
    frames = int(round(seconds * fps))
    rate = int(fps) if float(fps).is_integer() else fps
    return f"{frames}/{rate}s"


def frame_duration(fps: float) -> str:
    rate = Fraction(1, 1) / Fraction(str(fps))
    return f"{rate.numerator}/{rate.denominator}s"


def file_url(path: Path) -> str:
    return path.resolve().as_uri()


def add_asset(resources: ET.Element, asset_id: str, path: Path, duration: str) -> None:
    asset = ET.SubElement(
        resources,
        "asset",
        {
            "id": asset_id,
            "name": path.stem,
            "start": "0s",
            "duration": duration,
            "hasVideo": "1",
            "hasAudio": "1",
        },
    )
    ET.SubElement(asset, "media-rep", {"kind": "original-media", "src": file_url(path)})


def build_fcpxml(edl_path: Path) -> ET.ElementTree:
    edl = read_json(edl_path)
    footage_root = edl_path.parent.parent
    fps = float(edl["fps"])

    fcpxml = ET.Element("fcpxml", {"version": "1.10"})
    resources = ET.SubElement(fcpxml, "resources")

    formats: dict[tuple[int, int], str] = {}
    assets: dict[str, tuple[str, Path]] = {}

    for timeline in edl["timelines"]:
        width, height = timeline["resolution"]
        format_key = (int(width), int(height))
        if format_key not in formats:
            format_id = f"r{len(formats) + 1}"
            formats[format_key] = format_id
            ET.SubElement(
                resources,
                "format",
                {
                    "id": format_id,
                    "name": f"FFVideoFormat{width}x{height}",
                    "frameDuration": frame_duration(fps),
                    "width": str(width),
                    "height": str(height),
                },
            )

        for source_id, source_path in timeline["sources"].items():
            if source_id in assets:
                continue
            resolved = ensure_within(resolve_relative(source_path, footage_root), footage_root)
            asset_id = f"a{len(assets) + 1}"
            assets[source_id] = (asset_id, resolved)
            longest_duration = max(
                (float(item["source_end"]) for item in timeline["ranges"] if item["source"] == source_id),
                default=0.0,
            )
            add_asset(resources, asset_id, resolved, fcpx_time(longest_duration, fps))

    library = ET.SubElement(fcpxml, "library")
    event = ET.SubElement(library, "event", {"name": edl["project_name"]})

    for timeline in edl["timelines"]:
        width, height = timeline["resolution"]
        project = ET.SubElement(event, "project", {"name": timeline["name"]})
        sequence = ET.SubElement(
            project,
            "sequence",
            {
                "format": formats[(int(width), int(height))],
                "duration": fcpx_time(timeline_duration(timeline), fps),
                "tcStart": "0s",
                "tcFormat": "NDF",
            },
        )
        spine = ET.SubElement(sequence, "spine")
        cursor = 0.0

        for index, item in enumerate(sorted(timeline["ranges"], key=lambda r: float(r.get("record_start", 0)))):
            record_start = float(item.get("record_start", cursor))
            if record_start > cursor:
                gap_duration = record_start - cursor
                ET.SubElement(
                    spine,
                    "gap",
                    {
                        "name": "Gap",
                        "offset": fcpx_time(cursor, fps),
                        "start": "0s",
                        "duration": fcpx_time(gap_duration, fps),
                    },
                )
                cursor = record_start

            source_start = float(item["source_start"])
            source_end = float(item["source_end"])
            duration = source_end - source_start
            asset_id, _ = assets[item["source"]]
            clip_name = item.get("beat") or item.get("quote") or f"Clip {index + 1}"
            clip = ET.SubElement(
                spine,
                "asset-clip",
                {
                    "name": str(clip_name),
                    "ref": asset_id,
                    "offset": fcpx_time(record_start, fps),
                    "start": fcpx_time(source_start, fps),
                    "duration": fcpx_time(duration, fps),
                },
            )
            if item.get("reason"):
                ET.SubElement(clip, "note").text = str(item["reason"])
            cursor = max(cursor, record_start + duration)

    ET.indent(fcpxml, space="  ")
    return ET.ElementTree(fcpxml)


def timeline_duration(timeline: dict) -> float:
    end = 0.0
    for item in timeline["ranges"]:
        record_start = float(item.get("record_start", 0.0))
        duration = float(item["source_end"]) - float(item["source_start"])
        end = max(end, record_start + duration)
    return end


def main() -> None:
    parser = argparse.ArgumentParser(description="Export FCPXML from video-timeline-copilot EDL")
    parser.add_argument("edl", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="Output .fcpxml path")
    args = parser.parse_args()

    edl_path = args.edl.resolve()
    edl = read_json(edl_path)
    out_path = args.out or edl_path.parent / f"{safe_filename(edl['project_name'], 'timeline')}.fcpxml"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tree = build_fcpxml(edl_path)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"FCPXML -> {out_path}")


if __name__ == "__main__":
    main()
