from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

from helpers.common import safe_filename, write_json
from helpers.media_tools import find_ffmpeg


DEFAULT_MODEL = "htdemucs"
DEFAULT_MODE = "vocals"
STEMS_BY_MODE = {
    "vocals": ["vocals", "no_vocals"],
    "4-stem": ["vocals", "drums", "bass", "other"],
}

Runner = Callable[..., subprocess.CompletedProcess[Any]]


def default_edit_dir(source: Path) -> Path:
    return source.parent.parent / "edit" if source.parent.name == "raw" else source.parent / "edit"


def demucs_available() -> bool:
    if importlib.util.find_spec("demucs") is None:
        return False
    return importlib.util.find_spec("demucs.separate") is not None


def require_demucs() -> None:
    if demucs_available():
        return
    raise RuntimeError(
        "demucs is not installed. Install this helper with the Demucs extra, for example: "
        'uv tool install "video-timeline-copilot[transcribe,demucs] @ '
        'git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"'
    )


def extracted_audio_path(source: Path, edit_dir: Path) -> Path:
    return edit_dir / "audio" / "extracted" / f"{safe_filename(source.stem, 'source')}.wav"


def extract_source_audio(source: Path, destination: Path, *, overwrite: bool = False) -> Path:
    if destination.exists() and not overwrite:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        find_ffmpeg(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "2",
        "-ar",
        "44100",
        "-c:a",
        "pcm_s16le",
        str(destination),
    ]
    subprocess.run(cmd, check=True)
    return destination


def demucs_output_extension(output_format: str) -> str:
    return "wav" if output_format == "wav" else output_format


def build_demucs_command(
    audio: Path,
    out_root: Path,
    *,
    model: str = DEFAULT_MODEL,
    mode: str = DEFAULT_MODE,
    device: str | None = None,
    jobs: int | None = None,
    output_format: str = "wav",
) -> list[str]:
    cmd = [sys.executable, "-m", "demucs.separate", "-n", model, "-o", str(out_root)]
    if mode == "vocals":
        cmd.extend(["--two-stems", "vocals"])
    elif mode != "4-stem":
        raise ValueError(f"unsupported separation mode: {mode}")

    if device:
        cmd.extend(["--device", device])
    if jobs is not None:
        cmd.extend(["-j", str(jobs)])
    if output_format == "mp3":
        cmd.append("--mp3")
    elif output_format == "flac":
        cmd.append("--flac")
    elif output_format != "wav":
        raise ValueError(f"unsupported output format: {output_format}")

    cmd.append(str(audio))
    return cmd


def demucs_track_dir(out_root: Path, model: str, audio: Path) -> Path:
    return out_root / model / audio.stem


def expected_stems(track_dir: Path, mode: str, output_format: str) -> dict[str, str]:
    extension = demucs_output_extension(output_format)
    return {stem: str(track_dir / f"{stem}.{extension}") for stem in STEMS_BY_MODE[mode]}


def write_manifest(
    track_dir: Path,
    *,
    source: Path,
    extracted_audio: Path,
    model: str,
    mode: str,
    output_format: str,
    stems: dict[str, str],
    command: list[str],
) -> Path:
    manifest = {
        "source": str(source),
        "extracted_audio": str(extracted_audio),
        "model": model,
        "mode": mode,
        "format": output_format,
        "stems": stems,
        "command": command,
    }
    path = track_dir / "vtc_stems.json"
    write_json(path, manifest)
    return path


def run_demucs(command: list[str], *, runner: Runner = subprocess.run) -> None:
    runner(command, check=True)


def separate_audio(
    source: Path,
    *,
    edit_dir: Path | None = None,
    out_root: Path | None = None,
    model: str = DEFAULT_MODEL,
    mode: str = DEFAULT_MODE,
    device: str | None = None,
    jobs: int | None = None,
    output_format: str = "wav",
    overwrite: bool = False,
    check_demucs: bool = True,
    runner: Runner = subprocess.run,
) -> dict:
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(f"source not found: {source}")
    if mode not in STEMS_BY_MODE:
        raise ValueError(f"unsupported separation mode: {mode}")
    if check_demucs:
        require_demucs()

    resolved_edit_dir = (edit_dir or default_edit_dir(source)).resolve()
    audio = extract_source_audio(source, extracted_audio_path(source, resolved_edit_dir), overwrite=overwrite)
    resolved_out_root = (out_root or resolved_edit_dir / "audio" / "demucs").resolve()
    resolved_out_root.mkdir(parents=True, exist_ok=True)

    command = build_demucs_command(
        audio,
        resolved_out_root,
        model=model,
        mode=mode,
        device=device,
        jobs=jobs,
        output_format=output_format,
    )
    run_demucs(command, runner=runner)

    track_dir = demucs_track_dir(resolved_out_root, model, audio)
    stems = expected_stems(track_dir, mode, output_format)
    missing = [path for path in stems.values() if not Path(path).exists()]
    if missing:
        raise FileNotFoundError("Demucs did not create expected stem file(s): " + ", ".join(missing))

    manifest_path = write_manifest(
        track_dir,
        source=source,
        extracted_audio=audio,
        model=model,
        mode=mode,
        output_format=output_format,
        stems=stems,
        command=command,
    )
    return {
        "source": str(source),
        "extracted_audio": str(audio),
        "output_dir": str(track_dir),
        "manifest": str(manifest_path),
        "stems": stems,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Separate source audio into Demucs stems")
    parser.add_argument("source", type=Path, help="Source video or audio file")
    parser.add_argument("--edit-dir", type=Path, default=None, help="Output edit directory")
    parser.add_argument("--out-root", type=Path, default=None, help="Demucs output root; defaults to edit/audio/demucs")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Demucs model name")
    parser.add_argument("--mode", choices=sorted(STEMS_BY_MODE), default=DEFAULT_MODE)
    parser.add_argument("--device", default=None, help="Demucs device, e.g. cuda or cpu")
    parser.add_argument("--jobs", type=int, default=None, help="Parallel jobs passed to Demucs")
    parser.add_argument("--format", choices=["wav", "mp3", "flac"], default="wav", help="Stem output format")
    parser.add_argument("--overwrite", action="store_true", help="Re-extract cached source audio before separation")
    args = parser.parse_args()

    try:
        result = separate_audio(
            args.source,
            edit_dir=args.edit_dir,
            out_root=args.out_root,
            model=args.model,
            mode=args.mode,
            device=args.device,
            jobs=args.jobs,
            output_format=args.format,
            overwrite=args.overwrite,
        )
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(f"stems -> {result['output_dir']}")
    print(f"manifest -> {result['manifest']}")


if __name__ == "__main__":
    main()
