from __future__ import annotations

import argparse
from array import array
import hashlib
from pathlib import Path
import sys
from typing import Callable

from helpers.audio_refine import decode_audio_window
from helpers.common import ensure_within, read_json, resolve_relative, write_json
from helpers.media_tools import stream_types
from helpers.pack_transcripts import STOPWORD_TOKENS, normalize_text
from helpers.timing import range_timeline_duration
from helpers.validate_edl import validate


SAMPLE_RATE = 16_000
DEFAULT_MODEL = "small"
DEFAULT_PHRASE_GAP = 0.35
DEFAULT_REPEAT_WINDOW = 30.0
DEFAULT_REPEAT_MIN_WORDS = 3
DEFAULT_REPEAT_COVERAGE = 0.5
DEFAULT_REPEAT_LOOKBACK = 3
BLOCKING_KINDS = {"repeat_across_cut"}

# A transcriber receives mono float samples at SAMPLE_RATE and returns words:
# [{"start": float, "end": float, "text": str}, ...] in seconds from sample 0.
Transcriber = Callable[[array, int], list[dict]]


def default_report_path(edl_path: Path) -> Path:
    return edl_path.parent / "qa" / "transcript_report.json"


def default_readout_path(edl_path: Path) -> Path:
    return edl_path.parent / "qa" / "transcript_readout.md"


def edl_digest(edl_path: Path) -> str:
    return hashlib.sha256(edl_path.read_bytes()).hexdigest()


def format_timecode(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes, secs = divmod(seconds, 60.0)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"


def source_language(edit_dir: Path, source_paths: dict[str, Path]) -> str | None:
    for path in source_paths.values():
        transcript = edit_dir / "transcripts" / f"{path.stem}.json"
        if transcript.exists():
            language = read_json(transcript).get("language")
            if language:
                return str(language)
    return None


def render_timeline_audio(
    ranges: list[dict],
    source_paths: dict[str, Path],
    *,
    decoder: Callable[[Path, float, float], array] | None = None,
) -> tuple[array, list[dict]]:
    """Concatenate the audible source audio of each range, in record order.

    Content QA only needs what is said, so retimed ranges are decoded at their
    original speed. Each returned span maps a range to its sample offsets.
    """
    decode = decoder or (lambda path, start, end: decode_audio_window(path, start, end, sample_rate=SAMPLE_RATE))
    audio = array("h")
    spans = []
    has_audio: dict[Path, bool] = {}
    for index, item in enumerate(ranges):
        source = source_paths[item["source"]]
        if source not in has_audio:
            has_audio[source] = decoder is not None or "audio" in stream_types(source)
        begin = len(audio)
        if has_audio[source]:
            audio.extend(decode(source, float(item["source_start"]), float(item["source_end"])))
        spans.append(
            {
                "index": index,
                "source": item["source"],
                "source_start": float(item["source_start"]),
                "source_end": float(item["source_end"]),
                "record_start": float(item.get("record_start", 0.0)),
                "record_duration": range_timeline_duration(item),
                "sample_start": begin,
                "sample_end": len(audio),
                "allow_repeat": bool(item.get("allow_repeat")),
            }
        )
    return audio, spans


def span_record_words(span: dict, words: list[dict]) -> list[dict]:
    """Map words timed from the start of a range's audio to timeline seconds."""
    seconds = (span["sample_end"] - span["sample_start"]) / SAMPLE_RATE
    if seconds <= 0:
        return []
    scale = span["record_duration"] / seconds
    mapped = []
    for word in sorted(words, key=lambda item: float(item["start"])):
        start = min(max(0.0, float(word["start"])), seconds)
        end = min(max(start, float(word["end"])), seconds)
        mapped.append(
            {
                "text": str(word.get("text") or "").strip(),
                "start": span["record_start"] + start * scale,
                "end": span["record_start"] + end * scale,
            }
        )
    return mapped


def transcribe_spans(audio: array, spans: list[dict], transcriber: Transcriber) -> None:
    """Transcribe every range on its own.

    Whisper tends to write a phrase once when it hears it twice in the same
    window, which hides exactly the retakes this check looks for. Isolating each
    range keeps both deliveries in the text.
    """
    for span in spans:
        samples = audio[span["sample_start"] : span["sample_end"]]
        span["words"] = span_record_words(span, transcriber(samples, SAMPLE_RATE)) if len(samples) else []


def range_phrases(spans: list[dict], phrase_gap: float) -> list[dict]:
    """Group words into phrases that never cross a cut."""
    phrases = []
    for span in spans:
        current: list[dict] = []
        for word in span["words"]:
            if current and word["start"] - current[-1]["end"] >= phrase_gap:
                phrases.append(_phrase(current, span))
                current = []
            current.append(word)
        if current:
            phrases.append(_phrase(current, span))
    return phrases


def _phrase(words: list[dict], span: dict) -> dict:
    return {
        "start": words[0]["start"],
        "end": words[-1]["end"],
        "text": " ".join(word["text"] for word in words).strip(),
        "words": list(words),
        "range_index": span["index"],
        "allow_repeat": span["allow_repeat"],
    }


def _tokens(text: str) -> list[str]:
    return normalize_text(text).split()


def _longest_common_run(earlier: list[str], later: list[str]) -> tuple[int, int, int]:
    """Return (length, earlier_index, later_index) of the longest shared token run."""
    best = (0, 0, 0)
    previous_row = [0] * (len(later) + 1)
    for i in range(1, len(earlier) + 1):
        row = [0] * (len(later) + 1)
        for j in range(1, len(later) + 1):
            if earlier[i - 1] == later[j - 1]:
                row[j] = previous_row[j - 1] + 1
                if row[j] > best[0]:
                    best = (row[j], i - row[j], j - row[j])
        previous_row = row
    return best


def _content_count(tokens: list[str]) -> int:
    return sum(1 for token in tokens if len(token) > 2 and token not in STOPWORD_TOKENS)


def find_repetitions(
    phrases: list[dict],
    *,
    repeat_window: float = DEFAULT_REPEAT_WINDOW,
    min_run_words: int = DEFAULT_REPEAT_MIN_WORDS,
    min_coverage: float = DEFAULT_REPEAT_COVERAGE,
    max_lookback: int = DEFAULT_REPEAT_LOOKBACK,
) -> list[dict]:
    """Flag a phrase that restarts a recent phrase: the typical retake left in an edit.

    A later phrase is a likely retake when it starts (within its first words) with
    a token run that covers most of a recent earlier phrase. Parallel rhetorical
    phrases can match too, so findings are review items, not proof.
    """
    findings = []
    for index, phrase in enumerate(phrases):
        if phrase["allow_repeat"]:
            continue
        later = _tokens(phrase["text"])
        if len(later) < min_run_words:
            continue
        candidates = [
            earlier_phrase
            for earlier_phrase in reversed(phrases[max(0, index - max_lookback) : index])
            if phrase["start"] - earlier_phrase["end"] <= repeat_window
        ]
        for earlier_phrase in candidates:
            earlier = _tokens(earlier_phrase["text"])
            if len(earlier) < min_run_words:
                continue
            length, earlier_at, later_at = _longest_common_run(earlier, later)
            run = earlier[earlier_at : earlier_at + length]
            if later_at > 2:
                continue
            whole_restart = length == len(earlier) and length >= 2
            partial_restart = (
                length >= min_run_words and _content_count(run) >= 2 and length / len(earlier) >= min_coverage
            )
            if not (whole_restart or partial_restart):
                continue
            kind = "repeat_across_cut" if earlier_phrase["range_index"] != phrase["range_index"] else "repeat_within_range"
            findings.append(
                {
                    "kind": kind,
                    "shared_words": " ".join(run),
                    "earlier": _phrase_ref(earlier_phrase),
                    "later": _phrase_ref(phrase),
                }
            )
            break
        else:
            doubled = _doubled_run(later, min_run_words)
            if doubled:
                findings.append(
                    {
                        "kind": "repeat_within_range",
                        "shared_words": " ".join(doubled),
                        "earlier": _phrase_ref(phrase),
                        "later": _phrase_ref(phrase),
                    }
                )
    return findings


def _doubled_run(tokens: list[str], min_run_words: int, max_gap: int = 3) -> list[str] | None:
    """Find a run said twice in a row inside one phrase ("deixar um... e se você gostou")."""
    for size in range(min(12, len(tokens) // 2), min_run_words - 1, -1):
        for first in range(0, len(tokens) - 2 * size + 1):
            run = tokens[first : first + size]
            if _content_count(run) < 2:
                continue
            for second in range(first + size, min(len(tokens) - size, first + size + max_gap) + 1):
                if tokens[second : second + size] == run:
                    return run
    return None


def _phrase_ref(phrase: dict) -> dict:
    return {
        "range_index": phrase["range_index"],
        "record_start": round(phrase["start"], 3),
        "record_end": round(phrase["end"], 3),
        "text": phrase["text"],
    }


def readout_lines(timeline_name: str, spans: list[dict], findings: list[dict]) -> list[str]:
    flagged = {}
    for finding in findings:
        flagged.setdefault(finding["later"]["range_index"], []).append(finding)
    lines = [f"## {timeline_name}", ""]
    for span in spans:
        text = " ".join(word["text"] for word in span["words"]).strip() or "(no speech)"
        marker = ""
        for finding in flagged.get(span["index"], []):
            earlier = finding["earlier"]
            marker += f"  [{finding['kind']}: repeats range {earlier['range_index']} \"{earlier['text']}\"]"
        lines.append(
            f"- r{span['index']:03d} {format_timecode(span['record_start'])} "
            f"(src {span['source']} {span['source_start']:.2f}-{span['source_end']:.2f}) {text}{marker}"
        )
    lines.append("")
    return lines


def whisper_transcriber(model_name: str, *, language: str | None, device: str = "auto", compute_type: str = "auto") -> Transcriber:
    try:
        from faster_whisper import WhisperModel
        import numpy as np
    except ImportError as exc:
        raise SystemExit(
            "faster-whisper is not installed. Run: pip install '.[transcribe]' or pip install faster-whisper"
        ) from exc
    from helpers.transcribe import load_whisper_model

    model, _, _ = load_whisper_model(WhisperModel, model_name, device=device, compute_type=compute_type)

    def transcribe(samples: array, sample_rate: int) -> list[dict]:
        if sample_rate != SAMPLE_RATE:
            raise ValueError(f"expected {SAMPLE_RATE} Hz audio")
        # Passing samples instead of a file path avoids PyAV decoding differences.
        audio = np.frombuffer(samples.tobytes(), dtype="<i2").astype(np.float32) / 32768.0
        segments, _ = model.transcribe(
            audio,
            language=language,
            word_timestamps=True,
            vad_filter=False,
            beam_size=1,
            condition_on_previous_text=False,
        )
        return [
            {"start": float(word.start), "end": float(word.end), "text": word.word}
            for segment in segments
            for word in (segment.words or [])
        ]

    return transcribe


def qa_transcript(
    edl_path: Path,
    *,
    transcriber: Transcriber,
    timeline_name: str | None = None,
    out_path: Path | None = None,
    readout_path: Path | None = None,
    phrase_gap: float = DEFAULT_PHRASE_GAP,
    repeat_window: float = DEFAULT_REPEAT_WINDOW,
    min_run_words: int = DEFAULT_REPEAT_MIN_WORDS,
    min_coverage: float = DEFAULT_REPEAT_COVERAGE,
    decoder: Callable[[Path, float, float], array] | None = None,
) -> dict:
    edl_path = edl_path.resolve()
    validation_errors = validate(edl_path)
    if validation_errors:
        raise ValueError("EDL validation failed: " + "; ".join(validation_errors))

    edl = read_json(edl_path)
    root = edl_path.parent.parent
    timelines = edl.get("timelines") or []
    if timeline_name:
        timelines = [item for item in timelines if item.get("name") == timeline_name]
        if not timelines:
            raise ValueError(f"timeline not found: {timeline_name}")

    report_timelines = []
    findings: list[dict] = []
    readout = ["# Transcript readout of the edited timeline", ""]
    for timeline in timelines:
        source_paths = {
            source_id: ensure_within(resolve_relative(source_path, root), root)
            for source_id, source_path in timeline.get("sources", {}).items()
        }
        ranges = sorted(timeline.get("ranges") or [], key=lambda item: float(item.get("record_start", 0.0)))
        audio, spans = render_timeline_audio(ranges, source_paths, decoder=decoder)
        transcribe_spans(audio, spans, transcriber)
        timeline_findings = find_repetitions(
            range_phrases(spans, phrase_gap),
            repeat_window=repeat_window,
            min_run_words=min_run_words,
            min_coverage=min_coverage,
        )
        for finding in timeline_findings:
            finding["timeline"] = timeline.get("name")
        findings.extend(timeline_findings)
        readout.extend(readout_lines(str(timeline.get("name")), spans, timeline_findings))
        report_timelines.append(
            {
                "name": timeline.get("name"),
                "range_count": len(spans),
                "ranges": [
                    {
                        "index": span["index"],
                        "record_start": round(span["record_start"], 3),
                        "source": span["source"],
                        "source_start": span["source_start"],
                        "source_end": span["source_end"],
                        "text": " ".join(word["text"] for word in span["words"]).strip(),
                    }
                    for span in spans
                ],
            }
        )

    readout_file = (readout_path or default_readout_path(edl_path)).resolve()
    readout_file.parent.mkdir(parents=True, exist_ok=True)
    readout_file.write_text("\n".join(readout), encoding="utf-8")

    report = {
        "edl": str(edl_path),
        "edl_sha256": edl_digest(edl_path),
        "readout": str(readout_file),
        "checks": {
            "repeats_across_cuts_found": any(item["kind"] in BLOCKING_KINDS for item in findings),
            "repeats_within_ranges_found": any(item["kind"] not in BLOCKING_KINDS for item in findings),
        },
        "findings": findings,
        "timelines": report_timelines,
    }
    write_json((out_path or default_report_path(edl_path)).resolve(), report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-transcribe the edited timeline audio and flag repeated takes left in the edit"
    )
    parser.add_argument("edl", type=Path)
    parser.add_argument("--timeline", default=None, help="Timeline name; defaults to every timeline")
    parser.add_argument("--out", type=Path, default=None, help="Report path; defaults to edit/qa/transcript_report.json")
    parser.add_argument("--readout", type=Path, default=None, help="Readout path; defaults to edit/qa/transcript_readout.md")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="faster-whisper model (default: small)")
    parser.add_argument("--language", default=None, help="Language code; defaults to the cached source transcript language")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--compute-type", default="auto")
    parser.add_argument("--phrase-gap", type=float, default=DEFAULT_PHRASE_GAP)
    parser.add_argument("--repeat-window", type=float, default=DEFAULT_REPEAT_WINDOW)
    parser.add_argument("--repeat-min-words", type=int, default=DEFAULT_REPEAT_MIN_WORDS, help="Minimum shared words")
    parser.add_argument(
        "--repeat-coverage",
        type=float,
        default=DEFAULT_REPEAT_COVERAGE,
        help="Share of the earlier phrase that must reappear at the start of the later one",
    )
    args = parser.parse_args()

    edl_path = args.edl.resolve()
    language = args.language
    if language is None:
        edl = read_json(edl_path)
        root = edl_path.parent.parent
        sources = {
            key: resolve_relative(value, root)
            for timeline in edl.get("timelines") or []
            for key, value in (timeline.get("sources") or {}).items()
        }
        language = source_language(edl_path.parent, sources)

    transcriber = whisper_transcriber(args.model, language=language, device=args.device, compute_type=args.compute_type)
    try:
        report = qa_transcript(
            edl_path,
            transcriber=transcriber,
            timeline_name=args.timeline,
            out_path=args.out,
            readout_path=args.readout,
            phrase_gap=args.phrase_gap,
            repeat_window=args.repeat_window,
            min_run_words=args.repeat_min_words,
            min_coverage=args.repeat_coverage,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"transcript QA -> {args.out or default_report_path(edl_path)}")
    print(f"readout -> {report['readout']}")
    for finding in report["findings"]:
        print(
            f"{finding['kind'].upper()}: r{finding['later']['range_index']:03d} "
            f"\"{finding['later']['text']}\" repeats r{finding['earlier']['range_index']:03d} "
            f"\"{finding['earlier']['text']}\"",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
