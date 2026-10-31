from __future__ import annotations

from array import array
import json
from pathlib import Path

import pytest

from helpers.cli import COMMANDS
from helpers.evaluate_edl import evaluate_edl
from helpers.qa_transcript import (
    SAMPLE_RATE,
    default_readout_path,
    default_report_path,
    qa_transcript,
    render_timeline_audio,
    span_record_words,
)


def write_edl(tmp_path: Path, ranges: list[dict]) -> Path:
    raw_dir = tmp_path / "raw"
    edit_dir = tmp_path / "edit"
    raw_dir.mkdir()
    edit_dir.mkdir()
    (raw_dir / "clip.mp4").write_bytes(b"")
    record = 0.0
    for item in ranges:
        item.setdefault("source", "A001")
        item["record_start"] = record
        record += (item["source_end"] - item["source_start"]) / float(item.get("speed", 1.0))
    edl = {
        "version": 1,
        "project_name": "Transcript QA",
        "fps": 30,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": ranges,
            }
        ],
    }
    path = edit_dir / "edl.json"
    path.write_text(json.dumps(edl), encoding="utf-8")
    return path


def silent_decoder(path: Path, start: float, end: float) -> array:
    return array("h", [0]) * int(round((end - start) * SAMPLE_RATE))


def scripted_transcriber(lines: list[tuple[float, str]]):
    """Answer each per-range call with the scripted lines that fall inside it.

    Line times are seconds of the concatenated timeline audio; words last 0.25 s.
    """
    state = {"offset": 0.0}

    def transcribe(samples: array, sample_rate: int) -> list[dict]:
        begin = state["offset"]
        length = len(samples) / sample_rate
        state["offset"] = begin + length
        words = []
        for start, text in lines:
            if not begin <= start < begin + length:
                continue
            for index, token in enumerate(text.split()):
                word_start = start - begin + index * 0.3
                words.append({"start": word_start, "end": word_start + 0.25, "text": token})
        return words

    return transcribe


def test_qa_transcript_command_is_registered() -> None:
    assert COMMANDS["qa-transcript"][0] == "helpers.qa_transcript"


def test_flags_repeated_take_left_across_a_cut(tmp_path: Path) -> None:
    edl_path = write_edl(
        tmp_path,
        [
            {"source_start": 10.0, "source_end": 13.0},
            {"source_start": 20.0, "source_end": 25.0},
        ],
    )
    transcriber = scripted_transcriber(
        [
            (0.2, "lembra que o vermelho"),
            (3.1, "lembra que o vermelho é a única cor que o mundo liga"),
        ]
    )

    report = qa_transcript(edl_path, transcriber=transcriber, decoder=silent_decoder)

    assert report["checks"]["repeats_across_cuts_found"] is True
    finding = report["findings"][0]
    assert finding["kind"] == "repeat_across_cut"
    assert finding["earlier"]["range_index"] == 0
    assert finding["later"]["range_index"] == 1
    assert finding["later"]["record_start"] == pytest.approx(3.1)
    assert default_report_path(edl_path).exists()
    readout = default_readout_path(edl_path).read_text(encoding="utf-8")
    assert "r000 00:00:00.00" in readout
    assert "[repeat_across_cut: repeats range 0" in readout


def test_allow_repeat_suppresses_intentional_repetition(tmp_path: Path) -> None:
    edl_path = write_edl(
        tmp_path,
        [
            {"source_start": 10.0, "source_end": 13.0},
            {"source_start": 20.0, "source_end": 25.0, "allow_repeat": True},
        ],
    )
    transcriber = scripted_transcriber(
        [
            (0.2, "lembra que o vermelho"),
            (3.1, "lembra que o vermelho é a única cor"),
        ]
    )

    report = qa_transcript(edl_path, transcriber=transcriber, decoder=silent_decoder)

    assert report["findings"] == []


def test_repetition_inside_one_range_is_reported_separately(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path, [{"source_start": 0.0, "source_end": 8.0}])
    transcriber = scripted_transcriber(
        [
            (0.2, "fortnite apex overwatch"),
            (2.0, "fortnite apex overwatch muitos outros seguem a mesma lógica"),
        ]
    )

    report = qa_transcript(edl_path, transcriber=transcriber, decoder=silent_decoder)

    assert [item["kind"] for item in report["findings"]] == ["repeat_within_range"]
    assert report["checks"]["repeats_across_cuts_found"] is False


def test_distinct_sentences_produce_no_findings(tmp_path: Path) -> None:
    edl_path = write_edl(
        tmp_path,
        [
            {"source_start": 0.0, "source_end": 3.0},
            {"source_start": 5.0, "source_end": 8.0},
        ],
    )
    transcriber = scripted_transcriber(
        [
            (0.2, "o amarelo ficou associado com alegria"),
            (3.2, "e os jogos usam esse vocabulário compartilhado"),
        ]
    )

    report = qa_transcript(edl_path, transcriber=transcriber, decoder=silent_decoder)

    assert report["findings"] == []
    assert report["timelines"][0]["ranges"][1]["text"].startswith("e os jogos")


def test_retimed_range_maps_words_to_record_time() -> None:
    ranges = [
        {"source": "A001", "source_start": 0.0, "source_end": 2.0, "record_start": 0.0},
        {"source": "A001", "source_start": 10.0, "source_end": 14.0, "record_start": 2.0, "speed": 2.0},
    ]
    audio, spans = render_timeline_audio(ranges, {"A001": Path("clip.mp4")}, decoder=silent_decoder)
    assert len(audio) == 6 * SAMPLE_RATE

    words = span_record_words(spans[1], [{"start": 2.0, "end": 2.5, "text": "palavra"}])

    word = words[0]
    assert word["start"] == pytest.approx(3.0)
    assert word["end"] == pytest.approx(3.25)


def test_evaluate_edl_blocks_on_repeats_across_cuts(tmp_path: Path) -> None:
    edl_path = write_edl(
        tmp_path,
        [
            {"source_start": 10.0, "source_end": 13.0},
            {"source_start": 20.0, "source_end": 25.0},
        ],
    )
    transcriber = scripted_transcriber(
        [
            (0.2, "lembra que o vermelho"),
            (3.1, "lembra que o vermelho é a única cor"),
        ]
    )
    qa_transcript(edl_path, transcriber=transcriber, decoder=silent_decoder)

    report = evaluate_edl(edl_path)

    assert report["status"] == "needs_revision"
    assert any(item.startswith("transcript QA failed: repeat_across_cut") for item in report["blockers"])
    criterion = next(item for item in report["criteria"] if item["name"] == "content_repetition")
    assert criterion["status"] == "fail"


def test_evaluate_edl_flags_stale_transcript_report(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path, [{"source_start": 0.0, "source_end": 3.0}])
    qa_transcript(edl_path, transcriber=scripted_transcriber([(0.2, "olá")]), decoder=silent_decoder)
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["timelines"][0]["ranges"][0]["source_end"] = 2.5
    edl_path.write_text(json.dumps(edl), encoding="utf-8")

    report = evaluate_edl(edl_path)

    assert any("stale" in item for item in report["blockers"])


def test_evaluate_edl_requires_transcript_qa_when_asked(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path, [{"source_start": 0.0, "source_end": 3.0}])

    optional = evaluate_edl(edl_path)
    required = evaluate_edl(edl_path, require_transcript_qa=True)

    assert not any("transcript" in item for item in optional["blockers"])
    assert any("transcript QA report is required" in item for item in required["blockers"])


def test_evaluate_edl_passes_clean_transcript_report(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path, [{"source_start": 0.0, "source_end": 3.0}])
    qa_transcript(
        edl_path,
        transcriber=scripted_transcriber([(0.2, "uma frase só")]),
        decoder=silent_decoder,
    )

    report = evaluate_edl(edl_path, require_transcript_qa=True)

    criterion = next(item for item in report["criteria"] if item["name"] == "content_repetition")
    assert criterion["status"] == "pass"
    assert not any("transcript" in item for item in report["blockers"])


def test_short_phrase_restarted_whole_across_a_cut_is_flagged(tmp_path: Path) -> None:
    edl_path = write_edl(
        tmp_path,
        [
            {"source_start": 0.0, "source_end": 2.0},
            {"source_start": 5.0, "source_end": 9.0},
        ],
    )
    transcriber = scripted_transcriber([(0.2, "e o resto"), (2.2, "e o resto o jogo constrói em cima disso")])

    report = qa_transcript(edl_path, transcriber=transcriber, decoder=silent_decoder)

    assert [item["kind"] for item in report["findings"]] == ["repeat_across_cut"]
    assert report["findings"][0]["shared_words"] == "e o resto"


def test_phrase_said_twice_without_a_pause_is_flagged(tmp_path: Path) -> None:
    edl_path = write_edl(tmp_path, [{"source_start": 0.0, "source_end": 10.0}])
    transcriber = scripted_transcriber(
        [(0.2, "e se você gostou desse vídeo não esqueça de deixar um e se você gostou desse vídeo não esqueça de deixar um gostei")]
    )

    report = qa_transcript(edl_path, transcriber=transcriber, decoder=silent_decoder)

    assert [item["kind"] for item in report["findings"]] == ["repeat_within_range"]
    assert report["findings"][0]["shared_words"].startswith("e se você gostou")
