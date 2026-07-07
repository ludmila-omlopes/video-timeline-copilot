from __future__ import annotations

import argparse
import re
from difflib import SequenceMatcher
from pathlib import Path

from helpers.common import read_json
from helpers.video_analysis import analysis_to_lines


CORRECTION_ANCHORS = {"ao", "aos", "da", "das", "de", "do", "dos", "em", "na", "nas", "no", "nos", "para"}
ENUMERATION_STARTERS = {"depois", "primeiro", "segunda", "segundo", "terceira", "terceiro"}
STOPWORD_TOKENS = {
    "a",
    "an",
    "and",
    "as",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "the",
}


def fmt(seconds: float) -> str:
    return f"{seconds:06.2f}"


def _group_word_items(words: list[dict], silence_threshold: float) -> list[list[dict]]:
    groups = []
    current = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        groups.append(current)
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
    return groups


def _phrase_from_word_items(words: list[dict], *, include_words: bool = False) -> dict:
    text = " ".join((w.get("text") or "").strip() for w in words).strip()
    phrase = {"start": words[0]["start"], "end": words[-1]["end"], "text": text}
    if include_words:
        phrase["words"] = list(words)
    return phrase


def group_words(words: list[dict], silence_threshold: float) -> list[dict]:
    return [_phrase_from_word_items(group) for group in _group_word_items(words, silence_threshold)]


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _phrase_token_items(phrase: dict) -> list[dict]:
    raw_words = phrase.get("words")
    if not raw_words:
        return [{"text": token, "start": None, "end": None} for token in normalize_text(phrase.get("text") or "").split()]

    tokens = []
    for word in raw_words:
        for token in normalize_text(word.get("text") or "").split():
            tokens.append({"text": token, "start": word.get("start"), "end": word.get("end")})
    return tokens


def _token_texts(tokens: list[dict]) -> list[str]:
    return [str(token["text"]) for token in tokens]


def _meaningful_window(tokens: list[dict]) -> bool:
    return any(len(str(token["text"])) > 2 for token in tokens)


def _content_window(tokens: list[dict]) -> bool:
    texts = _token_texts(tokens)
    return all(len(text) > 2 and text not in STOPWORD_TOKENS for text in texts)


def _window_timing_gap(left: list[dict], right: list[dict]) -> float | None:
    left_end = left[-1].get("end")
    right_start = right[0].get("start")
    if left_end is None or right_start is None:
        return None
    return float(right_start) - float(left_end)


def _has_enumeration_context(tokens: list[dict], first_index: int, second_index: int) -> bool:
    first_before = str(tokens[first_index - 1]["text"]) if first_index > 0 else ""
    second_before = str(tokens[second_index - 1]["text"]) if second_index > 0 else ""
    return (
        str(tokens[first_index]["text"]) in ENUMERATION_STARTERS
        or first_before in ENUMERATION_STARTERS
        or second_before in ENUMERATION_STARTERS
    )


def _intra_phrase_restart(phrase: dict, *, min_overlap_words: int) -> bool:
    tokens = _phrase_token_items(phrase)
    if len(tokens) < 3:
        return False

    max_window = min(4, len(tokens) // 2)
    for size in range(min_overlap_words, max_window + 1):
        for first_index in range(0, len(tokens) - (size * 2) + 1):
            left = tokens[first_index : first_index + size]
            if not _content_window(left):
                continue
            second_limit = min(len(tokens) - size + 1, first_index + size + 9)
            for second_index in range(first_index + size, second_limit):
                right = tokens[second_index : second_index + size]
                gap = _window_timing_gap(left, right)
                if gap is not None and gap < 0.15:
                    continue
                if _has_enumeration_context(tokens, first_index, second_index):
                    continue
                ratio = SequenceMatcher(None, _token_texts(left), _token_texts(right)).ratio()
                if ratio >= 0.8:
                    return True

    for first_index in range(len(tokens) - 2):
        anchor = str(tokens[first_index]["text"])
        if anchor not in CORRECTION_ANCHORS:
            continue
        second_limit = min(len(tokens) - 1, first_index + 9)
        for second_index in range(first_index + 2, second_limit):
            if str(tokens[second_index]["text"]) != anchor:
                continue
            gap = _window_timing_gap([tokens[first_index]], [tokens[second_index]])
            if gap is not None and gap < 0.15:
                continue
            first_next = str(tokens[first_index + 1]["text"])
            second_next = str(tokens[second_index + 1]["text"])
            if first_next != second_next and len(first_next) > 2 and len(second_next) > 2:
                return True

    return False


def _cross_phrase_restart(
    phrase: dict,
    previous: dict,
    *,
    min_overlap_words: int,
    max_restart_gap: float,
) -> bool:
    if float(phrase["start"]) - float(previous["end"]) > max_restart_gap:
        return False

    current_tokens = _phrase_token_items(phrase)
    previous_tail = _phrase_token_items(previous)[-6:]
    if len(current_tokens) < min_overlap_words or len(previous_tail) < min_overlap_words:
        return False

    prefix = current_tokens[:min_overlap_words]
    if _content_window(prefix):
        for index in range(0, len(previous_tail) - min_overlap_words + 1):
            window = previous_tail[index : index + min_overlap_words]
            ratio = SequenceMatcher(None, _token_texts(prefix), _token_texts(window)).ratio()
            if ratio >= 0.8:
                return True

    first = str(current_tokens[0]["text"])
    tail_texts = _token_texts(previous_tail)
    if first not in tail_texts:
        return False
    first_tail_index = tail_texts.index(first)
    for current_token in current_tokens[1:4]:
        token_text = str(current_token["text"])
        if len(token_text) <= 2:
            continue
        if token_text in tail_texts[first_tail_index + 1 :]:
            return True
    return False


def restart_correction_note(
    phrase: dict,
    previous_phrases: list[dict],
    *,
    min_overlap_words: int = 2,
    max_restart_gap: float = 1.5,
) -> str | None:
    if min_overlap_words < 1:
        return None

    if _intra_phrase_restart(phrase, min_overlap_words=min_overlap_words):
        return (
            f"possible self-correction/restart of {fmt(phrase['start'])}-{fmt(phrase['end'])}; "
            "keep only the corrected delivery"
        )

    if previous_phrases:
        previous = previous_phrases[-1]
        if _cross_phrase_restart(
            phrase,
            previous,
            min_overlap_words=min_overlap_words,
            max_restart_gap=max_restart_gap,
        ):
            return (
                f"possible self-correction/restart of {fmt(previous['start'])}-{fmt(previous['end'])}; "
                "keep only the corrected delivery"
            )

    return None


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
    restart_overlap_words: int = 2,
    restart_max_gap: float = 1.5,
    include_video_analysis: bool = True,
) -> list[str]:
    transcripts_dir = edit_dir / "transcripts"
    files = sorted(transcripts_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no transcript JSON files found in {transcripts_dir}")

    lines = ["# Packed transcripts", ""]
    for path in files:
        data = read_json(path)
        phrases = [
            _phrase_from_word_items(group, include_words=True)
            for group in _group_word_items(data.get("words", []), silence_threshold)
        ]
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
            if note is None:
                note = restart_correction_note(
                    phrase,
                    previous_phrases,
                    min_overlap_words=restart_overlap_words,
                    max_restart_gap=restart_max_gap,
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
    restart_overlap_words: int = 2,
    restart_max_gap: float = 1.5,
    include_video_analysis: bool = True,
) -> Path:
    lines = build_packed_lines(
        edit_dir,
        silence_threshold=silence_threshold,
        repeat_window=repeat_window,
        similarity_threshold=similarity_threshold,
        min_words=min_words,
        restart_overlap_words=restart_overlap_words,
        restart_max_gap=restart_max_gap,
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
    parser.add_argument("--restart-overlap-words", type=int, default=2)
    parser.add_argument("--restart-max-gap", type=float, default=1.5)
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
            restart_overlap_words=args.restart_overlap_words,
            restart_max_gap=args.restart_max_gap,
            include_video_analysis=not args.no_video_analysis,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    transcript_count = len(list((edit_dir / "transcripts").glob("*.json")))
    print(f"packed {transcript_count} transcript(s) -> {out}")


if __name__ == "__main__":
    main()
