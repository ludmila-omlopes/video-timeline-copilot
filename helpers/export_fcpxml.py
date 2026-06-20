from __future__ import annotations

import argparse
from fractions import Fraction
from pathlib import Path
import xml.etree.ElementTree as ET

from helpers.common import ensure_within, read_json, resolve_relative, safe_filename
from helpers.transforms import resolve_transform
from helpers.validate_edl import validate


def fcpx_time(seconds: float, fps: float) -> str:
    return fcpx_time_from_frames(fcpx_frames(seconds, fps), fps)


def fps_fraction(fps: float) -> Fraction:
    """Map a float fps to its conventional rational frame rate."""
    nearest_int = round(fps)
    if nearest_int > 0 and abs(fps - nearest_int) < 1e-6:
        return Fraction(nearest_int, 1)

    ntsc_base = round(fps * 1001 / 1000)
    if ntsc_base > 0 and abs(fps - ntsc_base * 1000 / 1001) < 0.005:
        return Fraction(ntsc_base * 1000, 1001)

    return Fraction(fps).limit_denominator(100000)


def fcpx_frames(seconds: float, fps: float) -> int:
    rate = fps_fraction(fps)
    return int(round(seconds * rate.numerator / rate.denominator))


def fcpx_time_from_frames(frames: int, fps: float) -> str:
    rate = fps_fraction(fps)
    value = Fraction(frames * rate.denominator, rate.numerator)
    if value.denominator == 1:
        return f"{value.numerator}s"
    return f"{value.numerator}/{value.denominator}s"


def frame_duration(fps: float) -> str:
    rate = fps_fraction(fps)
    return f"{rate.denominator}/{rate.numerator}s"


def file_url(path: Path) -> str:
    return path.resolve().as_uri()


def add_asset(
    resources: ET.Element,
    asset_id: str,
    path: Path,
    duration: str,
    format_id: str,
    media_info: dict | None = None,
) -> None:
    attrs = {
        "id": asset_id,
        "name": path.stem,
        "start": "0s",
        "duration": duration,
        "hasVideo": "1",
        "hasAudio": "1",
        "format": format_id,
        "videoSources": "1",
        "audioSources": "1",
        "audioChannels": str((media_info or {}).get("audio_channels") or 2),
        "audioRate": str((media_info or {}).get("audio_rate") or 48000),
    }
    asset = ET.SubElement(
        resources,
        "asset",
        attrs,
    )
    ET.SubElement(asset, "media-rep", {"kind": "original-media", "src": file_url(path)})


def build_fcpxml(edl_path: Path) -> ET.ElementTree:
    validation_errors = validate(edl_path)
    if validation_errors:
        raise ValueError("EDL validation failed: " + "; ".join(validation_errors))

    edl = read_json(edl_path)
    footage_root = edl_path.parent.parent
    fps = float(edl["fps"])
    media_by_path = load_media_index(edl_path.parent, footage_root)

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
            add_asset(
                resources,
                asset_id,
                resolved,
                fcpx_time(longest_duration, fps),
                formats[format_key],
                media_by_path.get(resolved),
            )

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
                "audioLayout": "stereo",
                "audioRate": "48k",
            },
        )
        spine = ET.SubElement(sequence, "spine")
        cursor = 0.0

        for index, item in enumerate(sorted(timeline["ranges"], key=lambda r: float(r.get("record_start", 0)))):
            record_start = float(item.get("record_start", cursor))
            cursor_frames = fcpx_frames(cursor, fps)
            record_start_frames = fcpx_frames(record_start, fps)
            if record_start_frames > cursor_frames:
                raise ValueError(f"range {index + 1} creates a record gap; validate the EDL before export")
            if record_start_frames < cursor_frames:
                raise ValueError(f"range {index + 1} overlaps the previous clip; validate the EDL before export")

            source_start = float(item["source_start"])
            source_end = float(item["source_end"])
            duration = source_end - source_start
            duration_frames = fcpx_frames(duration, fps)
            if duration_frames <= 0:
                raise ValueError(f"range {index + 1} duration rounds to zero frames")
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
                    "duration": fcpx_time_from_frames(duration_frames, fps),
                    "format": formats[(int(width), int(height))],
                    "srcEnable": "all",
                    "audioRole": "dialogue",
                    "videoRole": "video",
                },
            )
            if item.get("reason"):
                ET.SubElement(clip, "note").text = str(item["reason"])
            ET.SubElement(clip, "adjust-conform", {"type": "fill"})
            transform = resolve_transform(item.get("transform"), int(width), int(height))
            if transform.zoom != 1.0 or transform.pan != 0.0 or transform.tilt != 0.0:
                ET.SubElement(
                    clip,
                    "adjust-transform",
                    {
                        "position": f"{transform.pan:.3f} {transform.tilt:.3f}",
                        "scale": f"{transform.zoom:.3f} {transform.zoom:.3f}",
                    },
                )
            cursor = max(cursor, record_start + duration)

    ET.indent(fcpxml, space="  ")
    return ET.ElementTree(fcpxml)


def load_media_index(edit_dir: Path, footage_root: Path) -> dict[Path, dict]:
    index_path = edit_dir / "media_index.json"
    if not index_path.exists():
        return {}

    media_by_path = {}
    for item in read_json(index_path).get("media", []):
        item_path = item.get("path")
        if not item_path:
            continue
        media_by_path[resolve_relative(item_path, footage_root).resolve()] = item
    return media_by_path


def timeline_duration(timeline: dict) -> float:
    end = 0.0
    cursor = 0.0
    for item in sorted(timeline["ranges"], key=lambda value: float(value.get("record_start", 0.0))):
        record_start = float(item.get("record_start", cursor))
        duration = float(item["source_end"]) - float(item["source_start"])
        end = max(end, record_start + duration)
        cursor = max(cursor, record_start + duration)
    return end


def default_fcpxml_path(edl_path: Path, edl: dict | None = None) -> Path:
    payload = edl or read_json(edl_path)
    return edl_path.parent / f"{safe_filename(payload['project_name'], 'timeline')}.fcpxml"


def write_fcpxml(edl_path: Path, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree = build_fcpxml(edl_path)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export FCPXML from video-timeline-copilot EDL")
    parser.add_argument("edl", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="Output .fcpxml path")
    args = parser.parse_args()

    edl_path = args.edl.resolve()
    edl = read_json(edl_path)
    out_path = args.out or default_fcpxml_path(edl_path, edl)

    result = write_fcpxml(edl_path, out_path)
    print(f"FCPXML -> {result}")


if __name__ == "__main__":
    main()
