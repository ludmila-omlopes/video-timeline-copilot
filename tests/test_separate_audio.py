from __future__ import annotations

import json
from pathlib import Path
import sys

from helpers.cli import COMMANDS
from helpers.separate_audio import (
    build_demucs_command,
    default_edit_dir,
    expected_stems,
    separate_audio,
)


def test_separate_audio_command_is_registered() -> None:
    assert COMMANDS["separate-audio"] == ("helpers.separate_audio", "Separate source audio into Demucs stems")


def test_default_edit_dir_uses_parent_of_raw_folder() -> None:
    assert default_edit_dir(Path("project/raw/clip.mp4")) == Path("project/edit")
    assert default_edit_dir(Path("project/clip.mp4")) == Path("project/edit")


def test_build_demucs_command_defaults_to_two_stem_vocal_split(tmp_path: Path) -> None:
    audio = tmp_path / "edit" / "audio" / "extracted" / "clip.wav"
    out_root = tmp_path / "edit" / "audio" / "demucs"

    command = build_demucs_command(audio, out_root, device="cpu", jobs=2)

    assert command == [
        sys.executable,
        "-m",
        "demucs.separate",
        "-n",
        "htdemucs",
        "-o",
        str(out_root),
        "--two-stems",
        "vocals",
        "--device",
        "cpu",
        "-j",
        "2",
        str(audio),
    ]


def test_expected_stems_for_four_stem_mode(tmp_path: Path) -> None:
    track_dir = tmp_path / "edit" / "audio" / "demucs" / "htdemucs" / "clip"

    assert expected_stems(track_dir, "4-stem", "flac") == {
        "vocals": str(track_dir / "vocals.flac"),
        "drums": str(track_dir / "drums.flac"),
        "bass": str(track_dir / "bass.flac"),
        "other": str(track_dir / "other.flac"),
    }


def test_separate_audio_writes_manifest_with_stems(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "raw" / "clip.mp4"
    source.parent.mkdir()
    source.write_bytes(b"video")
    edit_dir = tmp_path / "edit"

    def fake_extract(source_path: Path, destination: Path, *, overwrite: bool = False) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"wav")
        return destination

    def fake_run(command: list[str], *, runner) -> None:
        audio = Path(command[-1])
        out_root = Path(command[command.index("-o") + 1])
        track_dir = out_root / "htdemucs" / audio.stem
        track_dir.mkdir(parents=True, exist_ok=True)
        for stem in ("vocals", "no_vocals"):
            (track_dir / f"{stem}.wav").write_bytes(b"stem")

    monkeypatch.setattr("helpers.separate_audio.extract_source_audio", fake_extract)
    monkeypatch.setattr("helpers.separate_audio.run_demucs", fake_run)

    result = separate_audio(source, edit_dir=edit_dir, check_demucs=False)
    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))

    assert Path(result["stems"]["vocals"]).exists()
    assert Path(result["stems"]["no_vocals"]).exists()
    assert manifest["mode"] == "vocals"
    assert manifest["stems"] == result["stems"]
