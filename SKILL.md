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
4. Visual context should be gathered before creative clip selection when the
   request depends on visible events, on-screen text, action, objects, people,
   framing, or scene changes. If video analysis is unavailable, continue with
   the transcript-only fallback and say so.
5. Cuts must land on audio-safe word boundaries whenever speech is the basis
   for the edit. Use transcript timings for intent, then audio activity around
   each boundary to avoid trimming the first or last phoneme.
6. Infer sensible defaults from the current folder before asking questions.
7. All session outputs go in the footage folder's `edit/` directory.
8. Always validate the EDL before exporting.
9. Always export SRT and FCPXML after validation.
10. When the user asks for a technical preview or when visual/technical timeline
   integrity is in doubt, render an MP4 preview and run QA before final handoff.
11. Run final self-evaluation before handoff. If it fails, revise the EDL and
    rerun exports/evaluation up to the configured attempt limit. For
    transcript-backed speech edits, use strict cut warnings so incomplete
    words, phrases, or sentence fragments block handoff.
12. If Resolve external scripting is unavailable, stop after validated EDL, SRT,
    and FCPXML generation and tell the user to import the FCPXML manually.
13. Repeated delivery, false starts, and self-corrections are not useful
    story beats. When adjacent transcript phrases restate the same idea, keep
    only the cleanest complete version and discard the earlier/incomplete take.

## CLI Invocation

Use the `vtc` command when it is available on `PATH`. The recommended installer
uses `uv tool install` so `vtc` should be installed as an isolated tool.

Before running the workflow for the first time in an environment, bootstrap the
helper CLI. Do not ask the user how to install `uv` or `vtc`; the commands are
listed here. Ask for approval to run installation commands when required by the
agent environment, then run the appropriate steps.

First check whether the helper CLI is available:

```bash
vtc --help
```

If `vtc` is missing and the user has not already approved installing the helper
CLI, stop before the video workflow. Explain that the skill instructions are
installed but the Python helper CLI is still required for media inventory,
transcription, EDL validation, subtitle export, FCPXML export, preview
rendering, evaluation, and Resolve handoff. Ask for permission before installing
it:

Windows PowerShell:

```powershell
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  winget install --id astral-sh.uv -e
}

$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = "$machinePath;$userPath"

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
  $uv = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter uv.exe -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty FullName
}
if (-not $uv) {
  throw "uv is installed or requested, but uv.exe was not found. Reopen PowerShell or install uv from https://docs.astral.sh/uv/"
}

& $uv tool install --force "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"

$toolDir = "$env:USERPROFILE\.local\bin"
if (Test-Path $toolDir) {
  $env:Path = "$toolDir;$env:Path"
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  if ($userPath -notlike "*$toolDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$toolDir", "User")
  }
}

vtc --help
```

macOS/Linux:

```bash
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv tool install "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"
export PATH="$HOME/.local/bin:$PATH"
vtc --help
```

After installation, always verify `vtc --help` works in the current shell before
continuing. If installation succeeded but `vtc` is still missing, refresh PATH
from user/machine environment variables and add the uv tool directory for the
current session. On Windows that is usually `%USERPROFILE%\.local\bin`.

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
  mechanical silence removal; it removes transcript word gaps even when the
  audio is not technically silent. Then run `vtc refine-audio-cuts --replace`
  so cut boundaries are expanded by source audio activity, not only transcript
  word timestamps.
  Also collapse repeated takes: if the speaker restarts the same sentence or
  repeats the same point nearby, include only one version. Do not leave record
  gaps or half-second fragments; keep clips at least 0.8 seconds unless a
  longer configured minimum applies.
- "short edit" without a duration: create a 10-30 second rough cut depending on
  source length.
- "Shorts", "YouTube Short", or vertical short-form edit: default to a 9:16
  timeline, usually `resolution: [1080, 1920]`, unless the user explicitly asks
  for another format. Pick one self-contained idea, start on the strongest hook,
  keep pacing tight without clipping words, and avoid intros/outros that do not
  serve the short.
- "highlight" / "best moments": prioritize clear, self-contained transcript
  phrases and avoid isolated filler words, false starts, and duplicate
  deliveries.
- "Shorts" from gameplay with a facecam overlay: treat facecam handling as
  part of the vertical Shorts framing. Use `preset: gameplay-facecam` for
  reaction/commentary beats and `preset: gameplay-screen` for gameplay beats,
  with the same known facecam rectangle, so the screen-focused scene excludes
  the facecam instead of showing it again.

Treat `takes_packed.md` notes such as `possible repeated take` and
`possible self-correction/restart` as warnings that the marked phrase probably
duplicates or corrects an earlier attempt. Do not place both versions on the
timeline unless the user's request explicitly asks to show the repetition.
Prefer the more complete, fluent, and contextually useful delivery; often that
is the later take after the speaker restarted. If the restart detector is too
strict or too loose for a transcript, rerun `vtc pack-transcripts` with
`--restart-overlap-words` or `--restart-max-gap`.

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

3. Analyze visual context when the edit depends on visible events, scene
   changes, action, on-screen text, objects, people, or framing:

   ```bash
   vtc analyze-video /path/to/footage/raw/interview.mp4 --edit-dir /path/to/footage/edit
   ```

   This creates `edit/video_analysis/<source>.json`, `edit/video_analysis.md`,
   and sampled frames under `edit/video_frames/`. The default helper uses local
   FFmpeg scene/freeze detection and sampled frames only. It does not run OCR,
   object detection, face recognition, or a hosted vision model, so there is no
   extra model cost. If deeper visual understanding is required, inspect the
   sampled frames or add external/model observations to the JSON `observations`
   array, then repack transcripts.

4. Pack transcripts and cached visual context:

   ```bash
   vtc pack-transcripts --edit-dir /path/to/footage/edit
   ```

5. Read `edit/takes_packed.md`, any needed transcript JSON files, and sampled
   frames referenced by the visual context. If `takes_packed.md` says no cached
   video analysis exists, treat visual matching as limited and continue
   transcript-only unless the user's prompt requires visible-event matching.

6. Write `edit/edl.json` from the user's requested outcome. Combine transcript
   timing with visual-analysis signals when selecting clips. For draft silence
   removal, use the deterministic helper:

   ```bash
   vtc draft-silence-cut /path/to/footage/raw/interview.mp4 --edit-dir /path/to/footage/edit --style documentary
   ```

   Then inspect/refine the generated EDL when the request requires more than
   mechanical silence removal.

7. Refine speech cut boundaries from the source audio:

   ```bash
   vtc refine-audio-cuts /path/to/footage/edit/edl.json --replace
   ```

   This expands cut starts/ends outward only when RMS activity is found close
   to the boundary. It is meant to catch transcript timestamps that end a word
   slightly before the audible phoneme finishes.

   If the user needs to rebalance baked-in voice and background music, split the
   source audio into Demucs stems:

   ```bash
   vtc separate-audio /path/to/footage/raw/interview.mp4 --edit-dir /path/to/footage/edit
   ```

   The default output is a two-stem vocal split under
   `edit/audio/demucs/htdemucs/<source>/` with `vocals.wav`, `no_vocals.wav`,
   and `vtc_stems.json`. Use `--mode 4-stem` for vocals, drums, bass, and
   other.

8. Validate:

   ```bash
   vtc validate-edl /path/to/footage/edit/edl.json
   ```

9. Generate subtitles:

   ```bash
   vtc export-srt /path/to/footage/edit/edl.json
   ```

10. Export FCPXML fallback:

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

   If the user manually edited a timeline in an FCPXML-compatible NLE and
   exported a fresh XML, sync those cuts back to a new EDL before continuing
   agent-led editing:

   ```bash
   vtc import-fcpxml /path/to/footage/edit/Adjusted.fcpxml --base-edl /path/to/footage/edit/edl.json
   ```

   The default output is `edit/edl.imported.json` with a reconciliation report
   at `edit/qa/fcpxml_import_report.json`. Use `--replace` only when the user
   explicitly wants to replace the base EDL; the helper validates a temporary
   import and writes an `edl.bak.json` backup before replacing.

11. Optionally render a technical preview and QA report:

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
   duration mismatches, transform coverage failures, audio-only/video-only
   regions, record gaps, record overlaps, and short clips as issues to correct.
   When FCPXML geometry itself is under inspection, render the exported XML
   separately instead of relying only on the EDL preview:

   ```bash
   vtc render-fcpxml-preview /path/to/footage/edit/timeline.fcpxml --resolve-crop-x-factor 2
   ```

   Use this to compare the actual exported XML layout against the EDL preview
   when debugging Resolve crop/transform import behavior.

12. Run self-evaluation before final handoff:

   ```bash
   vtc evaluate-edl /path/to/footage/edit/edl.json --require-preview --strict-cut-warnings --attempt 1 --max-attempts 3
   ```

   Default output:

   ```text
   edit/qa/evaluation_report.json
   ```

   If the report status is `needs_revision`, revise `edit/edl.json`, rerun
   validation, SRT/FCPXML export, preview rendering, QA, and evaluation with the
   next `--attempt` value. Stop after `--max-attempts`; if the status is still
   `blocked`, tell the user what failed instead of continuing to iterate.

13. Build Resolve project when external scripting is available:

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
- cut-craft warnings such as cuts inside spoken words or partial
  transcript-backed sentences/segments
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

## Shorts-Specific Guidelines

Use these rules whenever the user asks for Shorts, YouTube Shorts, vertical
short-form, or a social cut intended to stand alone:

- Format: default to a 9:16 vertical timeline, normally `resolution:
  [1080, 1920]`. Do not change an explicitly requested format.
- Duration: respect the user's requested duration. If none is given, choose a
  compact cut around one complete idea instead of stretching to fill time.
- Hook: open on the strongest sentence, reveal, contradiction, question, or
  visual action. Cut preamble before the hook unless it is necessary context.
- Structure: keep one main setup/payoff. Avoid stitching unrelated highlights
  into one short unless the user asked for a montage.
- Speech: remove dead air, false starts, duplicate retakes, and filler, but
  preserve complete words and self-contained phrases. Run
  `vtc refine-audio-cuts --replace` before validation/export.
- Framing: for horizontal footage, choose an intentional vertical crop per
  range. Keep faces, hands, important UI, and subtitles inside the vertical
  frame.
- Gameplay facecam: when a Short is cut from gameplay with a facecam overlay,
  create distinct vertical scene types. Use `gameplay-facecam` for the
  facecam/reaction shot. Use `gameplay-screen` for gameplay/screen shots so
  the helper crops to the largest remaining gameplay region and does not show
  the facecam again. Do not use a generic center crop if it repeats the facecam
  in the screen-focused scene.
- Captions: always export SRT. Prefer short caption chunks that track spoken
  phrases; avoid long subtitle blocks that cover the subject.
- B-roll: use B-roll only when it clarifies the point, hides a jump cut, or
  adds necessary visual evidence. Do not bury the speaker under generic filler.
- Handoff: for Shorts, render a preview and run QA when framing or captions are
  important, because vertical crop mistakes are hard to see from EDL alone.

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
          "speed": 2.0,
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

`speed` is an optional playback multiplier. Use `2.0` for 200% speed,
`0.5` for 50% speed, and omit it for normal speed. A retimed range keeps the
same `source_start`/`source_end` source span, but its timeline duration becomes
`(source_end - source_start) / speed`. `export-fcpxml` writes constant-speed
retimes as Resolve-compatible `timeMap` entries so the speed change remains
editable after import. FCPXML imports from Resolve may also include
`record_duration` to preserve Resolve's frame-rounded clip duration.

For gameplay recordings with a facecam overlay, transform presets can derive
safe zoom/pan/tilt values from a facecam rectangle:

```json
{
  "transform": {
    "preset": "gameplay-facecam",
    "facecam": {"x": 1600, "y": 720, "width": 320, "height": 360}
  }
}
```

Use `gameplay-facecam` when the scene should crop into the camera. Use
`gameplay-screen` with the same `facecam` rectangle when the scene should show
the gameplay/screen area while excluding the facecam. Rectangles can be pixel
coordinates or normalized values from `0.0` to `1.0`. Optional `padding`
expands the excluded/focused facecam rectangle before calculating the transform.

For Shorts that need the facecam and screen visible at the same time, keep a
single timing/audio range and add `visual_layers`. Each layer crops a source
region into a destination region on the vertical canvas. The preview renderer
composites the layered layout. FCPXML export promotes a same-source gameplay or
screen layer to the primary visible clip when possible, then writes the
remaining layers as connected video clips above it; this matches Resolve's own
export style for vertical gameplay/facecam timelines. When a layer's
`source_rect` and `dest_rect` aspect ratios differ, the crop is tightened
around its center to match the destination aspect in both preview and FCPXML
output:

```json
{
  "source": "A001",
  "source_start": 325.333,
  "source_end": 338.866,
  "record_start": 0,
  "visual_layers": [
    {
      "name": "Facecam",
      "source_rect": {"x": 0.0, "y": 0.43, "width": 0.24, "height": 0.36},
      "dest_rect": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.45}
    },
    {
      "name": "Screen",
      "source_rect": {"x": 0.13, "y": 0.12, "width": 0.67, "height": 0.67},
      "dest_rect": {"x": 0.0, "y": 0.50, "width": 1.0, "height": 0.45}
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

For tight social edits, remove more dead air but preserve audible word
starts/ends, keep record_start values contiguous, and avoid sub-minimum clips.
For documentary and long-form edits, preserve more natural pauses and avoid
rapid jump cuts unless the visual continuity is acceptable. For highlights,
favor self-contained phrases and avoid isolated filler words.

Always run `vtc validate-edl` before export. When transcript timings exist, the
validator warns if a source cut appears to land inside a spoken word or if the
timeline keeps only part of a transcript-backed sentence/segment. Validation
fails when a timeline has record gaps, record overlaps, or clips shorter than
the minimum duration. Final `vtc evaluate-edl` treats speech-boundary warnings
as blockers for handoff.

Before validation/export on speech edits, run `vtc refine-audio-cuts --replace`
on the EDL. The helper does not choose new dialogue content; it only expands
existing source_start/source_end boundaries outward when nearby source audio
indicates that the transcript timestamp would clip the audible word edge.

## Resolve Caveats

DaVinci Resolve's scripting API is strongest at project creation, media import,
timeline creation, timeline item property changes, markers, project export, and
project archive. Subtitle automation varies by Resolve version. Always generate
SRT as a stable handoff artifact even when trying to import subtitle tracks.

Retimed ranges are supported by the FCPXML exporter/importer, not by the Resolve
scripting backend. If the EDL contains `speed` or `record_duration`, export
FCPXML and import it into Resolve instead of using `build-resolve-project` or
`update-resolve-timeline`.

`vtc update-resolve-timeline` works against an existing Resolve project. It
rebuilds EDL timelines in that project; it does not live-edit individual clips
inside the currently selected timeline. If `--replace-existing` is used and
Resolve refuses to delete an active timeline, create a uniquely named timeline
first or switch to another timeline before retrying.

DaVinci Resolve Free may not expose external scripting. In that case, stop after
validated EDL, SRT, and FCPXML generation and tell the user to import the FCPXML
manually.
