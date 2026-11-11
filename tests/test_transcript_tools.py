from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers.dialogue import full_transcript_blocks, segment_lines, transcript_path_for
from helpers.find_phrase import find_in_words, find_phrase
from helpers.fix_transcript import (
    backup_original,
    find_word_runs,
    fix_transcript,
    glossary_replacements,
    parse_replacement,
)
from helpers.preferences import load_preferences, update_preferences
from helpers.transcribe import language_code, pending_videos, transcribe_with_progress


def word(start: float, text: str, length: float = 0.3) -> dict:
    return {"start": start, "end": round(start + length, 3), "text": text, "probability": 0.9}


def sample_transcript() -> dict:
    first = [word(0.0, " We"), word(0.4, " opened"), word(0.8, " Cloud"), word(1.2, " Code,"), word(1.6, " today.")]
    second = [word(5.0, " Then"), word(5.4, " Holonight"), word(5.8, " crashed.")]
    segments = [
        {"start": 0.0, "end": 1.9, "text": " We opened Cloud Code, today.", "words": first},
        {"start": 5.0, "end": 6.1, "text": " Then Holonight crashed.", "words": second},
    ]
    return {"source": "/footage/raw/session.mp4", "duration": 7.0, "segments": segments, "words": [*first, *second]}


def write_transcript(edit_dir: Path, stem: str, transcript: dict) -> Path:
    folder = edit_dir / "transcripts"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stem}.json"
    path.write_text(json.dumps(transcript), encoding="utf-8")
    return path


def test_segment_lines_filter_by_time_and_can_show_timestamps() -> None:
    transcript = sample_transcript()
    assert segment_lines(transcript) == ["We opened Cloud Code, today.", "Then Holonight crashed."]
    assert segment_lines(transcript, start=4.0) == ["Then Holonight crashed."]
    assert segment_lines(transcript, end=2.0, timestamps=True) == ["[00:00:00 0.00-1.90] We opened Cloud Code, today."]


def test_transcript_path_accepts_stem_or_media_name(tmp_path: Path) -> None:
    edit_dir = tmp_path / "edit"
    path = write_transcript(edit_dir, "session", sample_transcript())
    assert transcript_path_for(edit_dir, "session") == path
    assert transcript_path_for(edit_dir, "raw/session.mp4") == path
    with pytest.raises(FileNotFoundError):
        transcript_path_for(edit_dir, "missing")


def test_full_transcript_blocks_name_each_source_and_mark_silence(tmp_path: Path) -> None:
    edit_dir = tmp_path / "edit"
    write_transcript(edit_dir, "session", sample_transcript())
    write_transcript(edit_dir, "broll", {"source": "/footage/raw/broll.mp4", "segments": []})
    assert full_transcript_blocks(edit_dir) == [
        "broll.mp4\n[no dialogue]",
        "session.mp4\nWe opened Cloud Code, today.\nThen Holonight crashed.",
    ]


def test_find_in_words_returns_word_level_times_for_exact_and_close_matches() -> None:
    words = sample_transcript()["words"]

    exact = find_in_words(words, "cloud code")
    assert exact[0]["ratio"] == 1.0
    assert (exact[0]["start"], exact[0]["end"]) == (0.8, 1.5)
    assert exact[0]["before"] == "We opened" and exact[0]["after"] == "today. Then Holonight crashed."

    close = find_in_words(words, "hollow night crashed", min_ratio=0.6)
    assert close and close[0]["ratio"] < 1.0 and close[0]["end"] == 6.1

    assert find_in_words(words, "cloud coat", min_ratio=1.0) == []
    with pytest.raises(ValueError):
        find_in_words(words, "?!")


def test_find_phrase_searches_every_transcript_and_ranks_exact_first(tmp_path: Path) -> None:
    edit_dir = tmp_path / "edit"
    write_transcript(edit_dir, "session", sample_transcript())
    write_transcript(edit_dir, "other", {"words": [word(2.0, " cloud"), word(2.4, " coat")]})

    results = find_phrase(edit_dir, "Cloud Code", min_ratio=0.7)

    assert [item["source"] for item in results] == ["session", "other"]
    assert results[0]["ratio"] == 1.0
    assert find_phrase(edit_dir, "Cloud Code", source="other", min_ratio=1.0) == []


def test_parse_replacement_and_glossary_pairs() -> None:
    assert parse_replacement("Cloud Code => Claude Code") == ("Cloud Code", "Claude Code")
    with pytest.raises(ValueError):
        parse_replacement("Cloud Code")
    context = {"glossary": [{"term": "Hollow Knight", "heard_as": ["Holonight", "hollow knight"]}, {"term": "Hornet"}]}
    assert glossary_replacements(context) == [("Holonight", "Hollow Knight")]


def test_find_word_runs_only_matches_whole_words() -> None:
    words = [word(0.0, " recode"), word(0.4, " the"), word(0.8, " code.")]
    assert find_word_runs(words, "code") == [(2, 2)]
    assert find_word_runs(words, "the code") == [(1, 2)]


def test_fix_transcript_keeps_slots_for_same_length_and_never_moves_timing() -> None:
    transcript = sample_transcript()
    before = [(item["start"], item["end"]) for item in transcript["words"]]

    changes = fix_transcript(transcript, [("cloud code", "Claude Code")])

    assert [(item["start"], item["end"]) for item in transcript["words"]] == before
    assert [item["text"] for item in transcript["words"][2:4]] == [" Claude", " Code,"]
    assert transcript["segments"][0]["text"] == " We opened Claude Code, today."
    assert changes == [{"start": 0.8, "end": 1.5, "from": "Cloud Code,", "to": "Claude Code", "words_after": 2}]
    assert transcript["corrections"] == changes


def test_fix_transcript_collapses_a_run_when_the_word_count_changes() -> None:
    transcript = sample_transcript()

    fix_transcript(transcript, [("Holonight", "Hollow Knight"), ("cloud code", "Claude")])

    texts = [item["text"] for item in transcript["words"]]
    assert texts == [" We", " opened", " Claude,", " today.", " Then", " Hollow Knight", " crashed."]
    merged = transcript["words"][2]
    assert (merged["start"], merged["end"]) == (0.8, 1.5)
    knight = transcript["words"][5]
    assert (knight["start"], knight["end"]) == (5.4, 5.7)
    assert transcript["segments"][1]["text"] == " Then Hollow Knight crashed."
    assert transcript["words"] == [item for segment in transcript["segments"] for item in segment["words"]]


def test_fix_transcript_without_segment_words_edits_the_flat_list_and_skips_noops() -> None:
    transcript = {"words": [word(0.0, " Cloud"), word(0.4, " Code")], "segments": []}
    assert fix_transcript(transcript, [("Claude Code", "claude code")]) == []
    assert "corrections" not in transcript
    assert len(fix_transcript(transcript, [("cloud code", "Claude Code")])) == 1
    assert [item["text"] for item in transcript["words"]] == [" Claude", " Code"]


def test_backup_original_keeps_the_first_version_only(tmp_path: Path) -> None:
    path = write_transcript(tmp_path / "edit", "session", {"words": []})
    backup = backup_original(path)
    path.write_text('{"words": [1]}', encoding="utf-8")
    assert backup_original(path) == backup
    assert json.loads(backup.read_text(encoding="utf-8")) == {"words": []}
    # Originals live in a subfolder so they are never read as a source transcript.
    assert backup.parent.name == "originals"


def test_language_code_ignores_free_text_names() -> None:
    assert language_code("pt") == "pt"
    assert language_code(" EN ") == "en"
    assert language_code("Portuguese") is None
    assert language_code(None) is None


def test_pending_videos_skips_cached_unless_forced(tmp_path: Path) -> None:
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    (transcripts / "a.json").write_text("{}", encoding="utf-8")
    videos = [tmp_path / "a.mp4", tmp_path / "b.mp4"]
    assert pending_videos(videos, transcripts, force=False) == ([videos[1]], [videos[0]])
    assert pending_videos(videos, transcripts, force=True) == (videos, [])


def test_transcribe_passes_glossary_prompt_only_when_given(tmp_path: Path) -> None:
    seen = []

    class FakeModel:
        def transcribe(self, _path, **kwargs):
            seen.append(kwargs)
            info = type("Info", (), {"language": "pt", "language_probability": 0.9, "duration": 0.0})()
            return iter(()), info

    transcribe_with_progress(FakeModel(), tmp_path / "a.mp4", language=None, no_vad=False)
    transcribe_with_progress(FakeModel(), tmp_path / "a.mp4", language="pt", no_vad=False, initial_prompt="Glossary: Hornet.")

    assert "initial_prompt" not in seen[0]
    assert seen[1]["initial_prompt"] == "Glossary: Hornet."
    assert seen[1]["word_timestamps"] is True


def test_preferences_store_editor_and_numbered_notes(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    update_preferences(set_values=["editor=resolve", "language=pt"], add_notes=["Start on the first strong line"], path=path)
    preferences = update_preferences(add_notes=["No greetings"], path=path)

    assert preferences["editor"] == "resolve" and preferences["language"] == "pt"
    assert [note["text"] for note in preferences["notes"]] == ["Start on the first strong line", "No greetings"]

    assert [note["text"] for note in update_preferences(forget_notes=[1], path=path)["notes"]] == ["No greetings"]
    assert load_preferences(path)["notes"][0]["text"] == "No greetings"
    with pytest.raises(ValueError, match="no note number 5"):
        update_preferences(forget_notes=[5], path=path)
    with pytest.raises(ValueError, match="editor must be one of"):
        update_preferences(set_values=["editor=avid"], path=path)
