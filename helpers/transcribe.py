from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def serialize_segments(segments) -> list[dict]:
    output = []
    for segment in segments:
        words = []
        for word in segment.words or []:
            words.append(
                {
                    "start": word.start,
                    "end": word.end,
                    "text": word.word,
                    "probability": word.probability,
                }
            )
        output.append(
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "words": words,
            }
        )
    return output


def print_progress(current: float, total: float) -> None:
    if total <= 0:
        return
    width = 30
    ratio = min(max(current / total, 0.0), 1.0)
    filled = int(width * ratio)
    bar = "#" * filled + "-" * (width - filled)
    percent = ratio * 100
    print(f"\rtranscribing [{bar}] {percent:5.1f}% ({current:0.1f}s/{total:0.1f}s)", end="", file=sys.stderr)


def collect_segments_with_progress(segments_iter, duration: float) -> list:
    segments = []
    print_progress(0.0, duration)
    for segment in segments_iter:
        segments.append(segment)
        print_progress(float(segment.end or 0.0), duration)
    print_progress(duration, duration)
    print(file=sys.stderr)
    return segments


def flatten_words(segments: list[dict]) -> list[dict]:
    words = []
    for segment in segments:
        words.extend(segment.get("words", []))
    return words


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe one video with faster-whisper")
    parser.add_argument("video", type=Path)
    parser.add_argument("--edit-dir", type=Path, default=None)
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--compute-type", default="auto")
    parser.add_argument("--language", default=None)
    parser.add_argument("--no-vad", action="store_true")
    args = parser.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper is not installed. Run: pip install '.[transcribe]' or pip install faster-whisper")

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    edit_dir = (args.edit_dir or video.parent / "edit").resolve()
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcripts_dir / f"{video.stem}.json"

    if out_path.exists():
        print(f"cached transcript -> {out_path}")
        return

    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    segments_iter, info = model.transcribe(
        str(video),
        language=args.language,
        word_timestamps=True,
        vad_filter=not args.no_vad,
        beam_size=5,
    )
    raw_segments = collect_segments_with_progress(segments_iter, float(info.duration or 0.0))
    segments = serialize_segments(raw_segments)
    payload = {
        "source": str(video),
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "segments": segments,
        "words": flatten_words(segments),
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"transcribed {video.name} -> {out_path}")


if __name__ == "__main__":
    main()
