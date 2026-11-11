from __future__ import annotations

import argparse
import math
import subprocess
import tempfile
from pathlib import Path

from helpers.common import clock, parse_clock, read_json, safe_filename, write_json
from helpers.media_tools import find_ffmpeg, media_duration


DEFAULT_FRAMES = 16
DEFAULT_COLUMNS = 4
SHORT_RANGE_SECONDS = 10.0
SHORT_RANGE_FRAMES = 8
DEFAULT_TILE_WIDTH = 480
DEFAULT_SEGMENT_MINUTES = 10.0


def sheets_dir(edit_dir: Path) -> Path:
    return edit_dir / "contact_sheets"


def sheet_layout(range_seconds: float, frames: int = DEFAULT_FRAMES, columns: int = DEFAULT_COLUMNS) -> tuple[int, int, int]:
    """Return (frames, columns, rows). Very short ranges get fewer tiles so frames do not repeat."""
    if range_seconds <= SHORT_RANGE_SECONDS:
        frames = min(frames, SHORT_RANGE_FRAMES)
    frames = max(1, frames)
    columns = max(1, min(columns, frames))
    rows = int(math.ceil(frames / columns))
    return frames, columns, rows


def sheet_times(start: float, end: float, frames: int) -> list[float]:
    """Evenly spaced sample times, each at the middle of its slice of the range."""
    span = end - start
    if span <= 0:
        raise ValueError("end must be greater than start")
    step = span / frames
    return [round(start + (index + 0.5) * step, 3) for index in range(frames)]


def time_label(seconds: float, range_seconds: float) -> str:
    if range_seconds < 60:
        tenths = int(round((seconds - int(seconds)) * 10))
        whole = int(seconds)
        if tenths == 10:
            whole, tenths = whole + 1, 0
        return f"{clock(whole)}.{tenths}"
    return clock(seconds)


def range_descriptor(start: float, end: float) -> str:
    return f"{clock(start).replace(':', '-')}_to_{clock(end).replace(':', '-')}"


def default_sheet_path(edit_dir: Path, video: Path, start: float | None, end: float | None) -> Path:
    stem = safe_filename(video.stem)
    descriptor = "full" if start is None and end is None else range_descriptor(start or 0.0, end or 0.0)
    return sheets_dir(edit_dir) / f"{stem}_{descriptor}.jpg"


def segment_ranges(duration: float, segment_seconds: float) -> list[tuple[float, float]]:
    """Split a long source into consecutive windows that each get their own closer sheet."""
    if segment_seconds <= 0 or duration <= segment_seconds:
        return []
    ranges = []
    cursor = 0.0
    while cursor < duration - 1.0:
        ranges.append((cursor, min(duration, cursor + segment_seconds)))
        cursor += segment_seconds
    return ranges


def sheets_for_source(edit_dir: Path, stem: str) -> list[Path]:
    """Contact sheets already built for a source, whole-clip sheet first."""
    folder = sheets_dir(edit_dir)
    if not folder.exists():
        return []
    prefix = f"{safe_filename(stem)}_"
    sheets = [path for path in folder.glob(f"{prefix}*.jpg")]
    return sorted(sheets, key=lambda path: (not path.stem.endswith("_full"), path.name))


def _escape_drawtext(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "")


def frame_filter(tile_width: int, label: str | None, font: Path | None = None) -> str:
    filters = [f"scale={tile_width}:-2"]
    if label:
        options = [
            f"text='{_escape_drawtext(label)}'",
            "x=8",
            "y=8",
            "fontsize=h/11",
            "fontcolor=white",
            "box=1",
            "boxcolor=black@0.65",
            "boxborderw=6",
        ]
        if font is not None:
            escaped_font = str(font).replace("\\", "/").replace(":", "\\:")
            options.insert(0, f"fontfile='{escaped_font}'")
        filters.append("drawtext=" + ":".join(options))
    return ",".join(filters)


def grab_frame(video: Path, seconds: float, out_path: Path, vf: str) -> None:
    subprocess.run(
        [
            find_ffmpeg(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{seconds:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            vf,
            "-q:v",
            "3",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def tile_frames(frames_dir: Path, out_path: Path, columns: int, rows: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            find_ffmpeg(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            "1",
            "-start_number",
            "0",
            "-i",
            str(frames_dir / "tile_%03d.jpg"),
            "-vf",
            f"tile={columns}x{rows}:padding=4:margin=4",
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def build_sheet(
    video: Path,
    out_path: Path,
    *,
    start: float,
    end: float,
    frames: int = DEFAULT_FRAMES,
    columns: int = DEFAULT_COLUMNS,
    tile_width: int = DEFAULT_TILE_WIDTH,
    font: Path | None = None,
) -> dict:
    """Build one grid image of evenly spaced frames, each stamped with its source time."""
    span = end - start
    frames, columns, rows = sheet_layout(span, frames, columns)
    times = sheet_times(start, end, frames)
    labelled = True

    with tempfile.TemporaryDirectory(prefix="vtc-sheet-") as tmp:
        tmp_dir = Path(tmp)
        for index, seconds in enumerate(times):
            target = tmp_dir / f"tile_{index:03d}.jpg"
            label = time_label(seconds, span) if labelled else None
            try:
                grab_frame(video, seconds, target, frame_filter(tile_width, label, font))
            except subprocess.CalledProcessError:
                if not labelled:
                    raise
                # Some FFmpeg builds ship without drawtext or a usable default font.
                labelled = False
                grab_frame(video, seconds, target, frame_filter(tile_width, None))
        tile_frames(tmp_dir, out_path, columns, rows)

    record = {
        "version": 1,
        "source": str(video),
        "sheet": out_path.name,
        "start": round(start, 3),
        "end": round(end, 3),
        "columns": columns,
        "rows": rows,
        "timestamps_burned_in": labelled,
        "frames": [
            {"tile": index + 1, "row": index // columns + 1, "column": index % columns + 1, "time": seconds, "label": time_label(seconds, span)}
            for index, seconds in enumerate(times)
        ],
    }
    write_json(out_path.with_suffix(".json"), record)
    return record


def source_videos_from_media_index(edit_dir: Path) -> list[Path]:
    index_path = edit_dir / "media_index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"no videos provided and media index not found: {index_path}")
    return [Path(item["path"]) for item in read_json(index_path).get("media") or [] if item.get("path") and not item.get("error")]


def build_sheets_for_video(
    video: Path,
    edit_dir: Path,
    *,
    start: float | None = None,
    end: float | None = None,
    frames: int = DEFAULT_FRAMES,
    columns: int = DEFAULT_COLUMNS,
    tile_width: int = DEFAULT_TILE_WIDTH,
    segment_seconds: float = DEFAULT_SEGMENT_MINUTES * 60,
    force: bool = False,
    font: Path | None = None,
    out_path: Path | None = None,
) -> list[Path]:
    duration = media_duration(video) or 0.0
    if duration <= 0:
        raise ValueError(f"could not read a duration for {video}")

    whole = start is None and end is None
    jobs: list[tuple[float, float, Path]] = []
    if whole:
        jobs.append((0.0, duration, out_path or default_sheet_path(edit_dir, video, None, None)))
        for segment_start, segment_end in segment_ranges(duration, segment_seconds):
            jobs.append((segment_start, segment_end, default_sheet_path(edit_dir, video, segment_start, segment_end)))
    else:
        range_start = float(start or 0.0)
        range_end = duration if end is None else float(end)
        if range_end > duration + 0.5:
            raise ValueError(f"end {clock(range_end)} is past the end of the source ({clock(duration)})")
        range_end = min(range_end, duration)
        if range_end <= range_start:
            raise ValueError("end must be greater than start")
        jobs.append((range_start, range_end, out_path or default_sheet_path(edit_dir, video, range_start, range_end)))

    written = []
    for job_start, job_end, target in jobs:
        if target.exists() and not force:
            written.append(target)
            continue
        build_sheet(video, target, start=job_start, end=job_end, frames=frames, columns=columns, tile_width=tile_width, font=font)
        written.append(target)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build contact sheets: one grid image of evenly spaced, time-stamped frames per source or range"
    )
    parser.add_argument("videos", nargs="*", type=Path, help="Source video(s). Defaults to edit/media_index.json entries.")
    parser.add_argument("--edit-dir", type=Path, required=True)
    parser.add_argument("--start", default=None, help="Range start (seconds, MM:SS, or HH:MM:SS) to zoom into")
    parser.add_argument("--end", default=None, help="Range end (seconds, MM:SS, or HH:MM:SS)")
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES)
    parser.add_argument("--columns", type=int, default=DEFAULT_COLUMNS)
    parser.add_argument("--tile-width", type=int, default=DEFAULT_TILE_WIDTH)
    parser.add_argument("--segment-minutes", type=float, default=DEFAULT_SEGMENT_MINUTES,
                        help="Sources longer than this also get one closer sheet per window; 0 disables")
    parser.add_argument("--font", type=Path, default=None, help="Font file for the burned-in timestamps")
    parser.add_argument("--out", type=Path, default=None, help="Exact output path (single video only)")
    parser.add_argument("--force", action="store_true", help="Rebuild sheets that already exist")
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    try:
        videos = [path.resolve() for path in args.videos] if args.videos else source_videos_from_media_index(edit_dir)
        if not videos:
            raise SystemExit("no source videos found for contact sheets")
        if args.out is not None and len(videos) != 1:
            raise SystemExit("--out needs exactly one video")
        start = parse_clock(args.start) if args.start is not None else None
        end = parse_clock(args.end) if args.end is not None else None
        for video in videos:
            sheets = build_sheets_for_video(
                video,
                edit_dir,
                start=start,
                end=end,
                frames=args.frames,
                columns=args.columns,
                tile_width=args.tile_width,
                segment_seconds=args.segment_minutes * 60,
                force=args.force or args.out is not None,
                font=args.font,
                out_path=args.out.resolve() if args.out else None,
            )
            for sheet in sheets:
                print(f"contact sheet {video.name} -> {sheet}")
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
