from __future__ import annotations

import argparse
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from helpers.common import safe_filename
from helpers.export_fcpxml import DEFAULT_RESOLVE_CROP_X_FACTOR
from helpers.media_tools import find_ffmpeg, video_dimensions


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


def path_from_src(src: str) -> Path:
    parsed = urlparse(src)
    if parsed.scheme == "file":
        return Path(url2pathname(parsed.path)).resolve()
    if parsed.scheme:
        raise ValueError(f"unsupported media src scheme: {parsed.scheme}")
    return Path(src).resolve()


def parse_pair(value: str | None, default: tuple[float, float]) -> tuple[float, float]:
    if not value:
        return default
    parts = value.split()
    if len(parts) != 2:
        return default
    return float(parts[0]), float(parts[1])


def format_dimensions(root: ET.Element) -> dict[str, tuple[int, int]]:
    formats = {}
    for item in descendants(root, "format"):
        format_id = item.attrib.get("id")
        width = item.attrib.get("width")
        height = item.attrib.get("height")
        if format_id and width and height:
            formats[format_id] = (int(width), int(height))
    return formats


def assets(root: ET.Element, formats: dict[str, tuple[int, int]]) -> dict[str, dict]:
    records = {}
    for item in descendants(root, "asset"):
        asset_id = item.attrib.get("id")
        media_rep = first_child(item, "media-rep")
        src = media_rep.attrib.get("src") if media_rep is not None else None
        if not asset_id or not src:
            continue
        path = path_from_src(src)
        dimensions = formats.get(item.attrib.get("format", ""))
        if dimensions is None:
            dimensions = video_dimensions(path)
        if dimensions is None:
            raise ValueError(f"could not determine video dimensions for {path}")
        records[asset_id] = {
            "path": path,
            "width": dimensions[0],
            "height": dimensions[1],
            "start": parse_fcpx_time(item.attrib.get("start", "0s")),
        }
    return records


def preview_path(fcpxml_path: Path, project_name: str) -> Path:
    return fcpxml_path.parent / "previews" / f"{safe_filename(project_name, 'fcpxml')}_fcpxml_preview.mp4"


def _even(value: float) -> int:
    rounded = max(2, int(round(value)))
    return rounded if rounded % 2 == 0 else rounded + 1


def _trimmed_source_rect(
    clip: ET.Element,
    *,
    source_width: int,
    source_height: int,
    timeline_width: int,
    timeline_height: int,
    resolve_crop_x_factor: float,
) -> tuple[int, int, int, int]:
    crop = first_child(clip, "adjust-crop")
    trim_rect = first_child(crop, "trim-rect") if crop is not None else None
    trim = trim_rect.attrib if trim_rect is not None else {}
    fit_scale = min(timeline_width / source_width, timeline_height / source_height)
    x_factor = resolve_crop_x_factor if resolve_crop_x_factor > 0 else 1.0

    left = float(trim.get("left", 0.0)) / 100.0 * source_width * x_factor
    right = float(trim.get("right", 0.0)) / 100.0 * source_width * x_factor
    top = float(trim.get("top", 0.0)) / 100.0 * source_height
    bottom = float(trim.get("bottom", 0.0)) / 100.0 * source_height
    if fit_scale <= 0:
        fit_scale = 1.0

    x = max(0, int(round(left)))
    y = max(0, int(round(top)))
    width = max(2, int(round(source_width - max(0.0, left) - max(0.0, right))))
    height = max(2, int(round(source_height - max(0.0, top) - max(0.0, bottom))))
    if x + width > source_width:
        width = max(2, source_width - x)
    if y + height > source_height:
        height = max(2, source_height - y)
    return x, y, width, height


def _layer_geometry(
    clip: ET.Element,
    *,
    crop_x: int,
    crop_width: int,
    crop_height: int,
    source_width: int,
    source_height: int,
    timeline_width: int,
    timeline_height: int,
) -> tuple[int, int, int, int]:
    transform = first_child(clip, "adjust-transform")
    scale_x, _ = parse_pair(transform.attrib.get("scale") if transform is not None else None, (1.0, 1.0))
    position_x, position_y = parse_pair(
        transform.attrib.get("position") if transform is not None else None,
        (0.0, 0.0),
    )
    fit_scale = min(timeline_width / source_width, timeline_height / source_height)
    display_width = _even(crop_width * fit_scale * scale_x)
    display_height = _even(crop_height * fit_scale * scale_x)
    display_scale = display_width / crop_width if crop_width > 0 else 1.0
    position_scale = timeline_height / 100.0
    center_x = (
        timeline_width / 2.0
        + position_x * position_scale
        + display_scale * (crop_x + crop_width / 2.0 - source_width / 2.0)
    )
    center_y = timeline_height / 2.0 - position_y * position_scale
    overlay_x = int(round(center_x - display_width / 2.0))
    overlay_y = int(round(center_y - display_height / 2.0))
    return overlay_x, overlay_y, display_width, display_height


def _segment_args(
    clip: ET.Element,
    *,
    asset_records: dict[str, dict],
    timeline_width: int,
    timeline_height: int,
    fps: float,
    out_path: Path,
    resolve_crop_x_factor: float,
) -> list[str]:
    duration = parse_fcpx_time(clip.attrib["duration"])
    layer_clips = [clip, *children(clip, "asset-clip")]
    media_inputs: list[str] = []
    filter_parts: list[str] = []
    for index, layer_clip in enumerate(layer_clips):
        ref = layer_clip.attrib["ref"]
        asset = asset_records[ref]
        start = (
            parse_fcpx_time(layer_clip.attrib["start"]) - float(asset.get("start", 0.0))
            if layer_clip.attrib.get("start")
            else 0.0
        )
        media_inputs.extend(["-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", str(asset["path"])])
        crop_x, crop_y, crop_w, crop_h = _trimmed_source_rect(
            layer_clip,
            source_width=asset["width"],
            source_height=asset["height"],
            timeline_width=timeline_width,
            timeline_height=timeline_height,
            resolve_crop_x_factor=resolve_crop_x_factor,
        )
        overlay_x, overlay_y, display_w, display_h = _layer_geometry(
            layer_clip,
            crop_x=crop_x,
            crop_width=crop_w,
            crop_height=crop_h,
            source_width=asset["width"],
            source_height=asset["height"],
            timeline_width=timeline_width,
            timeline_height=timeline_height,
        )
        filter_parts.append(
            (
                f"[{index}:v]fps={fps},crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
                f"scale={display_w}:{display_h},setsar=1,format=rgba[layer{index}]"
            )
        )
        if index == 0:
            canvas_index = len(layer_clips)
            filter_parts.append(f"[{canvas_index}:v]format=rgba[base0]")
        next_base = f"base{index + 1}"
        filter_parts.append(
            f"[base{index}][layer{index}]overlay=x={overlay_x}:y={overlay_y}:shortest=0:eof_action=pass[{next_base}]"
        )

    canvas_index = len(layer_clips)
    audio_index = canvas_index + 1
    media_inputs.extend(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={timeline_width}x{timeline_height}:r={fps}:d={duration:.6f}",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=stereo:sample_rate=48000:d={duration:.6f}",
        ]
    )
    filter_parts.append(f"[base{len(layer_clips)}]format=yuv420p[vout]")
    filter_parts.append(f"[{audio_index}:a]aresample=48000,apad[aout]")

    return [
        find_ffmpeg(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        *media_inputs,
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-t",
        f"{duration:.6f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(out_path),
    ]


def _concat_args(segment_paths: list[Path], list_path: Path, out_path: Path) -> list[str]:
    lines = []
    for segment_path in segment_paths:
        escaped = segment_path.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [
        find_ffmpeg(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(out_path),
    ]


def render_fcpxml_preview(
    fcpxml_path: Path,
    out_path: Path | None = None,
    *,
    project_name: str | None = None,
    resolve_crop_x_factor: float = DEFAULT_RESOLVE_CROP_X_FACTOR,
) -> Path:
    root = ET.parse(fcpxml_path).getroot()
    formats = format_dimensions(root)
    asset_records = assets(root, formats)
    projects = descendants(root, "project")
    if project_name:
        projects = [project for project in projects if project.attrib.get("name") == project_name]
    if not projects:
        raise ValueError(f"project not found: {project_name}" if project_name else "FCPXML has no project")
    project = projects[0]
    sequence = first_child(project, "sequence")
    spine = first_child(sequence, "spine") if sequence is not None else None
    if sequence is None or spine is None:
        raise ValueError("FCPXML project has no sequence/spine")
    timeline_width, timeline_height = formats[sequence.attrib["format"]]
    fps = 30.0
    destination = (out_path or preview_path(fcpxml_path, project.attrib.get("name", "fcpxml"))).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    clips = [clip for clip in children(spine, "asset-clip") if clip.attrib.get("duration")]
    if not clips:
        raise ValueError("FCPXML spine has no renderable asset-clip")

    with tempfile.TemporaryDirectory(prefix="vtc-fcpxml-preview-") as tmp:
        tmp_dir = Path(tmp)
        segments = []
        for index, clip in enumerate(clips):
            segment_path = tmp_dir / f"{index:04d}_clip.mp4"
            subprocess.run(
                _segment_args(
                    clip,
                    asset_records=asset_records,
                    timeline_width=timeline_width,
                    timeline_height=timeline_height,
                    fps=fps,
                    out_path=segment_path,
                    resolve_crop_x_factor=resolve_crop_x_factor,
                ),
                check=True,
            )
            segments.append(segment_path)
        subprocess.run(_concat_args(segments, tmp_dir / "concat.txt", destination), check=True)

    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Render an MP4 preview from an FCPXML file")
    parser.add_argument("fcpxml", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="Output preview .mp4 path")
    parser.add_argument("--project", default=None, help="Project/timeline name to render; defaults to the first")
    parser.add_argument(
        "--resolve-crop-x-factor",
        type=float,
        default=DEFAULT_RESOLVE_CROP_X_FACTOR,
        help="Resolve horizontal crop import factor used to interpret visual-layer left/right trim values",
    )
    args = parser.parse_args()
    result = render_fcpxml_preview(
        args.fcpxml.resolve(),
        args.out,
        project_name=args.project,
        resolve_crop_x_factor=args.resolve_crop_x_factor,
    )
    print(f"fcpxml preview -> {result}")


if __name__ == "__main__":
    main()
