from __future__ import annotations

import argparse
import re
from difflib import SequenceMatcher
from pathlib import Path

from helpers.common import read_json
from helpers.video_analysis import analysis_to_lines


def fmt(seconds: float) -> str:
    return f"{seconds:06.2f}"


def group_words(words: list[dict], silence_threshold: float) -> list[dict]:
    phrases = []
    current = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        text = " ".join((w.get("text") or "").strip() for w in current).strip()
        phrases.append({"start": current[0]["start"], "end": current[-1]["end"], "text": text})
        current = []

    previous_end = None
    for word in words:
        start = word.get("start")
        end = word.get("end")
        if start is None or end is None:
            continue
        if previous_end is not None and start - previous_end >= silence_threshold:
            flush()
        current.append(word)
        previous_end = end
    flush()
    return phrases


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def repeated_delivery_note(
    phrase: dict,
    previous_phrases: list[dict],
    *,
    repeat_window: float,
    similarity_threshold: float,
    min_words: int,
) -> str | None:
    text = normalize_text(phrase.get("text") or "")
    words = text.split()
    if len(words) < min_words:
        return None

    for previous in reversed(previous_phrases):
        if phrase["start"] - previous["end"] > repeat_window:
            break

        previous_text = normalize_text(previous.get("text") or "")
        previous_words = previous_text.split()
        if len(previous_words) < min_words:
            continue

        shorter, longer = sorted((text, previous_text), key=len)
        contains_retake = len(shorter.split()) >= min_words and shorter in longer
        starts_same = words[:min_words] == previous_words[:min_words]
        similar = SequenceMatcher(None, text, previous_text).ratio() >= similarity_threshold

        if contains_retake or starts_same or similar:
            return (
                f"possible repeated take of {fmt(previous['start'])}-{fmt(previous['end'])}; "
                "use only the cleanest complete delivery"
            )

    return None


def video_analysis_lines(edit_dir: Path, source_stem: str) -> list[str]:
    analysis_path = edit_dir / "video_analysis" / f"{source_stem}.json"
    if not analysis_path.exists():
        return [
            "No cached video analysis found; continue transcript-only or run "
            "`vtc analyze-video --edit-dir <edit-dir>` when visual events matter."
        ]
    return analysis_to_lines(read_json(analysis_path))


def build_packed_lines(
    edit_dir: Path,
    *,
    silence_threshold: float,
    repeat_window: float,
    similarity_threshold: float,
    min_words: int,
    include_video_analysis: bool = True,
) -> list[str]:
    transcripts_dir = edit_dir / "transcripts"
    files = sorted(transcripts_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no transcript JSON files found in {transcripts_dir}")

    lines = ["# Packed transcripts", ""]
    for path in files:
        data = read_json(path)
        phrases = group_words(data.get("words", []), silence_threshold)
        duration = data.get("duration", 0.0)
        lines.append(f"## {path.stem} (duration: {duration:.1f}s, {len(phrases)} phrases)")
        if include_video_analysis:
            lines.append("")
            lines.append("### Visual context")
            lines.extend(video_analysis_lines(edit_dir, path.stem))
            lines.append("")
            lines.append("### Transcript phrases")
        previous_phrases: list[dict] = []
        for phrase in phrases:
            note = repeated_delivery_note(
                phrase,
                previous_phrases,
                repeat_window=repeat_window,
                similarity_threshold=similarity_threshold,
                min_words=min_words,
            )
            suffix = f"  [NOTE: {note}]" if note else ""
            lines.append(f" [{fmt(phrase['start'])}-{fmt(phrase['end'])}] {phrase['text']}{suffix}")
            previous_phrases.append(phrase)
        lines.append("")

    return lines


def pack_transcripts(
    edit_dir: Path,
    *,
    silence_threshold: float,
    repeat_window: float,
    similarity_threshold: float,
    min_words: int,
    include_video_analysis: bool = True,
) -> Path:
    lines = build_packed_lines(
        edit_dir,
        silence_threshold=silence_threshold,
        repeat_window=repeat_window,
        similarity_threshold=similarity_threshold,
        min_words=min_words,
        include_video_analysis=include_video_analysis,
    )
    out = edit_dir / "takes_packed.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Pack transcript JSON files into takes_packed.md")
    parser.add_argument("--edit-dir", type=Path, required=True)
    parser.add_argument("--silence-threshold", type=float, default=0.5)
    parser.add_argument("--repeat-window", type=float, default=45.0)
    parser.add_argument("--repeat-similarity", type=float, default=0.82)
    parser.add_argument("--repeat-min-words", type=int, default=3)
    parser.add_argument(
        "--no-video-analysis",
        action="store_true",
        help="Do not include cached edit/video_analysis/*.json context in takes_packed.md",
    )
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    try:
        out = pack_transcripts(
            edit_dir,
            silence_threshold=args.silence_threshold,
            repeat_window=args.repeat_window,
            similarity_threshold=args.repeat_similarity,
            min_words=args.repeat_min_words,
            include_video_analysis=not args.no_video_analysis,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    transcript_count = len(list((edit_dir / "transcripts").glob("*.json")))
    print(f"packed {transcript_count} transcript(s) -> {out}")


if __name__ == "__main__":
    main()
