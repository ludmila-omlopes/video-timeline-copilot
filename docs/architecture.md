# Architecture

`video-timeline-copilot` separates creative reasoning from timeline execution.

## Layers

### 1. Media Layer

`helpers/inventory.py` uses `ffprobe` to create `edit/media_index.json`.

This gives the agent concrete file paths, durations, codecs, and dimensions
without asking the model to infer them from filenames.

### 2. Transcript Layer

`helpers/transcribe.py` uses faster-whisper with word timestamps and VAD. Its
output is cached in `edit/transcripts/`.

`helpers/pack_transcripts.py` turns raw transcript JSON into
`edit/takes_packed.md`, which is the primary surface the agent reads when
choosing cuts.

`helpers/draft_silence_cut.py` creates a deterministic rough-cut EDL from audio
activity. It uses FFmpeg `silencedetect` as the baseline detector and uses
cached transcript word timings, when present, to move cut points away from
spoken-word interiors.

### 3. Intent Layer

The agent writes `edit/edl.json`. This is the durable edit contract.

The EDL should be specific enough to reproduce the edit, but generic enough to
target multiple backends later. Today it supports:

- timeline name
- frame rate
- resolution
- source media IDs
- source in/out times
- record start times
- track index
- optional transform metadata
- subtitle output path
- editorial markers

### 4. Validation Layer

`helpers/validate_edl.py` checks the EDL before any editor-specific backend runs.
It also emits cut-quality warnings, such as transcript-backed cuts that appear
to land inside words, without turning those warnings into hard schema errors.

Validation is deliberately separate from Resolve so offline workflows still get
useful feedback.

### 5. Evaluation Layer

`helpers/render_preview.py` can render an MP4 proxy directly from `edl.json`.
`helpers/qa_preview.py` compares that proxy against the EDL and writes technical
QA output such as duration checks, audio-only/video-only regions, record gaps,
and a contact sheet.

`helpers/evaluate_edl.py` is the final handoff gate. It combines EDL validation,
cut-quality warnings, preview QA, and explicit agent-review criteria into
`edit/qa/evaluation_report.json`. The report tells the agent whether to proceed,
revise the EDL and retry, or stop after the configured attempt limit.

### 6. Backend Layer

`helpers/build_resolve_project.py` is the first backend. It translates the EDL
into DaVinci Resolve scripting API calls:

- create project
- set frame rate and resolution
- import media
- create timelines from source ranges
- apply clip transforms
- add markers
- export `.drp`
- archive `.dra`

`helpers/update_resolve_timeline.py` uses the same EDL-to-timeline builder
against an existing Resolve project. It can either create uniquely named updated
timelines or delete and recreate matching timelines when requested. This keeps
iterative agent edits possible while Resolve is open, without treating the
currently selected timeline as mutable source of truth.

Future backends should read the same EDL:

- `export_fcpxml.py`
- `update_fcpxml.py`
- `export_otio.py`
- `export_edl.py`
- `build_premiere_project.py`

## Design Rule

The model should not be the executor. The model produces structured edit intent.
Helpers execute deterministic transformations.
