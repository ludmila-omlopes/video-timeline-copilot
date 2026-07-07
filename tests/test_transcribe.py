from __future__ import annotations

from types import SimpleNamespace

import pytest

from helpers.transcribe import (
    is_cuda_runtime_error,
    load_whisper_model,
    transcribe_with_cuda_fallback,
)


def test_detects_missing_cuda_dll_error() -> None:
    assert is_cuda_runtime_error(RuntimeError("Could not locate cublas64_12.dll"))


def test_auto_device_falls_back_to_cpu_int8_for_cuda_runtime_error(capsys) -> None:
    calls = []

    class FakeWhisperModel:
        def __init__(self, model_name: str, *, device: str, compute_type: str) -> None:
            calls.append((model_name, device, compute_type))
            if len(calls) == 1:
                raise RuntimeError("Could not locate cublas64_12.dll")

    model, device, compute_type = load_whisper_model(
        FakeWhisperModel,
        "large-v3",
        device="auto",
        compute_type="auto",
    )

    assert isinstance(model, FakeWhisperModel)
    assert device == "cpu"
    assert compute_type == "int8"
    assert calls == [
        ("large-v3", "auto", "auto"),
        ("large-v3", "cpu", "int8"),
    ]
    assert "falling back to CPU" in capsys.readouterr().out


def test_explicit_cuda_device_does_not_fall_back() -> None:
    calls = []

    class FakeWhisperModel:
        def __init__(self, model_name: str, *, device: str, compute_type: str) -> None:
            calls.append((model_name, device, compute_type))
            raise RuntimeError("Could not locate cublas64_12.dll")

    with pytest.raises(RuntimeError, match="cublas64_12.dll"):
        load_whisper_model(
            FakeWhisperModel,
            "large-v3",
            device="cuda",
            compute_type="auto",
        )

    assert calls == [("large-v3", "cuda", "auto")]


def test_auto_device_retries_on_cpu_when_transcription_iteration_fails(tmp_path) -> None:
    calls = []

    class FakeWhisperModel:
        def __init__(self, model_name: str, *, device: str, compute_type: str) -> None:
            self.device = device
            calls.append((model_name, device, compute_type))

        def transcribe(self, *_args, **_kwargs):
            def segments():
                if self.device == "auto":
                    raise RuntimeError("CUDA failed: cublas64_12.dll is missing")
                yield SimpleNamespace(end=1.0)

            return segments(), SimpleNamespace(
                language="en",
                language_probability=0.99,
                duration=1.0,
            )

    model = FakeWhisperModel("large-v3", device="auto", compute_type="auto")

    segments, info = transcribe_with_cuda_fallback(
        FakeWhisperModel,
        model,
        "large-v3",
        tmp_path / "input.mp4",
        requested_device="auto",
        requested_compute_type="auto",
        loaded_device="auto",
        language=None,
        no_vad=False,
    )

    assert len(segments) == 1
    assert info.language == "en"
    assert calls == [
        ("large-v3", "auto", "auto"),
        ("large-v3", "cpu", "int8"),
    ]
