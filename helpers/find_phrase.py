from __future__ import annotations

import argparse
import json
from difflib import SequenceMatcher
from pathlib import Path

from helpers.common import clock, fold_text, read_json
from helpers.dialogue import transcript_path_for, transcripts_dir


def word_tokens(words: list[dict]) -> list[dict]:
    """One entry per spoken token, each pointing back to the word that carries its timing."""
    tokens = []
    for index, word in enumerate(words):
        if word.get("start") is None or word.get("end") is None:
            continue
        for token in fold_text(word.get("text") or "").split():
            tokens.append({"token": token, "word": index})
    return tokens


def _context(words: list[dict], first: int, last: int, size: int) -> tuple[str, str]:
    before = "".join((word.get("text") or "") for word in words[max(0, first - size) : first]).strip()
    after = "".join((word.get("text") or "") for word in words[last + 1 : last + 1 + size]).strip()
    return before, after


def find_in_words(words: list[dict], phrase: str, *, min_ratio: float = 0.82, context_words: int = 6) -> list[dict]:
    query = fold_text(phrase).split()
    if not query:
        raise ValueError("phrase has no searchable words")
    tokens = word_tokens(words)
    size = len(query)
    query_text = " ".join(query)
    query_set = set(query)
    matches: list[dict] = []

    for offset in range(0, max(0, len(tokens) - size) + 1):
        window = tokens[offset : offset + size]
        if len(window) < size:
            break
        texts = [item["token"] for item in window]
        if texts == query:
            ratio = 1.0
        else:
            if min_ratio >= 1.0 or not query_set.intersection(texts):
                continue
            ratio = SequenceMatcher(None, query_text, " ".join(texts)).ratio()
            if ratio < min_ratio:
                continue
        first = window[0]["word"]
        last = window[-1]["word"]
        before, after = _context(words, first, last, context_words)
        matches.append(
            {
                "start": float(words[first]["start"]),
                "end": float(words[last]["end"]),
                "ratio": round(ratio, 3),
                "text": "".join((word.get("text") or "") for word in words[first : last + 1]).strip(),
                "before": before,
                "after": after,
            }
        )

    # Overlapping fuzzy windows describe the same spot; keep the best one of each cluster.
    matches.sort(key=lambda item: (-item["ratio"], item["start"]))
    kept: list[dict] = []
    for match in matches:
        if any(match["start"] < other["end"] and other["start"] < match["end"] for other in kept):
            continue
        kept.append(match)
    return sorted(kept, key=lambda item: (-item["ratio"], item["start"]))


def find_phrase(edit_dir: Path, phrase: str, *, source: str | None = None, min_ratio: float = 0.82, limit: int = 10) -> list[dict]:
    if source:
        files = [transcript_path_for(edit_dir, source)]
    else:
        files = sorted(transcripts_dir(edit_dir).glob("*.json"))
        if not files:
            raise FileNotFoundError(f"no transcript JSON files found in {transcripts_dir(edit_dir)}")
    results = []
    for path in files:
        transcript = read_json(path)
        for match in find_in_words(transcript.get("words") or [], phrase, min_ratio=min_ratio):
            results.append({"source": path.stem, **match})
    results.sort(key=lambda item: (-item["ratio"], item["source"], item["start"]))
    return results[:limit] if limit > 0 else results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find where a phrase is spoken across the cached transcripts, with word-level in and out times"
    )
    parser.add_argument("phrase")
    parser.add_argument("--edit-dir", type=Path, required=True)
    parser.add_argument("--source", default=None, help="Search one source only")
    parser.add_argument("--min-ratio", type=float, default=0.82, help="1.0 for exact wording only; lower tolerates mishearings")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        results = find_phrase(args.edit_dir.resolve(), args.phrase, source=args.source, min_ratio=args.min_ratio, limit=args.limit)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return
    if not results:
        print("no match")
        return
    for item in results:
        kind = "exact" if item["ratio"] >= 1.0 else f"close {item['ratio']:.2f}"
        print(
            f"{item['source']} [{clock(item['start'])} {item['start']:.3f}-{item['end']:.3f}] ({kind}) "
            f"...{item['before']} >>{item['text']}<< {item['after']}..."
        )


if __name__ == "__main__":
    main()
