from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
from pathlib import Path


def _find_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found

    exe = f"{name}.exe"
    candidates: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if packages.exists():
            candidates.extend(packages.glob(f"**/{exe}"))
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if root:
            candidates.extend(Path(root).glob(f"**/{exe}"))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    raise FileNotFoundError(
        f"{name} was not found on PATH or in common FFmpeg install locations. "
        "Install FFmpeg or add its bin directory to PATH."
    )


@functools.lru_cache(maxsize=None)
def find_ffmpeg() -> str:
    return _find_tool("ffmpeg")


@functools.lru_cache(maxsize=None)
def find_ffprobe() -> str:
    return _find_tool("ffprobe")


def ffprobe_json(path: Path) -> dict:
    proc = subprocess.run(
        [find_ffprobe(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def stream_types(path: Path) -> set[str]:
    return {stream.get("codec_type") for stream in ffprobe_json(path).get("streams", [])}


def media_duration(path: Path) -> float | None:
    value = ffprobe_json(path).get("format", {}).get("duration")
    return float(value) if value is not None else None
