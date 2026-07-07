# Architecture

`video-timeline-copilot` separates creative reasoning from timeline execution.

## Layers

### 1. Media Layer

`helpers/inventory.py` uses `ffprobe` to create `edit/media_index.json`.

This gives the agent concrete file paths, durations, codecs, and dimensions
without asking the model to infer them from filenames.

### 2. Video Analysis Layer

`helpers/video_analysis.py` uses local FFmpeg filters to create
`edit/video_analysis/<source>.json`, `edit/video_analysis.md`, and sampled JPEG
frames under `edit/video_frames/`.

The default analysis is deliberately model-free: scene-change timestamps,
freeze/near-static ranges, visual activity ranges inferred from those freezes,
and representative frame paths. It does not perform OCR, object detection, face
recognition, or hosted vision analysis. When those signals are needed, the JSON
supports an `observations` array for external/model notes such as visible text,
people, objects, or prompt-specific visual events. This keeps the normal
workflow local and cheap while still giving agents a structured place to combine
visual context with transcript context.

### 3. Transcript Layer

`helpers/transcribe.py` uses faster-whisper with word timestamps and VAD. Its
output is cached in `edit/transcripts/`.

`helpers/pack_transcripts.py` turns raw transcript JSON into
`edit/takes_packed.md`, which is the primary surface the agent reads when
choosing cuts. When matching video-analysis JSON exists, the packed file includes
sampled frames, scene-change signals, static ranges, and observations before the
transcript phrases. When it does not exist, the packed file explicitly tells the
agent it is operating in transcript-only mode.

`helpers/draft_silence_cut.py` creates a deterministic rough-cut EDL from audio
activity. It uses FFmpeg `silencedetect` as the baseline detector and uses
cached transcript word timings, when present, to move cut points away from
spoken-word interiors.

`helpers/audio_refine.py` is a post-pass for speech-safe boundaries. It decodes
small source-audio windows around each EDL cut, detects RMS activity near the
boundary, and expands `source_start`/`source_end` outward when the transcript
timestamp would trim audible phoneme edges.

### 4. Intent Layer

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
- optional constant-speed retime metadata
- subtitle output path
- editorial markers

Transform metadata supports raw `zoom`/`pan`/`tilt`, direct `focus_rect`, and
gameplay presets. `gameplay-facecam` focuses the camera rectangle;
`gameplay-screen` computes a centered zoom into the largest remaining gameplay
region after excluding the facecam rectangle, preventing the screen scene from
showing the facecam overlay again.

### 5. Validation Layer

`helpers/validate_edl.py` checks the EDL before any editor-specific backend runs.
It blocks invalid timeline timing, including record gaps, overlapping clips, and
clips shorter than the minimum duration. It also emits cut-quality warnings,
such as transcript-backed cuts that appear to land inside words or timelines
that keep only part of a transcript-backed sentence/segment, without turning
those warnings into hard schema errors.

Validation is deliberately separate from Resolve so offline workflows still get
useful feedback.

### 6. Evaluation Layer

`helpers/render_preview.py` can render an MP4 proxy directly from `edl.json`.
`helpers/qa_preview.py` compares that proxy against the EDL and writes technical
QA output such as duration checks, audio-only/video-only regions, record gaps,
record overlaps, short clips, and a contact sheet.

`helpers/evaluate_edl.py` is the final handoff gate. It combines EDL validation,
cut-quality warnings, preview QA, and explicit agent-review criteria into
`edit/qa/evaluation_report.json`. Speech-boundary warnings are blockers at this
stage so a technically valid EDL cannot pass with clipped words or partial
phrases. The report tells the agent whether to proceed, revise the EDL and
retry, or stop after the configured attempt limit.

### 7. Backend Layer

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

This scripting backend rejects retimed ranges because it does not yet apply
native Resolve speed changes. Constant-speed retimes are currently handled by
the FCPXML backend using `timeMap` entries that Resolve imports as editable
speed changes.

`helpers/update_resolve_timeline.py` uses the same EDL-to-timeline builder
against an existing Resolve project. It can either create uniquely named updated
timelines or delete and recreate matching timelines when requested. This keeps
iterative agent edits possible while Resolve is open, without treating the
currently selected timeline as mutable source of truth.

Existing backends that read the same EDL: `export_fcpxml.py`,
`update_fcpxml.py`, `import_fcpxml.py`, `build_resolve_project.py`, and
`update_resolve_timeline.py`.

Future backend candidates should read the same EDL:

- `export_otio.py`
- `export_edl.py`
- `build_premiere_project.py`

## Design Rule

The model should not be the executor. The model produces structured edit intent.
Helpers execute deterministic transformations.
