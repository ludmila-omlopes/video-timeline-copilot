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


def transcribe_with_progress(
    model,
    video: Path,
    *,
    language: str | None,
    no_vad: bool,
    initial_prompt: str | None = None,
):
    options = {}
    if initial_prompt:
        # Names and terms from the project glossary; biases recognition, never timing.
        options["initial_prompt"] = initial_prompt
    segments_iter, info = model.transcribe(
        str(video),
        language=language,
        word_timestamps=True,
        vad_filter=not no_vad,
        beam_size=5,
        **options,
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
    initial_prompt: str | None = None,
):
    try:
        return transcribe_with_progress(model, video, language=language, no_vad=no_vad, initial_prompt=initial_prompt)
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
        return transcribe_with_progress(
            cpu_model, video, language=language, no_vad=no_vad, initial_prompt=initial_prompt
        )


def flatten_words(segments: list[dict]) -> list[dict]:
    words = []
    for segment in segments:
        words.extend(segment.get("words", []))
    return words


def language_code(value: str | None) -> str | None:
    """Whisper wants a short code such as 'pt' or 'en'; ignore free-text language names."""
    if not value:
        return None
    text = value.strip().lower()
    return text if text.isalpha() and 2 <= len(text) <= 3 else None


def pending_videos(videos: list[Path], transcripts_dir: Path, *, force: bool) -> tuple[list[Path], list[Path]]:
    todo, cached = [], []
    for video in videos:
        (cached if (transcripts_dir / f"{video.stem}.json").exists() and not force else todo).append(video)
    return todo, cached


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe videos with faster-whisper (the model is loaded once)")
    parser.add_argument("videos", nargs="*", type=Path, help="Source video(s). With --all, every indexed source.")
    parser.add_argument("--edit-dir", type=Path, default=None)
    parser.add_argument("--all", action="store_true", help="Transcribe every source in edit/media_index.json that has no transcript yet")
    parser.add_argument("--force", action="store_true", help="Redo sources that already have a transcript")
    parser.add_argument("--model", default=None, help="Whisper model; defaults to the saved whisper_model preference, then large-v3")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--compute-type", default="auto")
    parser.add_argument("--language", default=None, help="Language code such as pt or en; defaults to the project or saved language")
    parser.add_argument("--no-vad", action="store_true")
    parser.add_argument("--initial-prompt", default=None, help="Text that biases recognition; defaults to the project glossary")
    parser.add_argument("--no-glossary", action="store_true", help="Do not prime recognition with the project glossary")
    args = parser.parse_args()

    if not args.videos and not args.all:
        sys.exit("give one or more videos, or use --all with --edit-dir")
    if args.all and args.edit_dir is None:
        sys.exit("--all needs --edit-dir")

    from helpers.preferences import load_preferences
    from helpers.project_context import glossary_prompt, load_context

    videos = [path.resolve() for path in args.videos]
    for video in videos:
        if not video.exists():
            sys.exit(f"video not found: {video}")
    edit_dir = (args.edit_dir or videos[0].parent / "edit").resolve()
    if args.all:
        from helpers.contact_sheet import source_videos_from_media_index

        try:
            indexed = [path.resolve() for path in source_videos_from_media_index(edit_dir)]
        except FileNotFoundError as exc:
            sys.exit(f"{exc}; run `vtc inventory` first")
        videos.extend(path for path in indexed if path not in videos)
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    todo, cached = pending_videos(videos, transcripts_dir, force=args.force)
    for video in cached:
        print(f"cached transcript -> {transcripts_dir / f'{video.stem}.json'}")
    if not todo:
        return

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper is not installed. Run: pip install '.[transcribe]' or pip install faster-whisper")

    preferences = load_preferences()
    context = load_context(edit_dir)
    model_name = args.model or preferences.get("whisper_model") or "large-v3"
    language = args.language or language_code(context.get("language")) or language_code(preferences.get("language"))
    initial_prompt = args.initial_prompt or (None if args.no_glossary else glossary_prompt(context))
    if initial_prompt:
        print_status(f"priming recognition with: {initial_prompt}")

    print_status(f"loading faster-whisper model '{model_name}' on device '{args.device}'")
    model, loaded_device, loaded_compute_type = load_whisper_model(
        WhisperModel,
        model_name,
        device=args.device,
        compute_type=args.compute_type,
    )
    if loaded_device != args.device or loaded_compute_type != args.compute_type:
        print_status(
            f"loaded fallback model on device '{loaded_device}' "
            f"with compute_type '{loaded_compute_type}'"
        )

    failures = []
    for position, video in enumerate(todo, start=1):
        out_path = transcripts_dir / f"{video.stem}.json"
        print_status(f"transcript: {position}/{len(todo)} starting {video.name}")
        try:
            raw_segments, info = transcribe_with_cuda_fallback(
                WhisperModel,
                model,
                model_name,
                video,
                requested_device=args.device,
                requested_compute_type=args.compute_type,
                loaded_device=loaded_device,
                language=language,
                no_vad=args.no_vad,
                initial_prompt=initial_prompt,
            )
        except Exception as error:
            if len(todo) == 1:
                raise
            failures.append(video)
            print_status(f"error: could not transcribe {video.name}: {error}")
            continue
        segments = serialize_segments(raw_segments)
        payload = {
            "source": str(video),
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "model": model_name,
            "segments": segments,
            "words": flatten_words(segments),
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"transcribed {video.name} -> {out_path}")

    if failures:
        sys.exit(f"{len(failures)} source(s) failed: " + ", ".join(video.name for video in failures))


if __name__ == "__main__":
    main()
