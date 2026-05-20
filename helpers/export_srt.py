from __future__ import annotations

import argparse
from pathlib import Path

from helpers.common import ensure_within, read_json, srt_timestamp


def words_in_range(words: list[dict], start: float, end: float) -> list[dict]:
    return [
        word
        for word in words
        if word.get("start") is not None
        and word.get("end") is not None
        and word["end"] > start
        and word["start"] < end
    ]


def build_srt_for_timeline(edl: dict, timeline: dict, edit_dir: Path, out_path: Path) -> None:
    entries = []
    transcript_cache: dict[str, dict] = {}
    offset = 0.0

    for item in sorted(timeline["ranges"], key=lambda r: float(r.get("record_start", 0))):
        source_id = item["source"]
        source_start = float(item["source_start"])
        source_end = float(item["source_end"])
        duration = source_end - source_start
        transcript_path = edit_dir / "transcripts" / f"{Path(timeline['sources'][source_id]).stem}.json"

        if transcript_path not in transcript_cache:
            if not transcript_path.exists():
                offset += duration
                continue
            transcript_cache[str(transcript_path)] = read_json(transcript_path)

        words = words_in_range(transcript_cache[str(transcript_path)].get("words", []), source_start, source_end)
        chunk = []
        for word in words:
            chunk.append(word)
            text = (word.get("text") or "").strip()
            if len(chunk) >= 5 or (text and text[-1] in ".?!"):
                local_start = max(source_start, chunk[0]["start"]) - source_start + offset
                local_end = min(source_end, chunk[-1]["end"]) - source_start + offset
                entries.append((local_start, max(local_end, local_start + 0.3), " ".join(w["text"].strip() for w in chunk)))
                chunk = []
        if chunk:
            local_start = max(source_start, chunk[0]["start"]) - source_start + offset
            local_end = min(source_end, chunk[-1]["end"]) - source_start + offset
            entries.append((local_start, max(local_end, local_start + 0.3), " ".join(w["text"].strip() for w in chunk)))

        offset += duration

    lines = []
    for index, (start, end, text) in enumerate(entries, start=1):
        lines.extend([str(index), f"{srt_timestamp(start)} --> {srt_timestamp(end)}", text.strip(), ""])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SRT subtitle files from EDL and transcript cache")
    parser.add_argument("edl", type=Path)
    args = parser.parse_args()

    edl_path = args.edl.resolve()
    edl = read_json(edl_path)
    edit_dir = edl_path.parent
    for timeline in edl["timelines"]:
        subtitle_spec = timeline.get("subtitles") or {}
        out_path = subtitle_spec.get("path")
        if out_path:
            target = ensure_within(edit_dir.parent / out_path, edit_dir.parent)
        else:
            target = edit_dir / "subtitles" / f"{timeline['name'].replace(' ', '_')}.srt"
        build_srt_for_timeline(edl, timeline, edit_dir, target)
        print(f"SRT -> {target}")


if __name__ == "__main__":
    main()
