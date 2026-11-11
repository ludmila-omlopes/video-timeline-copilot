from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
import unicodedata


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def is_image_path(path: str | Path) -> bool:
    return Path(str(path)).suffix.lower() in IMAGE_EXTENSIONS


def fold_text(text: str) -> str:
    """Lowercase, strip accents and punctuation so spoken phrases compare loosely."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    stripped = re.sub(r"[^\w\s]", " ", stripped.lower())
    return re.sub(r"\s+", " ", stripped).strip()


def clock(seconds: float) -> str:
    """Format seconds as HH:MM:SS for labels and file names."""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_clock(value: str | float | int) -> float:
    """Parse seconds, MM:SS, or HH:MM:SS(.fraction) into seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"unsupported time value: {value!r}")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_relative(path: str, base_dir: Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return (base_dir / p).resolve()


def ensure_within(path: Path, root: Path) -> Path:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"path escapes workspace: {resolved_path}") from exc
    return resolved_path


def safe_filename(value: str, fallback: str = "untitled") -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return name or fallback


def seconds_to_frames(seconds: float, fps: float) -> int:
    return int(round(seconds * fps))


def srt_timestamp(seconds: float) -> str:
    total_ms = int(round(max(0.0, seconds) * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"
