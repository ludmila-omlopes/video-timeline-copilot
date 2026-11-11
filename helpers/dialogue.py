from __future__ import annotations

import argparse
from pathlib import Path

from helpers.common import clock, parse_clock, read_json, safe_filename


def transcripts_dir(edit_dir: Path) -> Path:
    return edit_dir / "transcripts"


def transcript_path_for(edit_dir: Path, source: str) -> Path:
    """Accept a transcript stem, a media file name, or a media path."""
    folder = transcripts_dir(edit_dir)
    stem = Path(source).stem if Path(source).suffix else source
    for candidate in (folder / f"{stem}.json", folder / f"{safe_filename(stem)}.json"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no transcript for {source!r} in {folder}")


def segment_lines(transcript: dict, *, start: float | None = None, end: float | None = None, timestamps: bool = False) -> list[str]:
    lines = []
    for segment in transcript.get("segments") or []:
        seg_start = float(segment.get("start") or 0.0)
        seg_end = float(segment.get("end") or seg_start)
        if start is not None and seg_end < start:
            continue
        if end is not None and seg_start > end:
            continue
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{clock(seg_start)} {seg_start:.2f}-{seg_end:.2f}] {text}" if timestamps else text)
    return lines


def full_transcript_blocks(edit_dir: Path, *, timestamps: bool = False) -> list[str]:
    files = sorted(transcripts_dir(edit_dir).glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no transcript JSON files found in {transcripts_dir(edit_dir)}")
    blocks = []
    for path in files:
        transcript = read_json(path)
        name = Path(str(transcript.get("source") or path.stem)).name
        lines = segment_lines(transcript, timestamps=timestamps) or ["[no dialogue]"]
        blocks.append("\n".join([name, *lines]))
    return blocks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print one source's dialogue as clean text, or write every source's dialogue to one file"
    )
    parser.add_argument("source", nargs="?", default=None, help="Transcript stem, media file name, or media path")
    parser.add_argument("--edit-dir", type=Path, required=True)
    parser.add_argument("--all", action="store_true", help="Write every source to edit/full_transcript.txt")
    parser.add_argument("--from", dest="start", default=None, help="Only dialogue after this time")
    parser.add_argument("--to", dest="end", default=None, help="Only dialogue before this time")
    parser.add_argument("--timestamps", action="store_true", help="Prefix each line with its source time")
    parser.add_argument("--out", type=Path, default=None, help="Output path for --all")
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    try:
        if args.all:
            out = (args.out or edit_dir / "full_transcript.txt").resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            blocks = full_transcript_blocks(edit_dir, timestamps=args.timestamps)
            out.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
            print(f"full transcript ({len(blocks)} source(s)) -> {out}")
            return
        if not args.source:
            raise SystemExit("give a source, or use --all")
        transcript = read_json(transcript_path_for(edit_dir, args.source))
        start = parse_clock(args.start) if args.start is not None else None
        end = parse_clock(args.end) if args.end is not None else None
        lines = segment_lines(transcript, start=start, end=end, timestamps=args.timestamps)
        print("\n".join(lines) if lines else "[no dialogue]")
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
