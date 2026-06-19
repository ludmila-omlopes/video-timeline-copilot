# Audio Analysis

The project uses layered audio analysis instead of treating silence removal as a
final edit.

## Current Default

`vtc draft-silence-cut` uses FFmpeg `silencedetect` to find sustained low-level
audio, then uses transcript word timestamps to split long no-speech gaps when
transcripts are available. It writes an editable EDL containing the kept speech
ranges. This is deterministic, fast, cross-platform, and already aligned with
the project's FFmpeg dependency.

Default behavior:

- detect silence with a configurable threshold such as `-35dB`
- require a configurable minimum silence duration
- keep configurable pre/post-roll padding around detected activity
- merge nearby kept ranges
- drop very short kept ranges
- use transcript word timestamps, when present, to avoid cutting through spoken
  words
- split transcript word gaps longer than the preset or `--max-word-gap`, even
  when room tone or breath noise means FFmpeg does not classify the pause as
  silence

The helper writes `edit/edl.json`. The result should be treated as a draft
timeline for agent or manual refinement, not a finished creative edit.
Validation reports kept transcript gaps longer than the configured
`max_word_gap`, and self-evaluation blocks those long gaps so awkward pauses do
not silently pass QA.

## Styles

The helper exposes pacing presets:

- `social`: tighter cuts and shorter pause tolerance
- `highlight`: moderately tight cuts for short edits
- `documentary`: more natural pauses and breath room
- `longform`: conservative cuts that preserve pacing

Every preset can be overridden with explicit CLI options.

## Why FFmpeg First

Modern neural VAD tools such as Silero VAD and pyannote.audio are useful when
background music, room tone, or noisy recordings make amplitude-based silence
detection unreliable. They also introduce heavier dependencies, model downloads,
and sometimes access-token workflows. For the first deterministic helper,
FFmpeg is the right baseline because it is inspectable and repeatable.

The intended future path is to add optional detectors behind the same EDL
contract:

- FFmpeg `silencedetect` for deterministic amplitude-based silence
- Silero VAD for lightweight neural speech activity detection
- pyannote.audio when diarization or speaker-aware segmentation is needed

Transcript word timings remain the final guardrail for speech-safe cut points
and for removing awkward spoken pauses that are not technically silent.
