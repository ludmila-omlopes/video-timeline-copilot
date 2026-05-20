from __future__ import annotations

import argparse
from pathlib import Path

from helpers.common import read_json


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Pack transcript JSON files into takes_packed.md")
    parser.add_argument("--edit-dir", type=Path, required=True)
    parser.add_argument("--silence-threshold", type=float, default=0.5)
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    transcripts_dir = edit_dir / "transcripts"
    files = sorted(transcripts_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"no transcript JSON files found in {transcripts_dir}")

    lines = ["# Packed transcripts", ""]
    for path in files:
        data = read_json(path)
        phrases = group_words(data.get("words", []), args.silence_threshold)
        duration = data.get("duration", 0.0)
        lines.append(f"## {path.stem} (duration: {duration:.1f}s, {len(phrases)} phrases)")
        for phrase in phrases:
            lines.append(f" [{fmt(phrase['start'])}-{fmt(phrase['end'])}] {phrase['text']}")
        lines.append("")

    out = edit_dir / "takes_packed.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"packed {len(files)} transcript(s) -> {out}")


if __name__ == "__main__":
    main()
