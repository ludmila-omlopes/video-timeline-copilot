---
name: video-timeline-copilot
description: Generate editable video timelines from local footage using transcript-first AI editing, faster-whisper, structured EDLs, FCPXML, and optional DaVinci Resolve scripting API output.
---

# Video Timeline Copilot

Use this skill when the user wants an AI agent to create an editable video
timeline from local media. Users should be able to ask for outcomes such as
"remove silent parts", "make a 30 second highlight", or "create a rough cut"
without knowing about `edit/edl.json`, SRT, FCPXML, or helper commands.

Do not render a flattened MP4 as the primary deliverable unless the user
explicitly asks for a render.

## Principles

1. The primary artifact is an editable timeline.
2. The LLM writes edit intent as `edl.json`; helper scripts execute it.
3. Transcripts are cached per source and reused.
4. Cuts must land on word boundaries whenever speech is the basis for the edit.
5. Infer sensible defaults from the current folder before asking questions.
6. All session outputs go in the footage folder's `edit/` directory.
7. Always validate the EDL before exporting.
8. Always export SRT and FCPXML after validation.
9. If Resolve external scripting is unavailable, stop after validated EDL, SRT,
   and FCPXML generation and tell the user to import the FCPXML manually.

## User-Facing Request Handling

When the user asks for a video edit from a folder, take ownership of the
internal workflow. Do not ask the user to name `edit/edl.json` or specific helper
commands.

Infer the footage root as follows:

1. If the current working directory contains `raw/`, use the current directory.
2. If the current working directory contains video files directly, use the
   current directory and treat those files as sources.
3. If exactly one obvious child directory contains `raw/`, use that child.
4. If multiple plausible footage roots or multiple source videos exist and the
   user's requested target is ambiguous, ask one concise clarification.

Create `edit/` automatically when needed.

For simple requests, choose conservative defaults:

- "remove silence" / "remove silent parts": keep speech ranges based on word
  timestamp gaps, cut gaps longer than about 0.8 seconds, and add about 0.15
  seconds of padding before and after speech ranges.
- "short edit" without a duration: create a 10-30 second rough cut depending on
  source length.
- "highlight" / "best moments": prioritize clear, self-contained transcript
  phrases and avoid isolated filler words.

If an edit strategy could materially change the user's intended story, briefly
state the strategy before writing the EDL. For straightforward mechanical
requests like removing silence, proceed without asking for confirmation unless
there is ambiguity.

## Standard Session Flow

1. Inventory media:

   ```bash
   vtc inventory /path/to/footage --edit-dir /path/to/footage/edit
   ```

2. Transcribe sources with faster-whisper:

   ```bash
   vtc transcribe /path/to/footage/raw/interview.mp4 --edit-dir /path/to/footage/edit
   ```

3. Pack transcripts:

   ```bash
   vtc pack-transcripts --edit-dir /path/to/footage/edit
   ```

4. Read `edit/takes_packed.md` and any needed transcript JSON files.

5. Write `edit/edl.json` from the user's requested outcome.

6. Validate:

   ```bash
   vtc validate-edl /path/to/footage/edit/edl.json
   ```

7. Generate subtitles:

   ```bash
   vtc export-srt /path/to/footage/edit/edl.json
   ```

8. Export FCPXML fallback:

   ```bash
   vtc export-fcpxml /path/to/footage/edit/edl.json
   ```

9. Build Resolve project when external scripting is available:

   ```bash
   vtc resolve-env-check
   vtc build-resolve-project /path/to/footage/edit/edl.json
   ```

## EDL Contract

The EDL is JSON. It may contain one or more timelines. Each timeline contains
source media, cut ranges, optional transforms, optional subtitles, and optional
markers.

```json
{
  "version": 1,
  "project_name": "Generated_Edit",
  "fps": 30,
  "timelines": [
    {
      "name": "Short 01 - 9x16",
      "resolution": [1080, 1920],
      "sources": {
        "A001": "raw/interview.mp4"
      },
      "ranges": [
        {
          "source": "A001",
          "source_start": 12.42,
          "source_end": 18.9,
          "record_start": 0,
          "track": 1,
          "beat": "HOOK",
          "quote": "This is the hook.",
          "reason": "Cleanest opening.",
          "transform": {
            "zoom": 1.35,
            "pan": 0,
            "tilt": -120
          }
        }
      ],
      "subtitles": {
        "mode": "srt",
        "path": "edit/subtitles/Short_01_9x16.srt"
      },
      "markers": true
    }
  ]
}
```

## Resolve Caveats

DaVinci Resolve's scripting API is strongest at project creation, media import,
timeline creation, timeline item property changes, markers, project export, and
project archive. Subtitle automation varies by Resolve version. Always generate
SRT as a stable handoff artifact even when trying to import subtitle tracks.

DaVinci Resolve Free may not expose external scripting. In that case, stop after
validated EDL, SRT, and FCPXML generation and tell the user to import the FCPXML
manually.
