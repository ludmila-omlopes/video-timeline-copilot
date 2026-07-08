from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


CUDA_RUNTIME_ERROR_MARKERS = (
    "cublas",
    "cudnn",
    "cuda",
    "cudart",
    "nvcuda",
)


def serialize_segments(segments) -> list[dict]:
    output = []
    for segment in segments:
        words = []
        for word in segment.words or []:
            words.append(
                {
                    "start": word.start,
                    "end": word.end,
                    "text": word.word,
                    "probability": word.probability,
                }
            )
        output.append(
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "words": words,
            }
        )
    return output


def print_status(message: str) -> None:
    print(message, flush=True)


def is_cuda_runtime_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in CUDA_RUNTIME_ERROR_MARKERS)


def cpu_fallback_compute_type(compute_type: str) -> str:
    return "int8" if compute_type == "auto" else compute_type


def load_whisper_model(model_cls, model_name: str, *, device: str, compute_type: str):
    try:
        return model_cls(model_name, device=device, compute_type=compute_type), device, compute_type
    except Exception as error:
        if device != "auto" or not is_cuda_runtime_error(error):
            raise

        fallback_compute_type = cpu_fallback_compute_type(compute_type)
        print_status(
            "automatic GPU loading failed for faster-whisper; "
            f"falling back to CPU with compute_type='{fallback_compute_type}'"
        )
        print_status(f"original GPU error: {error}")
        return (
            model_cls(model_name, device="cpu", compute_type=fallback_compute_type),
            "cpu",
            fallback_compute_type,
        )


def progress_line(current: float, total: float) -> str | None:
    if total <= 0:
        return None
    width = 30
    ratio = min(max(current / total, 0.0), 1.0)
    filled = int(width * ratio)
    bar = "#" * filled + "-" * (width - filled)
    percent = ratio * 100
    return f"transcribing [{bar}] {percent:5.1f}% ({current:0.1f}s/{total:0.1f}s)"


def collect_segments_with_progress(segments_iter, duration: float, *, interval_seconds: float = 10.0) -> list:
    segments = []
    last_emit = 0.0
    last_percent = -1

    initial = progress_line(0.0, duration)
    if initial:
        print_status(initial)

    for segment in segments_iter:
        segments.append(segment)
        current = float(segment.end or 0.0)
        percent = int((current / duration) * 100) if duration > 0 else 0
        now = time.monotonic()
        should_emit = now - last_emit >= interval_seconds or percent >= last_percent + 5
        if should_emit:
            line = progress_line(current, duration)
            if line:
                print_status(line)
            last_emit = now
            last_percent = percent

    final = progress_line(duration, duration)
    if final:
        print_status(final)
    return segments


def transcribe_with_progress(model, video: Path, *, language: str | None, no_vad: bool):
    segments_iter, info = model.transcribe(
        str(video),
        language=language,
        word_timestamps=True,
        vad_filter=not no_vad,
        beam_size=5,
    )
    print_status(
        f"detected language={info.language} probability={info.language_probability:0.2f}; "
        f"duration={float(info.duration or 0.0):0.1f}s"
    )
    return collect_segments_with_progress(segments_iter, float(info.duration or 0.0)), info


def transcribe_with_cuda_fallback(
    model_cls,
    model,
    model_name: str,
    video: Path,
    *,
    requested_device: str,
    requested_compute_type: str,
    loaded_device: str,
    language: str | None,
    no_vad: bool,
):
    try:
        return transcribe_with_progress(model, video, language=language, no_vad=no_vad)
    except Exception as error:
        if requested_device != "auto" or loaded_device == "cpu" or not is_cuda_runtime_error(error):
            raise

        fallback_compute_type = cpu_fallback_compute_type(requested_compute_type)
        print_status(
            "automatic GPU transcription failed for faster-whisper; "
            f"retrying on CPU with compute_type='{fallback_compute_type}'"
        )
        print_status(f"original GPU error: {error}")
        cpu_model = model_cls(model_name, device="cpu", compute_type=fallback_compute_type)
        return transcribe_with_progress(cpu_model, video, language=language, no_vad=no_vad)


def flatten_words(segments: list[dict]) -> list[dict]:
    words = []
    for segment in segments:
        words.extend(segment.get("words", []))
    return words


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe one video with faster-whisper")
    parser.add_argument("video", type=Path)
    parser.add_argument("--edit-dir", type=Path, default=None)
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--compute-type", default="auto")
    parser.add_argument("--language", default=None)
    parser.add_argument("--no-vad", action="store_true")
    args = parser.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper is not installed. Run: pip install '.[transcribe]' or pip install faster-whisper")

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    edit_dir = (args.edit_dir or video.parent / "edit").resolve()
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcripts_dir / f"{video.stem}.json"

    if out_path.exists():
        print(f"cached transcript -> {out_path}")
        return

    print_status(f"loading faster-whisper model '{args.model}' on device '{args.device}'")
    model, loaded_device, loaded_compute_type = load_whisper_model(
        WhisperModel,
        args.model,
        device=args.device,
        compute_type=args.compute_type,
    )
    if loaded_device != args.device or loaded_compute_type != args.compute_type:
        print_status(
            f"loaded fallback model on device '{loaded_device}' "
            f"with compute_type '{loaded_compute_type}'"
        )
    print_status(f"model loaded; starting transcription for {video.name}")
    raw_segments, info = transcribe_with_cuda_fallback(
        WhisperModel,
        model,
        args.model,
        video,
        requested_device=args.device,
        requested_compute_type=args.compute_type,
        loaded_device=loaded_device,
        language=args.language,
        no_vad=args.no_vad,
    )
    segments = serialize_segments(raw_segments)
    payload = {
        "source": str(video),
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "segments": segments,
        "words": flatten_words(segments),
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"transcribed {video.name} -> {out_path}")


if __name__ == "__main__":
    main()
