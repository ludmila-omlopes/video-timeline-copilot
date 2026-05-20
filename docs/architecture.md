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

Validation is deliberately separate from Resolve so offline workflows still get
useful feedback.

### 5. Backend Layer

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

Future backends should read the same EDL:

- `export_fcpxml.py`
- `export_otio.py`
- `export_edl.py`
- `build_premiere_project.py`

## Design Rule

The model should not be the executor. The model produces structured edit intent.
Helpers execute deterministic transformations.

