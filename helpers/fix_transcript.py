from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from helpers.common import fold_text, read_json, write_json
from helpers.dialogue import transcript_path_for, transcripts_dir
from helpers.project_context import load_context


EDGE_RE = re.compile(r"^(?P<lead>\s*[^\w\s]*)(?P<core>.*?)(?P<trail>[^\w\s]*\s*)$", re.DOTALL)


def parse_replacement(raw: str) -> tuple[str, str]:
    """Parse 'heard => correct'."""
    heard, separator, correct = raw.partition("=>")
    heard, correct = heard.strip(), correct.strip()
    if not separator or not heard or not correct:
        raise ValueError(f"expected 'heard => correct', got {raw!r}")
    return heard, correct


def glossary_replacements(context: dict) -> list[tuple[str, str]]:
    pairs = []
    for entry in context.get("glossary") or []:
        term = str(entry.get("term") or "").strip()
        for heard in entry.get("heard_as") or []:
            heard = str(heard).strip()
            if term and heard and fold_text(heard) != fold_text(term):
                pairs.append((heard, term))
    return pairs


def _edges(text: str) -> tuple[str, str]:
    match = EDGE_RE.match(text or "")
    if match is None:
        return "", ""
    return match.group("lead"), match.group("trail")


def _token_stream(words: list[dict]) -> list[tuple[int, int, int, str]]:
    """(word index, token position in word, tokens in word, token)."""
    stream = []
    for index, word in enumerate(words):
        tokens = fold_text(word.get("text") or "").split()
        for position, token in enumerate(tokens):
            stream.append((index, position, len(tokens), token))
    return stream


def find_word_runs(words: list[dict], heard: str) -> list[tuple[int, int]]:
    """Runs of whole words whose spoken tokens equal the misheard phrase."""
    query = fold_text(heard).split()
    if not query:
        return []
    stream = _token_stream(words)
    runs = []
    offset = 0
    while offset + len(query) <= len(stream):
        window = stream[offset : offset + len(query)]
        starts_on_word = window[0][1] == 0
        ends_on_word = window[-1][1] == window[-1][2] - 1
        if starts_on_word and ends_on_word and [item[3] for item in window] == query:
            runs.append((window[0][0], window[-1][0]))
            offset += len(query)
        else:
            offset += 1
    return runs


def replace_run(words: list[dict], first: int, last: int, correct: str) -> dict:
    """Rewrite words[first:last+1] as the corrected text. Timing is never moved.

    When the corrected phrase has as many tokens as the run has words, each word
    keeps its own slot. Otherwise the run collapses into one word that spans the
    same start and end, so no boundary is ever invented.
    """
    run = words[first : last + 1]
    original = "".join((word.get("text") or "") for word in run).strip()
    lead, _ = _edges(run[0].get("text") or "")
    _, trail = _edges(run[-1].get("text") or "")
    tokens = correct.split()

    if len(tokens) == len(run):
        for position, (word, token) in enumerate(zip(run, tokens)):
            word_lead, word_trail = _edges(word.get("text") or "")
            if position == 0:
                word_lead = lead
            if position == len(run) - 1:
                word_trail = trail
            word["text"] = f"{word_lead}{token}{word_trail}"
        replaced = len(run)
    else:
        merged = dict(run[0])
        merged["end"] = run[-1].get("end")
        merged["text"] = f"{lead}{correct}{trail}"
        probabilities = [word.get("probability") for word in run if word.get("probability") is not None]
        if probabilities:
            merged["probability"] = min(probabilities)
        words[first : last + 1] = [merged]
        replaced = 1

    return {
        "start": run[0].get("start"),
        "end": run[-1].get("end"),
        "from": original,
        "to": correct,
        "words_after": replaced,
    }


def apply_to_words(words: list[dict], replacements: list[tuple[str, str]]) -> list[dict]:
    changes = []
    for heard, correct in replacements:
        if fold_text(heard) == fold_text(correct):
            continue
        # Work from the end so earlier indexes stay valid when a run collapses.
        for first, last in reversed(find_word_runs(words, heard)):
            changes.append(replace_run(words, first, last, correct))
    return changes


def fix_transcript(transcript: dict, replacements: list[tuple[str, str]]) -> list[dict]:
    """Apply corrections in place and return what changed."""
    changes: list[dict] = []
    segments = transcript.get("segments") or []
    if any(segment.get("words") for segment in segments):
        for segment in segments:
            segment_words = segment.get("words") or []
            segment_changes = apply_to_words(segment_words, replacements)
            if segment_changes:
                original_text = segment.get("text") or ""
                leading = original_text[: len(original_text) - len(original_text.lstrip())]
                segment["text"] = leading + "".join((word.get("text") or "") for word in segment_words).strip()
                changes.extend(segment_changes)
        transcript["words"] = [word for segment in segments for word in segment.get("words") or []]
    else:
        changes.extend(apply_to_words(transcript.get("words") or [], replacements))

    if changes:
        changes.sort(key=lambda item: float(item.get("start") or 0.0))
        transcript.setdefault("corrections", []).extend(changes)
    return changes


def backup_original(path: Path) -> Path:
    """Keep the first, untouched transcript so corrections can always be undone."""
    target = path.parent / "originals" / path.name
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Correct misheard names and terms in cached transcripts without changing any word timing"
    )
    parser.add_argument("sources", nargs="*", help="Transcript stems or media names. Defaults to every transcript.")
    parser.add_argument("--edit-dir", type=Path, required=True)
    parser.add_argument("--replace", dest="replacements", action="append", default=[], metavar="HEARD=>CORRECT")
    parser.add_argument("--glossary", action="store_true", help="Also apply every misheard form saved in the project glossary")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args()

    edit_dir = args.edit_dir.resolve()
    try:
        replacements = [parse_replacement(item) for item in args.replacements]
        if args.glossary:
            replacements.extend(glossary_replacements(load_context(edit_dir)))
        if not replacements:
            raise SystemExit("nothing to apply: pass --replace 'heard => correct' and/or --glossary")
        if args.sources:
            files = [transcript_path_for(edit_dir, source) for source in args.sources]
        else:
            files = sorted(transcripts_dir(edit_dir).glob("*.json"))
        if not files:
            raise SystemExit(f"no transcript JSON files found in {transcripts_dir(edit_dir)}")
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    total = 0
    for path in files:
        transcript = read_json(path)
        changes = fix_transcript(transcript, replacements)
        for change in changes:
            print(f"{path.stem} [{float(change['start'] or 0.0):.2f}] {change['from']!r} -> {change['to']!r}")
        total += len(changes)
        if changes and not args.dry_run:
            backup_original(path)
            write_json(path, transcript)
    verb = "would correct" if args.dry_run else "corrected"
    print(f"{verb} {total} place(s) in {len(files)} transcript(s)")
    if total and not args.dry_run:
        print("rerun `vtc pack-transcripts` so takes_packed.md shows the corrected wording")


if __name__ == "__main__":
    main()
