from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from helpers.common import VIDEO_EXTENSIONS, write_json


def find_ffprobe() -> str:
    found = shutil.which("ffprobe")
    if found:
        return found

    candidates = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if packages.exists():
            candidates.extend(packages.glob("**/ffprobe.exe"))

    program_files = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]
    for root in program_files:
        if root:
            candidates.extend(Path(root).glob("**/ffprobe.exe"))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    raise FileNotFoundError(
        "ffprobe was not found on PATH or in common FFmpeg install locations. "
        "Install FFmpeg or add its bin directory to PATH."
    )


def ffprobe(path: Path) -> dict:
    cmd = [
        find_ffprobe(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    payload = json.loads(proc.stdout)
    video_stream = next((s for s in payload.get("streams", []) if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in payload.get("streams", []) if s.get("codec_type") == "audio"), {})
    return {
        "path": str(path),
        "name": path.stem,
        "duration": float(payload.get("format", {}).get("duration", 0.0)),
        "width": int(video_stream.get("width", 0) or 0),
        "height": int(video_stream.get("height", 0) or 0),
        "video_codec": video_stream.get("codec_name"),
        "audio_codec": audio_stream.get("codec_name"),
        "audio_channels": int(audio_stream.get("channels", 0) or 0),
        "audio_rate": int(audio_stream.get("sample_rate", 0) or 0),
        "avg_frame_rate": video_stream.get("avg_frame_rate"),
    }


def iter_source_videos(root: Path, edit_dir: Path) -> list[Path]:
    """List source videos under root, excluding generated outputs and hidden directories."""
    videos = []
    edit_dir = edit_dir.resolve()
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
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
            items.append(ffprobe(video))
        except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            items.append({"path": str(video), "error": str(exc)})

    out = edit_dir / "media_index.json"
    write_json(out, {"root": str(root), "media": items})
    print(f"indexed {len(items)} media file(s) -> {out}")


if __name__ == "__main__":
    main()
