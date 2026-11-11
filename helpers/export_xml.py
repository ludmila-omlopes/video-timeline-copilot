from __future__ import annotations

import argparse
from fractions import Fraction
from pathlib import Path
import xml.etree.ElementTree as ET

from helpers.common import ensure_within, is_image_path, read_json, resolve_relative, safe_filename
from helpers.export_fcpxml import fcpx_frames, fps_fraction, load_media_index, timeline_duration
from helpers.timing import range_effective_speed, range_timeline_duration
from helpers.validate_edl import validate


XMEML_VERSION = "4"


def default_xml_path(edl_path: Path, edl: dict | None = None) -> Path:
    payload = edl or read_json(edl_path)
    return edl_path.parent / f"{safe_filename(payload['project_name'], 'timeline')}.xml"


def rate_parts(rate: Fraction) -> tuple[int, bool]:
    """FCP7 XML states a whole-number timebase plus an NTSC flag for the 1000/1001 rates."""
    ntsc = rate.denominator == 1001
    return int(round(float(rate))), ntsc


def add_rate(parent: ET.Element, rate: Fraction) -> None:
    timebase, ntsc = rate_parts(rate)
    element = ET.SubElement(parent, "rate")
    ET.SubElement(element, "timebase").text = str(timebase)
    ET.SubElement(element, "ntsc").text = "TRUE" if ntsc else "FALSE"


def source_rate(media_info: dict | None, fallback: Fraction) -> Fraction:
    raw = (media_info or {}).get("avg_frame_rate")
    if not raw:
        return fallback
    try:
        numerator, _, denominator = str(raw).partition("/")
        value = Fraction(int(numerator), int(denominator or 1))
    except (ValueError, ZeroDivisionError):
        return fallback
    if value <= 0:
        return fallback
    return fps_fraction(float(value))


def frames_at(seconds: float, rate: Fraction) -> int:
    return int(round(seconds * rate.numerator / rate.denominator))


def path_url(path: Path) -> str:
    return path.resolve().as_uri().replace("file:///", "file://localhost/", 1)


def text(parent: ET.Element, tag: str, value: object) -> ET.Element:
    element = ET.SubElement(parent, tag)
    element.text = str(value)
    return element


def unsupported_notes(timeline: dict) -> list[str]:
    """What a cuts-only interchange file leaves behind, so nothing is dropped silently."""
    notes = []
    for index, item in enumerate(sorted(timeline["ranges"], key=lambda value: float(value.get("record_start", 0.0)))):
        if item.get("visual_layers"):
            notes.append(f"range {index + 1}: visual_layers layout is not carried; the clip arrives full frame")
        elif item.get("transform"):
            notes.append(f"range {index + 1}: zoom/pan/tilt is not carried; reapply the framing in the editor")
    return notes


def build_xml(edl_path: Path) -> tuple[ET.ElementTree, list[str]]:
    validation_errors = validate(edl_path)
    if validation_errors:
        raise ValueError("EDL validation failed: " + "; ".join(validation_errors))

    edl = read_json(edl_path)
    footage_root = edl_path.parent.parent
    sequence_rate = fps_fraction(float(edl["fps"]))
    media_by_path = load_media_index(edl_path.parent, footage_root)

    for timeline in edl["timelines"]:
        if any(abs(range_effective_speed(item) - 1.0) > 1e-6 for item in timeline["ranges"]):
            raise ValueError("FCP7 XML export does not support retimed ranges; export FCPXML instead")

    root = ET.Element("xmeml", {"version": XMEML_VERSION})
    project = ET.SubElement(root, "project")
    text(project, "name", edl["project_name"])
    children = ET.SubElement(project, "children")

    file_ids: dict[Path, str] = {}
    written_files: set[Path] = set()
    notes: list[str] = []
    clip_counter = 0

    def file_element(parent: ET.Element, path: Path, still_frames: int = 0) -> None:
        file_id = file_ids.setdefault(path, f"file-{len(file_ids) + 1}")
        element = ET.SubElement(parent, "file", {"id": file_id})
        if path in written_files:
            return
        written_files.add(path)
        info = media_by_path.get(path.resolve()) or {}
        still = is_image_path(path)
        rate = sequence_rate if still else source_rate(info, sequence_rate)
        text(element, "name", path.name)
        text(element, "pathurl", path_url(path))
        add_rate(element, rate)
        duration_frames = still_frames if still else frames_at(float(info.get("duration") or 0.0), rate)
        if duration_frames > 0:
            text(element, "duration", duration_frames)
        media = ET.SubElement(element, "media")
        video = ET.SubElement(media, "video")
        if still:
            text(video, "stillframe", "TRUE")
        characteristics = ET.SubElement(video, "samplecharacteristics")
        add_rate(characteristics, rate)
        if info.get("width") and info.get("height"):
            text(characteristics, "width", int(info["width"]))
            text(characteristics, "height", int(info["height"]))
        channels = 0 if still else audio_channels(info)
        if channels:
            audio = ET.SubElement(media, "audio")
            audio_characteristics = ET.SubElement(audio, "samplecharacteristics")
            text(audio_characteristics, "depth", 16)
            text(audio_characteristics, "samplerate", int(info.get("audio_rate") or 48000))
            text(audio, "channelcount", channels)

    for timeline_index, timeline in enumerate(edl["timelines"]):
        width, height = [int(value) for value in timeline["resolution"]]
        notes.extend(f"{timeline['name']}: {note}" for note in unsupported_notes(timeline))
        sequence = ET.SubElement(children, "sequence", {"id": f"sequence-{timeline_index + 1}"})
        text(sequence, "name", timeline["name"])
        text(sequence, "duration", fcpx_frames(timeline_duration(timeline), float(edl["fps"])))
        add_rate(sequence, sequence_rate)
        timecode = ET.SubElement(sequence, "timecode")
        add_rate(timecode, sequence_rate)
        text(timecode, "string", "00:00:00:00")
        text(timecode, "frame", 0)
        text(timecode, "displayformat", "NDF")

        media = ET.SubElement(sequence, "media")
        video = ET.SubElement(media, "video")
        video_format = ET.SubElement(video, "format")
        characteristics = ET.SubElement(video_format, "samplecharacteristics")
        add_rate(characteristics, sequence_rate)
        text(characteristics, "width", width)
        text(characteristics, "height", height)
        text(characteristics, "pixelaspectratio", "square")
        video_track = ET.SubElement(video, "track")

        audio = ET.SubElement(media, "audio")
        text(audio, "numOutputChannels", 2)
        audio_format = ET.SubElement(audio, "format")
        audio_characteristics = ET.SubElement(audio_format, "samplecharacteristics")
        text(audio_characteristics, "depth", 16)
        text(audio_characteristics, "samplerate", 48000)
        audio_tracks = [ET.SubElement(audio, "track"), ET.SubElement(audio, "track")]

        sources = {
            source_id: ensure_within(resolve_relative(source_path, footage_root), footage_root)
            for source_id, source_path in timeline["sources"].items()
        }
        still_holds: dict[Path, int] = {}
        for item in timeline["ranges"]:
            path = sources[item["source"]]
            if is_image_path(path):
                still_holds[path] = max(still_holds.get(path, 0), frames_at(range_timeline_duration(item), sequence_rate))

        audio_clip_index = [0, 0]
        cursor = 0.0
        ordered = sorted(timeline["ranges"], key=lambda value: float(value.get("record_start", 0.0)))
        for range_index, item in enumerate(ordered):
            path = sources[item["source"]]
            info = media_by_path.get(path.resolve()) or {}
            still = is_image_path(path)
            clip_rate = sequence_rate if still else source_rate(info, sequence_rate)
            record_start = float(item.get("record_start", cursor))
            duration = range_timeline_duration(item)
            start_frame = fcpx_frames(record_start, float(edl["fps"]))
            end_frame = start_frame + max(1, fcpx_frames(duration, float(edl["fps"])))
            in_frame = 0 if still else frames_at(float(item["source_start"]), clip_rate)
            out_frame = in_frame + max(1, frames_at(duration, clip_rate))
            file_duration = still_holds.get(path, 0) if still else frames_at(float(info.get("duration") or 0.0), clip_rate)
            channels = 0 if still or item.get("mute") else audio_channels(info)

            clip_counter += 1
            video_id = f"clipitem-{clip_counter}"
            audio_ids = []
            for _ in range(channels):
                clip_counter += 1
                audio_ids.append(f"clipitem-{clip_counter}")

            def clip_item(track: ET.Element, clip_id: str) -> ET.Element:
                clip = ET.SubElement(track, "clipitem", {"id": clip_id})
                text(clip, "name", path.name)
                text(clip, "enabled", "TRUE")
                if file_duration > 0:
                    text(clip, "duration", file_duration)
                add_rate(clip, clip_rate)
                text(clip, "start", start_frame)
                text(clip, "end", end_frame)
                text(clip, "in", in_frame)
                text(clip, "out", out_frame)
                file_element(clip, path, still_holds.get(path, 0))
                return clip

            def add_links(clip: ET.Element) -> None:
                if not audio_ids:
                    return
                link = ET.SubElement(clip, "link")
                text(link, "linkclipref", video_id)
                text(link, "mediatype", "video")
                text(link, "trackindex", 1)
                text(link, "clipindex", range_index + 1)
                for channel, audio_id in enumerate(audio_ids):
                    link = ET.SubElement(clip, "link")
                    text(link, "linkclipref", audio_id)
                    text(link, "mediatype", "audio")
                    text(link, "trackindex", channel + 1)
                    text(link, "clipindex", audio_clip_index[channel] + 1)
                    text(link, "groupindex", 1)

            video_clip = clip_item(video_track, video_id)
            if still:
                text(video_clip, "stillframe", "TRUE")
            label = item.get("beat") or item.get("quote")
            if label or item.get("reason"):
                comments = ET.SubElement(video_clip, "comments")
                if label:
                    text(comments, "mastercomment1", label)
                if item.get("reason"):
                    text(comments, "mastercomment2", item["reason"])
            add_links(video_clip)

            for channel, audio_id in enumerate(audio_ids):
                audio_clip = clip_item(audio_tracks[channel], audio_id)
                source_track = ET.SubElement(audio_clip, "sourcetrack")
                text(source_track, "mediatype", "audio")
                text(source_track, "trackindex", channel + 1)
                add_links(audio_clip)
            for channel in range(len(audio_ids)):
                audio_clip_index[channel] += 1

            if timeline.get("markers"):
                marker = ET.SubElement(sequence, "marker")
                text(marker, "name", item.get("beat") or item.get("quote") or "Edit")
                text(marker, "comment", item.get("reason") or item.get("quote") or "")
                text(marker, "in", start_frame)
                text(marker, "out", -1)
            cursor = max(cursor, record_start + duration)

    ET.indent(root, space="  ")
    return ET.ElementTree(root), notes


def audio_channels(media_info: dict | None) -> int:
    """Up to two channels are laid out; a source with no audio stream gets none."""
    info = media_info or {}
    if "audio_channels" not in info:
        return 2
    return max(0, min(2, int(info.get("audio_channels") or 0)))


def write_xml(edl_path: Path, out_path: Path) -> tuple[Path, list[str]]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree, notes = build_xml(edl_path)
    body = ET.tostring(tree.getroot(), encoding="unicode")
    out_path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + body + "\n", encoding="utf-8")
    return out_path, notes


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Export a cuts-only FCP7 XML (xmeml) from an EDL: for Premiere Pro, and as a fallback when "
            "Resolve imports an FCPXML with offline clips"
        )
    )
    parser.add_argument("edl", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="Output .xml path")
    args = parser.parse_args()

    edl_path = args.edl.resolve()
    try:
        result, notes = write_xml(edl_path, args.out or default_xml_path(edl_path))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    for note in notes:
        print(f"WARNING: {note}")
    print(f"FCP7 XML -> {result}")


if __name__ == "__main__":
    main()
