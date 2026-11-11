from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from helpers.common import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, write_json
from helpers.media_tools import ffprobe_json
from helpers.timecode import find_start_timecode


def ffprobe(path: Path) -> dict:
    payload = ffprobe_json(path)
    video_stream = next((s for s in payload.get("streams", []) if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in payload.get("streams", []) if s.get("codec_type") == "audio"), {})
    avg_frame_rate = video_stream.get("avg_frame_rate")
    item = {
        "path": str(path),
        "name": path.stem,
        "duration": float(payload.get("format", {}).get("duration", 0.0)),
        "width": int(video_stream.get("width", 0) or 0),
        "height": int(video_stream.get("height", 0) or 0),
        "video_codec": video_stream.get("codec_name"),
        "audio_codec": audio_stream.get("codec_name"),
        "audio_channels": int(audio_stream.get("channels", 0) or 0),
        "audio_rate": int(audio_stream.get("sample_rate", 0) or 0),
        "avg_frame_rate": avg_frame_rate,
    }
    start_timecode = find_start_timecode(payload)
    if start_timecode:
        item["start_timecode"] = start_timecode
        item["timecode_rate"] = avg_frame_rate
    return item


def file_fingerprint(path: Path) -> dict:
    """Size and modification time, used to notice a source that changed after it was analyzed."""
    try:
        stat = path.stat()
    except OSError:
        return {}
    return {"size": stat.st_size, "mtime": round(stat.st_mtime, 3)}


def iter_source_videos(root: Path, edit_dir: Path) -> list[Path]:
    """List source videos under root, excluding generated outputs and hidden directories."""
    return iter_source_files(root, edit_dir, VIDEO_EXTENSIONS)


def iter_source_images(root: Path, edit_dir: Path) -> list[Path]:
    """List still images (title cards, photos) under root, with the same exclusions as videos."""
    return iter_source_files(root, edit_dir, IMAGE_EXTENSIONS)


def iter_source_files(root: Path, edit_dir: Path, extensions: set[str]) -> list[Path]:
    videos = []
    edit_dir = edit_dir.resolve()
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in extensions:
            continue
        resolved = path.resolve()
        if edit_dir == resolved or edit_dir in resolved.parents:
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        videos.append(path)
    return videos


def main() -> None:
    parser = argparse.ArgumentParser(description="Index local video media into edit/media_index.json")
    parser.add_argument("folder", type=Path, help="Folder containing source media")
    parser.add_argument("--edit-dir", type=Path, default=None, help="Output edit directory")
    args = parser.parse_args()

    root = args.folder.resolve()
    edit_dir = (args.edit_dir or root / "edit").resolve()
    videos = iter_source_videos(root, edit_dir)
    items = []

    for video in videos:
        try:
            items.append({**ffprobe(video), **file_fingerprint(video)})
        except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            items.append({"path": str(video), "error": str(exc)})

    images = []
    for image in iter_source_images(root, edit_dir):
        entry = {"path": str(image), "name": image.stem, **file_fingerprint(image)}
        try:
            payload = ffprobe_json(image)
            stream = next((s for s in payload.get("streams", []) if s.get("codec_type") == "video"), {})
            entry["width"] = int(stream.get("width", 0) or 0)
            entry["height"] = int(stream.get("height", 0) or 0)
        except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            entry["error"] = str(exc)
        images.append(entry)

    out = edit_dir / "media_index.json"
    write_json(out, {"root": str(root), "media": items, "images": images})
    print(f"indexed {len(items)} video(s) and {len(images)} image(s) -> {out}")


if __name__ == "__main__":
    main()
