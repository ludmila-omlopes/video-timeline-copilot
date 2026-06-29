from __future__ import annotations

import argparse
from pathlib import Path

from helpers.common import ensure_within, read_json, safe_filename, srt_timestamp
from helpers.timing import range_timeline_duration, source_time_to_record_time


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
    transcript_cache: dict[str, dict | None] = {}
    cursor = 0.0

    for item in sorted(timeline["ranges"], key=lambda r: float(r.get("record_start", 0))):
        source_id = item["source"]
        source_start = float(item["source_start"])
        source_end = float(item["source_end"])
        duration = range_timeline_duration(item)
        record_start = float(item.get("record_start", cursor))
        transcript_path = edit_dir / "transcripts" / f"{Path(timeline['sources'][source_id]).stem}.json"

        cache_key = str(transcript_path)
        if cache_key not in transcript_cache:
            transcript_cache[cache_key] = read_json(transcript_path) if transcript_path.exists() else None
        payload = transcript_cache[cache_key]
        if payload is None:
            cursor = max(cursor, record_start + duration)
            continue

        words = words_in_range(payload.get("words", []), source_start, source_end)
        chunk = []
        for word in words:
            chunk.append(word)
            text = (word.get("text") or "").strip()
            if len(chunk) >= 5 or (text and text[-1] in ".?!"):
                local_start = source_time_to_record_time(item, max(source_start, chunk[0]["start"]), record_start)
                local_end = source_time_to_record_time(item, min(source_end, chunk[-1]["end"]), record_start)
                entries.append((local_start, max(local_end, local_start + 0.3), " ".join(w["text"].strip() for w in chunk)))
                chunk = []
        if chunk:
            local_start = source_time_to_record_time(item, max(source_start, chunk[0]["start"]), record_start)
            local_end = source_time_to_record_time(item, min(source_end, chunk[-1]["end"]), record_start)
            entries.append((local_start, max(local_end, local_start + 0.3), " ".join(w["text"].strip() for w in chunk)))

        cursor = max(cursor, record_start + duration)

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
            target = ensure_within(
                edit_dir / "subtitles" / f"{safe_filename(str(timeline['name']), 'timeline')}.srt",
                edit_dir.parent,
            )
        build_srt_for_timeline(edl, timeline, edit_dir, target)
        print(f"SRT -> {target}")


if __name__ == "__main__":
    main()
