from __future__ import annotations

import argparse
from fractions import Fraction
from pathlib import Path
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

from helpers.common import ensure_within, read_json, resolve_relative, safe_filename
from helpers.timing import range_effective_speed, range_playback_speed, range_source_duration, range_timeline_duration
from helpers.transforms import (
    aspect_fill_crop_rect,
    rect_trim_percentages,
    resolve_transform,
    visual_layer_dest_rect,
    visual_layer_source_rect,
)
from helpers.validate_edl import validate


FCPXML_VERSION = "1.13"
RANGE_ID_METADATA_KEY = "com.video-timeline-copilot.range-id"
DEFAULT_RESOLVE_CROP_X_FACTOR = 2.0


def range_id_for(timeline_index: int, range_index: int, item: dict) -> str:
    existing = item.get("id")
    if existing:
        return str(existing)
    return f"t{timeline_index + 1:03d}-r{range_index + 1:04d}"


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


def has_explicit_speed(item: dict) -> bool:
    return item.get("speed") is not None or item.get("playback_speed") is not None or item.get("speed_percent") is not None


def add_time_map(clip: ET.Element, item: dict, fps: float) -> None:
    source_duration = range_source_duration(item)
    record_duration = range_timeline_duration(item)
    explicit_speed = range_playback_speed(item) if has_explicit_speed(item) else range_effective_speed(item)
    time_map_duration = source_duration / explicit_speed
    if abs(source_duration - record_duration) <= 1e-6 and abs(explicit_speed - 1.0) <= 1e-6:
        return

    source_start = float(item["source_start"])
    source_end = float(item["source_end"])
    time_map = ET.SubElement(clip, "timeMap", {"frameSampling": "floor"})
    ET.SubElement(time_map, "timept", {"time": "0s", "interp": "linear", "value": fcpx_time(source_start, fps)})
    ET.SubElement(
        time_map,
        "timept",
        {
            "time": fcpx_time(time_map_duration, fps),
            "interp": "linear",
            "value": fcpx_time(source_end, fps),
        },
    )


def visual_layer_timing(item: dict, layer: dict) -> tuple[float, float, float]:
    source_start = float(layer.get("source_start", item["source_start"]))
    source_end = float(layer.get("source_end", item["source_end"]))
    duration = source_end - source_start
    if duration <= 0:
        raise ValueError("visual layer source_end must be greater than source_start")
    return source_start, source_end, duration


def visual_layer_source_id(item: dict, layer: dict) -> str:
    return str(layer.get("source", item["source"]))


def primary_visual_layer_index(item: dict) -> int | None:
    layers = item.get("visual_layers") or []
    candidates = []
    for index, layer in enumerate(layers):
        if visual_layer_source_id(item, layer) != str(item["source"]):
            continue
        layer_start, layer_end, _ = visual_layer_timing(item, layer)
        if abs(layer_start - float(item["source_start"])) > 1e-6 or abs(layer_end - float(item["source_end"])) > 1e-6:
            continue
        name = str(layer.get("name", layer.get("label", ""))).lower()
        dest = layer.get("dest_rect", layer.get("destination", layer.get("canvas_rect", {}))) or {}
        try:
            dest_area = float(dest.get("width", 0.0)) * float(dest.get("height", 0.0))
        except (TypeError, ValueError):
            dest_area = 0.0
        name_priority = 1 if any(token in name for token in ("gameplay", "screen", "main", "base")) else 0
        candidates.append((name_priority, dest_area, index))
    if not candidates:
        return None
    return max(candidates)[2]


def resolve_fit_scale(source_width: int, source_height: int, timeline_width: int, timeline_height: int) -> float:
    if source_width <= 0 or source_height <= 0 or timeline_width <= 0 or timeline_height <= 0:
        return 1.0
    return min(timeline_width / source_width, timeline_height / source_height)


def resolve_layer_transform(
    crop_rect,
    dest_rect,
    source_width: int,
    source_height: int,
    timeline_width: int,
    timeline_height: int,
) -> tuple[float, float, float]:
    if (
        crop_rect.width <= 0
        or crop_rect.height <= 0
        or dest_rect.width <= 0
        or dest_rect.height <= 0
        or source_width <= 0
        or source_height <= 0
        or timeline_width <= 0
        or timeline_height <= 0
    ):
        return 0.0, 0.0, 1.0

    desired_scale = dest_rect.width / crop_rect.width
    fit_scale = resolve_fit_scale(source_width, source_height, timeline_width, timeline_height)
    if fit_scale <= 0:
        return 0.0, 0.0, desired_scale
    resolve_position_scale = timeline_height / 100.0 if timeline_height > 0 else 1.0

    position_x = (dest_rect.center_x - timeline_width / 2.0) - desired_scale * (
        crop_rect.center_x - source_width / 2.0
    )
    position_y = timeline_height / 2.0 - dest_rect.center_y
    return position_x / resolve_position_scale, position_y / resolve_position_scale, desired_scale / fit_scale


def add_visual_adjustments(
    clip: ET.Element,
    layer: dict,
    *,
    source_width: int,
    source_height: int,
    timeline_width: int,
    timeline_height: int,
    resolve_crop_x_factor: float = DEFAULT_RESOLVE_CROP_X_FACTOR,
) -> None:
    source_rect = visual_layer_source_rect(layer, source_width, source_height)
    dest_rect = visual_layer_dest_rect(layer, timeline_width, timeline_height)
    crop_rect = aspect_fill_crop_rect(source_rect, dest_rect)
    trim = rect_trim_percentages(crop_rect, source_width, source_height)
    crop = ET.SubElement(clip, "adjust-crop", {"mode": "trim"})
    trim_attrs = {}
    horizontal_factor = resolve_crop_x_factor if resolve_crop_x_factor > 0 else 1.0
    for key in ("left", "right"):
        value = trim[key] / horizontal_factor
        if abs(value) > 1e-6:
            trim_attrs[key] = f"{value:.6f}".rstrip("0").rstrip(".")
    for key in ("top", "bottom"):
        if abs(trim[key]) > 1e-6:
            trim_attrs[key] = f"{trim[key]:.6f}".rstrip("0").rstrip(".")
    ET.SubElement(crop, "trim-rect", trim_attrs)
    position_x, position_y, scale = resolve_layer_transform(
        crop_rect,
        dest_rect,
        source_width,
        source_height,
        timeline_width,
        timeline_height,
    )
    ET.SubElement(
        clip,
        "adjust-transform",
        {
            "anchor": "0 0",
            "position": f"{position_x:.3f} {position_y:.3f}",
            "scale": f"{scale:.6f} {scale:.6f}",
        },
    )


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


def build_fcpxml(edl_path: Path, *, resolve_crop_x_factor: float = DEFAULT_RESOLVE_CROP_X_FACTOR) -> ET.ElementTree:
    validation_errors = validate(edl_path)
    if validation_errors:
        raise ValueError("EDL validation failed: " + "; ".join(validation_errors))

    edl = read_json(edl_path)
    footage_root = edl_path.parent.parent
    fps = float(edl["fps"])
    media_by_path = load_media_index(edl_path.parent, footage_root)

    fcpxml = ET.Element("fcpxml", {"version": FCPXML_VERSION})
    resources = ET.SubElement(fcpxml, "resources")

    formats: dict[tuple[int, int], str] = {}
    asset_records: dict[Path, dict] = {}
    timeline_assets: dict[tuple[int, str], tuple[str, Path]] = {}
    asset_formats: dict[Path, str] = {}

    def ensure_format(width: int, height: int) -> str:
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
        return formats[format_key]

    for timeline_index, timeline in enumerate(edl["timelines"]):
        width, height = timeline["resolution"]
        sequence_format = ensure_format(int(width), int(height))
        for source_id, source_path in timeline["sources"].items():
            resolved = ensure_within(resolve_relative(source_path, footage_root), footage_root)
            record = asset_records.get(resolved)
            if record is None:
                record = {
                    "id": f"a{len(asset_records) + 1}",
                    "path": resolved,
                    "fallback_format": sequence_format,
                    "max_source_end": 0.0,
                }
                asset_records[resolved] = record
            timeline_assets[(timeline_index, source_id)] = (str(record["id"]), resolved)

    for timeline_index, timeline in enumerate(edl["timelines"]):
        for item in timeline["ranges"]:
            _, resolved = timeline_assets[(timeline_index, item["source"])]
            record = asset_records[resolved]
            record["max_source_end"] = max(float(record["max_source_end"]), float(item["source_end"]))
            for layer in item.get("visual_layers") or []:
                layer_source = str(layer.get("source", item["source"]))
                _, layer_resolved = timeline_assets[(timeline_index, layer_source)]
                layer_record = asset_records[layer_resolved]
                layer_record["max_source_end"] = max(
                    float(layer_record["max_source_end"]),
                    float(layer.get("source_end", item["source_end"])),
                )

    for record in asset_records.values():
        resolved = record["path"]
        media_info = media_by_path.get(resolved)
        try:
            media_duration = float((media_info or {}).get("duration") or 0.0)
        except (TypeError, ValueError):
            media_duration = 0.0
        declared_duration = media_duration if media_duration > 0 else float(record["max_source_end"])
        asset_format = str(record["fallback_format"])
        try:
            media_width = int((media_info or {}).get("width") or 0)
            media_height = int((media_info or {}).get("height") or 0)
        except (TypeError, ValueError):
            media_width = 0
            media_height = 0
        if media_width > 0 and media_height > 0:
            asset_format = ensure_format(media_width, media_height)
        asset_formats[resolved] = asset_format
        add_asset(
            resources,
            str(record["id"]),
            resolved,
            fcpx_time(declared_duration, fps),
            asset_format,
            media_info,
        )

    library = ET.SubElement(fcpxml, "library")
    event = ET.SubElement(library, "event", {"name": edl["project_name"]})

    for timeline_index, timeline in enumerate(edl["timelines"]):
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
            duration = range_timeline_duration(item)
            duration_frames = fcpx_frames(duration, fps)
            if duration_frames <= 0:
                raise ValueError(f"range {index + 1} duration rounds to zero frames")
            asset_id, _ = timeline_assets[(timeline_index, item["source"])]
            clip_name = item.get("beat") or item.get("quote") or f"Clip {index + 1}"
            visual_layers = item.get("visual_layers") or []
            primary_layer_index = primary_visual_layer_index(item)
            primary_layer = visual_layers[primary_layer_index] if primary_layer_index is not None else None
            clip = ET.SubElement(
                spine,
                "asset-clip",
                {
                    "name": str(primary_layer.get("name") if primary_layer else clip_name),
                    "ref": asset_id,
                    "offset": fcpx_time(record_start, fps),
                    "start": fcpx_time(source_start, fps),
                    "duration": fcpx_time_from_frames(duration_frames, fps),
                    "format": asset_formats[timeline_assets[(timeline_index, item["source"])][1]]
                    if primary_layer
                    else formats[(int(width), int(height))],
                    "audioRole": "dialogue",
                    "videoRole": "video",
                },
            )
            if item.get("reason"):
                ET.SubElement(clip, "note").text = str(item["reason"])
            metadata = ET.SubElement(clip, "metadata")
            ET.SubElement(
                metadata,
                "md",
                {
                    "key": RANGE_ID_METADATA_KEY,
                    "value": range_id_for(timeline_index, index, item),
                },
            )
            add_time_map(clip, item, fps)
            if visual_layers:
                if primary_layer is None:
                    clip.set("srcEnable", "audio")
                else:
                    layer_media = media_by_path.get(timeline_assets[(timeline_index, item["source"])][1].resolve(), {})
                    source_width = int(primary_layer.get("source_width", layer_media.get("width") or width))
                    source_height = int(primary_layer.get("source_height", layer_media.get("height") or height))
                    add_visual_adjustments(
                        clip,
                        primary_layer,
                        source_width=source_width,
                        source_height=source_height,
                        timeline_width=int(width),
                        timeline_height=int(height),
                        resolve_crop_x_factor=resolve_crop_x_factor,
                    )
                for layer_index, layer in enumerate(visual_layers):
                    if primary_layer_index is not None and layer_index == primary_layer_index:
                        continue
                    layer_source = str(layer.get("source", item["source"]))
                    layer_asset_id, layer_path = timeline_assets[(timeline_index, layer_source)]
                    layer_source_start, _, _ = visual_layer_timing(item, layer)
                    layer_clip = ET.SubElement(
                        clip,
                        "asset-clip",
                        {
                            "name": str(layer.get("name") or layer.get("label") or f"Layer {layer_index + 1}"),
                            "ref": layer_asset_id,
                            "lane": str(int(layer.get("lane", layer.get("track", layer_index + 1)))),
                            "offset": fcpx_time(source_start, fps),
                            "start": fcpx_time(layer_source_start, fps),
                            "duration": fcpx_time_from_frames(duration_frames, fps),
                            "format": asset_formats[layer_path],
                            "srcEnable": "video",
                            "videoRole": "video",
                        },
                    )
                    layer_media = media_by_path.get(layer_path.resolve(), {})
                    source_width = int(layer.get("source_width", layer_media.get("width") or width))
                    source_height = int(layer.get("source_height", layer_media.get("height") or height))
                    add_time_map(layer_clip, {**item, **layer, "record_duration": duration}, fps)
                    add_visual_adjustments(
                        layer_clip,
                        layer,
                        source_width=source_width,
                        source_height=source_height,
                        timeline_width=int(width),
                        timeline_height=int(height),
                        resolve_crop_x_factor=resolve_crop_x_factor,
                    )
            else:
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
        duration = range_timeline_duration(item)
        end = max(end, record_start + duration)
        cursor = max(cursor, record_start + duration)
    return end


def _path_from_file_url(value: str) -> Path | None:
    parsed = urlparse(value)
    if parsed.scheme != "file":
        return None
    path = unquote(parsed.path)
    if len(path) >= 3 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return Path(path).resolve()


def _fcpx_time_seconds(value: str) -> float:
    if not value.endswith("s"):
        raise ValueError(f"FCPXML time does not end with 's': {value}")
    raw = value[:-1]
    if "/" in raw:
        numerator, denominator = raw.split("/", maxsplit=1)
        return float(Fraction(int(numerator), int(denominator)))
    return float(raw or 0)


def _required_source_ends_by_path(edl_path: Path, edl: dict) -> dict[Path, float]:
    footage_root = edl_path.parent.parent
    required: dict[Path, float] = {}
    for timeline in edl["timelines"]:
        sources = timeline["sources"]
        for item in timeline["ranges"]:
            source_path = ensure_within(resolve_relative(sources[item["source"]], footage_root), footage_root).resolve()
            required[source_path] = max(required.get(source_path, 0.0), float(item["source_end"]))
            for layer in item.get("visual_layers") or []:
                layer_source = str(layer.get("source", item["source"]))
                layer_path = ensure_within(resolve_relative(sources[layer_source], footage_root), footage_root).resolve()
                required[layer_path] = max(required.get(layer_path, 0.0), float(layer.get("source_end", item["source_end"])))
    return required


def fcpxml_integrity_issues(edl_path: Path, fcpxml_path: Path | None = None) -> list[str]:
    edl = read_json(edl_path)
    fps = float(edl["fps"])
    xml_path = fcpxml_path or default_fcpxml_path(edl_path, edl)
    root = ET.parse(xml_path).getroot()
    issues: list[str] = []
    required_source_ends = _required_source_ends_by_path(edl_path, edl)

    for asset in root.findall("./resources/asset"):
        media_rep = asset.find("./media-rep")
        source_path = _path_from_file_url(media_rep.attrib.get("src", "")) if media_rep is not None else None
        if source_path is None:
            continue
        required_end = required_source_ends.get(source_path)
        if required_end is None:
            continue
        declared_duration = _fcpx_time_seconds(asset.attrib.get("duration", "0s"))
        if declared_duration + (1 / fps) < required_end:
            issues.append(
                f"asset {asset.attrib.get('name', asset.attrib['id'])} declares {declared_duration:.3f}s "
                f"but EDL references source time {required_end:.3f}s"
            )

    projects = root.findall("./library/event/project")
    for timeline_index, timeline in enumerate(edl["timelines"]):
        if timeline_index >= len(projects):
            issues.append(f"timeline {timeline_index + 1} has no matching FCPXML project")
            continue
        primary_clips = projects[timeline_index].findall("./sequence/spine/asset-clip")
        ranges = sorted(timeline["ranges"], key=lambda item: float(item.get("record_start", 0)))
        for range_index, item in enumerate(ranges):
            expected_layers = item.get("visual_layers") or []
            if not expected_layers:
                continue
            if range_index >= len(primary_clips):
                issues.append(f"timeline {timeline_index + 1} range {range_index + 1} has no matching FCPXML clip")
                continue
            clip = primary_clips[range_index]
            layers = clip.findall("./asset-clip")
            primary_index = primary_visual_layer_index(item)
            expected_connected_count = len(expected_layers) if primary_index is None else len(expected_layers) - 1
            if primary_index is None and clip.attrib.get("srcEnable") != "audio":
                issues.append(
                    f"timeline {timeline_index + 1} range {range_index + 1} has visual_layers "
                    "but the primary FCPXML clip is not audio-only"
                )
            if primary_index is not None and clip.attrib.get("srcEnable") == "audio":
                issues.append(
                    f"timeline {timeline_index + 1} range {range_index + 1} has a primary visual layer "
                    "but the primary FCPXML clip is audio-only"
                )
            if len(layers) != expected_connected_count:
                issues.append(
                    f"timeline {timeline_index + 1} range {range_index + 1} expected "
                    f"{expected_connected_count} connected visual layer clips but FCPXML has {len(layers)}"
                )
                continue
            for layer_index, layer in enumerate(layers):
                if layer.attrib.get("srcEnable") != "video":
                    issues.append(
                        f"timeline {timeline_index + 1} range {range_index + 1} layer {layer_index + 1} "
                        "is not video-only"
                    )

    return issues


def default_fcpxml_path(edl_path: Path, edl: dict | None = None) -> Path:
    payload = edl or read_json(edl_path)
    return edl_path.parent / f"{safe_filename(payload['project_name'], 'timeline')}.fcpxml"


def write_fcpxml(
    edl_path: Path,
    out_path: Path,
    *,
    resolve_crop_x_factor: float = DEFAULT_RESOLVE_CROP_X_FACTOR,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree = build_fcpxml(edl_path, resolve_crop_x_factor=resolve_crop_x_factor)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export FCPXML from video-timeline-copilot EDL")
    parser.add_argument("edl", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="Output .fcpxml path")
    parser.add_argument(
        "--resolve-crop-x-factor",
        type=float,
        default=DEFAULT_RESOLVE_CROP_X_FACTOR,
        help="Resolve horizontal crop import factor used to serialize visual-layer left/right trim values",
    )
    args = parser.parse_args()

    edl_path = args.edl.resolve()
    edl = read_json(edl_path)
    out_path = args.out or default_fcpxml_path(edl_path, edl)

    result = write_fcpxml(edl_path, out_path, resolve_crop_x_factor=args.resolve_crop_x_factor)
    print(f"FCPXML -> {result}")


if __name__ == "__main__":
    main()
