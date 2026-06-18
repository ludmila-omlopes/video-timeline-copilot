---
name: video-timeline-copilot
description: "Use when editing local video footage with an AI agent: remove silence, create rough cuts or highlight edits, generate subtitles, export FCPXML, or build DaVinci Resolve timelines."
license: MIT
compatibility: "Requires Python 3.10+, uv for helper CLI installation, FFmpeg/ffprobe for media workflows, and optional faster-whisper/DaVinci Resolve Studio."
metadata:
  author: ludmila-omlopes
  version: "0.1.0"
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
9. When the user asks for a technical preview or when visual/technical timeline
   integrity is in doubt, render an MP4 preview and run QA before final handoff.
10. Run final self-evaluation before handoff. If it fails, revise the EDL and
    rerun exports/evaluation up to the configured attempt limit.
11. If Resolve external scripting is unavailable, stop after validated EDL, SRT,
   and FCPXML generation and tell the user to import the FCPXML manually.
12. Repeated delivery, false starts, and self-corrections are not useful
    story beats. When adjacent transcript phrases restate the same idea, keep
    only the cleanest complete version and discard the earlier/incomplete take.

## CLI Invocation

Use the `vtc` command when it is available on `PATH`. The recommended installer
uses `uv tool install` so `vtc` should be installed as an isolated tool.

Before running the workflow for the first time in an environment, check whether
the helper CLI is available:

```bash
vtc --help
```

If `vtc` is missing and the user has not already approved installing the helper
CLI, stop before the video workflow. Explain that the skill instructions are
installed but the Python helper CLI is still required for media inventory,
transcription, EDL validation, subtitle export, FCPXML export, preview
rendering, evaluation, and Resolve handoff. Ask for permission before installing
it:

```bash
uv tool install "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"
```

If `uv` is missing too, ask the user to install `uv` or follow the manual Python
helper setup in `install.md`.

Do not silently replace `vtc` with a hand-written FFmpeg/Python workflow. Only
use a manual fallback if the user explicitly refuses to install `vtc` or `uv`
and still asks you to continue. When using that degraded path, state that normal
validation, preview QA, evaluation, and exports may be incomplete compared with
the helper CLI workflow.

If the user approves using `uv` without installing the tool permanently, you may
run individual helper commands through uv:

```bash
uv tool run --from "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main" vtc
```

Treat `uv tool run` as an approved helper-CLI path, not as permission to bypass
the helper workflow.

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
  seconds of padding before and after speech ranges. Prefer
  `vtc draft-silence-cut` for the first deterministic pass when the user wants
  mechanical silence removal, then refine the generated EDL if needed. Also
  collapse repeated takes: if the speaker restarts the same sentence or repeats
  the same point nearby, include only one version.
- "short edit" without a duration: create a 10-30 second rough cut depending on
  source length.
- "highlight" / "best moments": prioritize clear, self-contained transcript
  phrases and avoid isolated filler words, false starts, and duplicate
  deliveries.

Treat `takes_packed.md` notes such as `possible repeated take` as warnings that
the marked phrase probably duplicates an earlier attempt. Do not place both
versions on the timeline unless the user's request explicitly asks to show the
repetition. Prefer the more complete, fluent, and contextually useful delivery;
often that is the later take after the speaker restarted.

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

5. Write `edit/edl.json` from the user's requested outcome. For draft silence
   removal, use the deterministic helper:

   ```bash
   vtc draft-silence-cut /path/to/footage/raw/interview.mp4 --edit-dir /path/to/footage/edit --style documentary
   ```

   Then inspect/refine the generated EDL when the request requires more than
   mechanical silence removal.

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

   If an FCPXML already exists and the user wants to keep updating the same XML
   file path, use:

   ```bash
   vtc update-fcpxml /path/to/footage/edit/edl.json
   ```

   Use `--xml /path/to/file.fcpxml` when the existing XML is not the default
   project-name path. This rewrites the XML file on disk; it does not live-sync
   an already-imported Resolve timeline.

9. Optionally render a technical preview and QA report:

   ```bash
   vtc render-preview /path/to/footage/edit/edl.json
   vtc qa-preview /path/to/footage/edit/edl.json
   ```

   Default outputs are:

   ```text
   edit/previews/<project>_preview.mp4
   edit/qa/preview_report.json
   edit/qa/contact_sheet.jpg
   ```

   Read `preview_report.json` before handoff when using this path. Treat
   duration mismatches, audio-only/video-only regions, and unexpected record
   gaps as issues to inspect and correct when they conflict with the intended
   edit.

10. Run self-evaluation before final handoff:

   ```bash
   vtc evaluate-edl /path/to/footage/edit/edl.json --require-preview --attempt 1 --max-attempts 3
   ```

   Default output:

   ```text
   edit/qa/evaluation_report.json
   ```

   If the report status is `needs_revision`, revise `edit/edl.json`, rerun
   validation, SRT/FCPXML export, preview rendering, QA, and evaluation with the
   next `--attempt` value. Stop after `--max-attempts`; if the status is still
   `blocked`, tell the user what failed instead of continuing to iterate.

11. Build Resolve project when external scripting is available:

   ```bash
   vtc resolve-env-check
   vtc build-resolve-project /path/to/footage/edit/edl.json
   ```

   If the user already has the Resolve project open and wants to keep working
   in that project, update the existing project instead:

   ```bash
   vtc update-resolve-timeline /path/to/footage/edit/edl.json --project "Existing Project"
   ```

   By default, this creates uniquely named replacement timelines and leaves old
   timelines intact. Use `--replace-existing` only when the user explicitly
   wants matching timeline names deleted and recreated.

## Self-Evaluation Loop

Use `vtc evaluate-edl` as the final gate before handoff. It checks:

- export validity through `vtc validate-edl` rules
- cut-craft warnings such as cuts inside spoken words
- preview QA when `edit/qa/preview_report.json` exists
- duration, audio-only, and video-only preview failures
- agent-review criteria for prompt alignment, pacing, and visual coherence

The helper writes a JSON report with `status`, `blockers`, `warnings`,
`revision_guidance`, and remaining attempts. Treat `status: pass` as permission
to proceed only after doing the listed agent review. Treat
`status: needs_revision` as instructions to revise the EDL and rerun the
workflow. Treat `status: blocked` as a hard stop: report the blockers and the
attempt count to the user.

Guardrails:

- Default maximum: 3 evaluation attempts.
- Do not render more than once per attempt unless a render command fails or the
  EDL changed.
- Do not use external paid or network video-analysis services unless the user
  explicitly asks for that path.
- Keep every report under `edit/qa/` so the user can inspect what was checked.

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

## Cut Craft Rules

By default, place cuts on complete word, phrase, sentence, beat, pause, or clear
visual transition boundaries. Avoid cutting through words, syllables, breaths,
and incomplete phrases unless the user explicitly asks for a deliberately
aggressive or stylized edit. Prefer the cleanest complete delivery when nearby
phrases repeat the same idea.

For tight social edits, remove more dead air but preserve word starts/ends and
avoid creating tiny record gaps. For documentary and long-form edits, preserve
more natural pauses and avoid rapid jump cuts unless the visual continuity is
acceptable. For highlights, favor self-contained phrases and avoid isolated
filler words.

Always run `vtc validate-edl` before export. When transcript timings exist, the
validator warns if a source cut appears to land inside a spoken word.

## Resolve Caveats

DaVinci Resolve's scripting API is strongest at project creation, media import,
timeline creation, timeline item property changes, markers, project export, and
project archive. Subtitle automation varies by Resolve version. Always generate
SRT as a stable handoff artifact even when trying to import subtitle tracks.

`vtc update-resolve-timeline` works against an existing Resolve project. It
rebuilds EDL timelines in that project; it does not live-edit individual clips
inside the currently selected timeline. If `--replace-existing` is used and
Resolve refuses to delete an active timeline, create a uniquely named timeline
first or switch to another timeline before retrying.

DaVinci Resolve Free may not expose external scripting. In that case, stop after
validated EDL, SRT, and FCPXML generation and tell the user to import the FCPXML
manually.
