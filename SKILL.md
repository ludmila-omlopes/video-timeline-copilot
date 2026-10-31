---
name: video-timeline-copilot
description: "Use when editing local video footage with an AI agent: remove silence, create rough cuts or highlight edits, generate subtitles, export FCPXML, or build DaVinci Resolve timelines."
license: MIT
metadata:
  author: ludmila-omlopes
  version: "0.1.0"
---

# Video Timeline Copilot

Use this skill when the user wants an AI agent to create an editable video
timeline from local media. Users should be able to ask for outcomes such as
"remove silent parts", "make a 30 second highlight", or "create a rough cut"
without knowing about `edit/edl.json`, SRT, FCPXML, or helper commands.

For Shorts and other social-first edits, treat the deliverable as a complete,
stand-alone piece of communication: one idea, a clear opening hook, a useful
payoff, and an intentional ending. Optimize for clarity and retention without
turning the cut into a sequence of arbitrary jump cuts.

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
12. Resolve integration is optional. When available, use a suitable Resolve MCP
    or the scripting backend for the requested handoff; otherwise deliver the
    validated EDL, SRT, and FCPXML and explain how to import manually.
13. Repeated delivery, false starts, and self-corrections are not useful
    story beats. When adjacent transcript phrases restate the same idea, keep
    only the cleanest complete version and discard the earlier/incomplete take.
14. A Short must end on a deliberate beat. Do not let the source clip stop after
    the payoff, during a sentence, or on an accidental reaction unless that
    abruptness is clearly part of the requested style.
15. Use the user's original media files as timeline sources by default. This
    includes separately recorded audio. Do not reference generated proxies,
    synchronized or transcoded intermediates, stems, previews, renders, or
    flattened clips in the EDL, FCPXML, or Resolve project unless the user
    explicitly requests or authorizes those derived files as sources.
16. Treat meaningful text already visible in the source as protected visual
    content in Shorts. Never let a vertical crop truncate a title, list, quote,
    label, chart, subtitle, or other text needed to understand the scene. Split
    the text-bearing interval into its own range and use a text-safe crop or a
    contain/letterbox layout until the text disappears.

## CLI Invocation

Use the `vtc` command when it is available on `PATH`. The recommended installer
uses `uv tool install` so `vtc` should be installed as an isolated tool.
One `vtc` installation can serve multiple agents that share an environment and
PATH; check availability before installing. Skill registration is separate:
when helping with setup, follow `install.md` to select only the user's agents,
inspect existing installations, and avoid duplicating or replacing them. Treat
Resolve MCP setup as a separate optional choice.

Before running the workflow for the first time in an environment, bootstrap the
helper CLI. Do not ask the user how to install `uv` or `vtc`; the commands are
listed in `install.md` (section "Agent bootstrap", in the same directory as this
file). Ask for approval to run installation commands when required by the agent
environment, then run the appropriate steps.

First check whether the helper CLI is available:

```bash
vtc --help
```

If `vtc` is missing and the user has not already approved installing the helper
CLI, stop before the video workflow. Explain that the skill instructions are
installed but the Python helper CLI is still required for media inventory,
transcription, EDL validation, subtitle export, FCPXML export, preview
rendering, evaluation, and Resolve handoff. Ask for permission before
installing it. Once the user approves, read `install.md` and run the "Agent
bootstrap" commands for the current platform. In short, they install `uv` if
needed and then run:

```bash
uv tool install "video-timeline-copilot[transcribe] @ git+https://github.com/ludmila-omlopes/video-timeline-copilot.git@main"
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

If the user approves using `uv` without installing the tool permanently, run
individual helper commands through the `uv tool run` invocation listed in
`install.md`. Treat `uv tool run` as an approved helper-CLI path, not as
permission to bypass the helper workflow.

## User-Facing Request Handling

At the start of every video-editing session, tell the user which working folder
will be used and that it needs to be accessible to the agent for reading and
writing. Ask them to put all assets intended for the edit there, including
video, audio, music, images, and other supplied material. If the user already
identified an accessible folder and its assets, acknowledge it without asking
again. If no folder is clear or it is not accessible, ask the user to choose
and grant access to one; do not start the media workflow until it is accessible.
Explain that generated outputs go in its `edit/` subdirectory. Do not move,
copy, or modify original assets without authorization. Do not silently omit
supplied assets: report missing or unsupported types and their impact. The
video inventory indexes videos, not every possible asset type; inspect other
supplied assets separately and do not claim the current EDL/exporters support
an asset unless verified.

Take ownership of the internal workflow. Do not ask the user to name
`edit/edl.json` or specific helper commands.

Identify the destination editor early, before choosing a handoff or offering
editor integration. Use the user's request and available context first. If the
editor matters and remains unknown, ask one concise question such as "Which
editor do you want to open the timeline in?" Continue independent preparation
while waiting. Do not ask when the user already specified an editor or only
requested an FCPXML. If the editor is undecided, deliver the FCPXML and explain
that import behavior depends on the editor.

- For DaVinci Resolve, offer optional integration to import and inspect the
  timeline when the user wants to work in Resolve. Use an available compatible
  MCP; if none is connected and the user wants one, follow the optional setup
  in `install.md`. Do not make setup a condition of delivery.
- For Final Cut Pro or another editor, deliver FCPXML and relevant import
  guidance. Check that the specific editor and requested features support it;
  do not promise compatibility or a native project without evidence. Do not
  offer Resolve MCP setup for another editor unless the user requests it.
- For an unknown or unsupported editor, explain the compatibility uncertainty
  and offer the EDL, SRT, and FCPXML as available artifacts; do not claim a
  successful import.

At handoff, distinguish what was generated, imported, checked for media links,
and visually inspected. Report any unverified or failed steps explicitly.

Early in each session, check whether DaVinci Resolve is running on the computer
that holds the working media, using a read-only process or app inventory when
available. Do this even if another editor is selected, but do not launch
Resolve or offer its integration solely because it is running. A running process
does not prove that scripting, MCP, or a project is connected; check those
separately when needed. Do not use an MCP call that automatically launches
Resolve as a running-state check. If the process state cannot be observed, say
it is unknown rather than assuming it is open or closed. If Resolve is the
destination and is not running, tell the user and, if they want live handoff,
help them open it; continue independent preparation or manual FCPXML delivery
as appropriate.

When the user asks to edit a timeline that is already open in Resolve, export
it first (**File > Export > Timeline**, FCPXML 1.8 `.fcpxml`, not the
`.fcpxmld` bundle) and read its structure before planning: compound clips, the
offsets and `timeMap` sync of separately recorded audio, muted camera audio,
and cuts the user already made. Treat earlier manual cuts as editorial intent
(they show which takes the user prefers), express new ranges against the
original media, and deliver a new timeline. Never modify the user's timeline.
See `docs/fcpxml-audio.md` for flattening compound clips.

Infer the footage root as follows:

1. If the current working directory contains `raw/`, use the current directory.
2. If the current working directory contains video files directly, use the
   current directory and treat those files as sources.
3. If exactly one obvious child directory contains `raw/`, use that child.
4. If multiple plausible footage roots or multiple source videos exist and the
   user's requested target is ambiguous, ask one concise clarification.

Create `edit/` automatically when needed.

Treat the inventory of user-provided media as the authoritative source set for
editable deliverables. Intermediates may be created under `edit/` for analysis,
transcription, synchronization measurement, preview rendering, or other helper
work, but keep them out of timeline source maps and exported asset resources.
When original audio was recorded separately, reference the original video and
original audio as separate assets and express synchronization through timeline
offsets or retiming. Do not replace them with a generated muxed or synchronized
clip. Preserve a mapping back to the originals whenever helper processing uses
an intermediate. Only depart from this policy when the user explicitly asks to
use a proxy, stem, transcode, render, or other derived file as an editable
source.

For simple requests, choose conservative defaults:

- "remove silence" / "remove silent parts": keep speech ranges based on word
  timestamp gaps, using the user's cut rhythm (see below) for how much air
  stays around speech. Prefer
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

Cut rhythm: before drafting any edit that removes pauses from speech, know how
tight the user wants the cuts. Run `vtc preferences` first. If a `cut_style` is
saved, or the request already says how tight to cut, use it without asking.
Otherwise ask one short question in plain language, with an example:

| Option to offer | `cut_style` | Air kept around speech | Pauses removed from |
|---|---|---|---|
| Very tight, YouTube jump cuts | `tight` | ~0.05 s | 0.25 s |
| Tight with a short breath | `social` | ~0.12 s | 0.35 s |
| Natural | `documentary` | ~0.25 s | 0.7 s |
| Relaxed, long-form | `longform` | ~0.35 s | 0.9 s |

Save the answer with `vtc preferences --set cut_style=<style>` and tell the
user it will be the default next time and can be changed. Fine-tune with
`--set padding=<seconds>` or `--set min_silence=<seconds>` when the user wants
something between presets. If nobody answers, use `documentary` and say so.
When the user tightens or loosens many cuts by hand after delivery, offer to
switch the saved style (or padding) to match, so the next draft starts closer.
- "Shorts", "YouTube Short", or vertical short-form edit: default to a 9:16
  timeline, usually `resolution: [1080, 1920]`, unless the user explicitly asks
  for another format. Select one self-contained idea and shape it as hook,
  minimal context, payoff, and a deliberate ending. Treat roughly 60-90 seconds
  as an editorial sweet spot, not a hard limit. A YouTube Short may run up to
  180 seconds; do not shorten strong material artificially, and allow a cut to
  exceed 120 seconds when the complete idea remains engaging. Do not pad to a
  target duration or combine unrelated highlights just to fill the timeline.
- "highlight" / "best moments": prioritize clear, self-contained transcript
  phrases and avoid isolated filler words, false starts, and duplicate
  deliveries.
- "Shorts" from gameplay with a facecam overlay: treat facecam handling as
  part of the vertical Shorts framing. Use `preset: gameplay-facecam` for
  reaction/commentary beats and `preset: gameplay-screen` for gameplay beats,
  with the same known facecam rectangle, so the screen-focused scene excludes
  the facecam instead of showing it again.
- Talking head (one person speaking to a fixed camera) edited with jump cuts:
  add small punch-ins so consecutive clips never share the same framing. Do it
  by default unless the saved preference `punch_ins` is `false` or the user
  declines, and mention it at handoff (see step 7). When the destination is
  Resolve, also offer a light background blur (saved preference
  `background_blur`). It is a Resolve grade, not EDL data: apply it after
  import, following `docs/resolve-talking-head.md`.
- B-roll over a talking head: cover sentences that name something visible
  (a game, a scene, an artwork, a menu) and keep the speaker on screen for
  opinions, asides and calls to action. Ask for the user's B-roll folder
  first and put downloads in a dedicated folder inside the project.
  Pre-render each shot with handles, place them on V2 from the Resolve
  Console, and move any timeline-level blur to the V1 clips so the B-roll
  stays sharp. Follow `docs/resolve-broll.md`.
- Explainer motion over a talking head (lists from a study, diagrams of a
  mechanism, comparisons): build one HyperFrames overlay per passage, timed to
  the words on the edited timeline, render WebM with alpha and place it on V3.
  Follow `docs/resolve-motion-hyperframes.md`.

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
   changes, action, on-screen text, objects, people, or framing. For Shorts,
   also do this before selecting clips whenever the crop, gameplay UI, facecam,
   or visual payoff affects which take is strongest:

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
   frames referenced by the visual context. For a Short, shortlist candidate
   ideas and check each for a hook, enough context to stand alone, a payoff, a
   clean ending, and a usable vertical crop. Inspect title cards and every
   interval containing meaningful source-baked text; a crop is not usable if it
   removes any required word or character. If `takes_packed.md` says no cached
   video analysis exists, treat visual matching as limited and say so when
   framing or visual selection materially affects the result.

6. Write `edit/edl.json` from the user's requested outcome. Combine transcript
   timing with visual-analysis signals when selecting clips. For draft silence
   removal, use the deterministic helper:

   ```bash
   vtc draft-silence-cut /path/to/footage/raw/interview.mp4 --edit-dir /path/to/footage/edit
   ```

   Without `--style`, the helper uses the saved `cut_style` preference (and any
   saved `padding`/`min_silence`). Pass `--style` only to override it for this
   edit. Apply the same air and pause values when cuts are written by hand.

   Then inspect/refine the generated EDL when the request requires more than
   mechanical silence removal. For a Shorts edit, prefer a deliberate manual
   selection of one idea over using a silence-cut draft as the final story.
   Before continuing, verify that every source entry resolves to an original
   user-provided media file unless the user explicitly authorized a derived
   source.

7. Refine speech cut boundaries from the source audio:

   ```bash
   vtc refine-audio-cuts /path/to/footage/edit/edl.json --replace
   ```

   This expands cut starts/ends outward only when RMS activity is found close
   to the boundary. It is meant to catch transcript timestamps that end a word
   slightly before the audible phoneme finishes.

   For talking-head edits with jump cuts, add punch-ins after the cuts are
   final:

   ```bash
   vtc punch-ins /path/to/footage/edit/edl.json --focus 0.55,0.33
   ```

   `--focus` is the speaker's eye position, normalized from the top-left of
   the frame. Read it from a sampled frame (`edit/video_frames/`) instead of
   guessing; the zoom keeps that point in place. The helper cycles framing at
   every cut (wide 1.0 and medium 1.12 by default). Short questions and
   exclamations, or ranges marked `"emphasis": true`, get a closer 1.25. A
   range that continues the previous one without a cut keeps its zoom. Ranges
   with an existing transform or `visual_layers` are left alone unless
   `--overwrite` is passed, and vertical timelines are skipped (Shorts use
   their own framing). Keep punch-ins subtle: about 1.1-1.3, never so tight
   that the head or hands touch the frame edge. Check headroom on the close
   level in the preview or in Resolve.

   To apply the same plan to a timeline already open in Resolve (for example
   after the user adjusted cuts there), pass `--lua edit/punch_ins.lua` and run
   that line in the Resolve Console. It refuses to run when the clip count
   differs. Work on a duplicate of the user's timeline
   (`Timeline:DuplicateTimeline`), never on the original.

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

   Before handoff, inspect the exported FCPXML asset resources. Confirm that
   every video and audio asset points to an original user-provided file and that
   separately recorded original audio remains a distinct editable source. Fail
   the handoff check if a helper-created proxy, synchronized clip, transcode,
   stem, preview, render, or flattened file appears as a source without the
   user's explicit authorization.

   For a Resolve handoff, do not treat original-media URLs alone as sufficient
   proof. Keep timeline component names tied to the original filenames and
   avoid per-range browser or source-clip names such as `P1_001`. When the
   original master clips already exist in the Media Pool, tell the user to
   disable **Automatically import source clips into media pool** in the XML
   import dialog and select the bin containing those masters. Also disable
   **Automatically set project settings** unless the user wants the project
   settings changed. After import,
   verify that Resolve conformed the timeline to the existing original clips
   and did not create one Media Pool item per edit. If it did, revise the XML
   component structure or use the Resolve scripting backend before handoff.

11. Render a preview and QA report for Shorts, and do so for any other edit when
    framing, captions, or technical timeline integrity is important:

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

   Read `preview_report.json` before handoff. For Shorts, inspect the first
   seconds, every crop change, caption placement, every source-baked text card,
   the payoff, and the final frame, not only the automated checks. Check the
   beginning, middle, and end of each text-bearing range and fail visual QA if
   any meaningful word or character is clipped or unreadable. Intentional black
   bars are acceptable when they preserve the full composition and text. Treat
   duration mismatches, transform coverage failures, audio-only/video-only
   regions, record gaps, record overlaps, and short clips as issues to correct.
   When FCPXML geometry itself is under inspection, render the exported XML
   separately instead of relying only on the EDL preview:

   ```bash
   vtc render-fcpxml-preview /path/to/footage/edit/timeline.fcpxml --resolve-crop-x-factor 2
   ```

   Use this to compare the actual exported XML layout against the EDL preview
   when debugging Resolve crop/transform import behavior.

   For speech edits, check what the timeline actually says:

   ```bash
   vtc qa-transcript /path/to/footage/edit/edl.json
   ```

   It transcribes each range on its own and flags phrases that restart a
   recent phrase, which is how retakes left in the edit look. Read
   `edit/qa/transcript_readout.md` (one line per range, with record timecodes)
   end to end, not only the flagged lines: it also shows clipped words and
   fragments. Parallel rhetorical phrases can be flagged too; keep them by
   setting `"allow_repeat": true` on the later range.

12. Run self-evaluation before final handoff. For Shorts, require the preview
    and strict cut warnings. For speech edits, also require transcript QA:

   ```bash
   vtc evaluate-edl /path/to/footage/edit/edl.json --require-preview --strict-cut-warnings --require-transcript-qa --attempt 1 --max-attempts 3
   ```

   Default output:

   ```text
   edit/qa/evaluation_report.json
   ```

   If the report status is `needs_revision`, revise `edit/edl.json`, rerun
   validation, SRT/FCPXML export, preview rendering, QA, and evaluation with the
   next `--attempt` value. Stop after `--max-attempts`; if the status is still
   `blocked`, tell the user what failed instead of continuing to iterate.

13. For a user who wants to continue in Resolve, use the available integration.
    If a Resolve MCP is already connected, inspect its tool descriptions and
    connection/capabilities first. Confirm the intended project and timeline
    from the request and readback before changing anything. A connection check
    may launch Resolve; follow the MCP's own setup and error guidance. Do not
    require or silently install an MCP: if none is connected, offer it as an
    optional way to work in the open project, without blocking delivery. If the
    user wants it installed, follow the optional MCP setup in `install.md`;
    their request authorizes setup, subject to the environment's permissions.

    When the MCP supports checked FCPXML import, use it for the generated XML
    if importing into Resolve is requested. Prefer checked/dry-run operations,
    use original media, and avoid sanitization or relinking that silently
    removes or substitutes clips. When existing masters should be reused, select
    the appropriate Media Pool bin and disable automatic source import if the
    integration supports it; otherwise explain the manual import option. Read
    back the imported timeline, its tracks and media links, and report offline
    or mismatched items. Structural readback does not prove visual correctness:
    inspect actual Resolve output when possible, especially framing and layers,
    or state that visual verification is pending. If import or inspection is
    unsupported or fails, report the limitation and use the scripting backend
    where appropriate or provide manual import steps.

    When external scripting is available, the CLI can also build a Resolve
    project directly from the EDL:

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
   wants matching timeline names deleted and recreated. Do not also build or
   import a second timeline unless requested or needed to resolve a failure.

   After importing a timeline whose speech comes from separately recorded
   audio, link each video item to its audio before handoff. Without links,
   trimming the video does not trim the audio. When the external recording
   replaces the camera audio, also offer to remove the muted camera-audio
   track. Use the MCP, the scripting backend, or the in-app Console recipes in
   `docs/resolve-console.md`, then save the project.

## Self-Evaluation Loop

Use `vtc evaluate-edl` as the final gate before handoff. It checks:

- export validity through `vtc validate-edl` rules
- cut-craft warnings such as cuts inside spoken words or partial
  transcript-backed sentences/segments
- preview QA when `edit/qa/preview_report.json` exists
- duration, audio-only, and video-only preview failures
- transcript QA when `edit/qa/transcript_report.json` exists: repeats across
  cuts block, repeats inside one range warn, and a report older than the EDL
  is stale
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

Whenever the user asks for Shorts, YouTube Shorts, vertical short-form, or a
social cut intended to stand alone, read `docs/shorts-guidelines.md` (relative
to this file) before selecting clips and follow its decision procedure, framing
rules, and QA checklist. The load-bearing defaults:

- Format: 9:16 vertical timeline, normally `resolution: [1080, 1920]`, unless
  the user explicitly requests another format.
- Story: one self-contained idea shaped as hook -> minimal context -> payoff ->
  deliberate ending. Aim near 60-90 seconds when the material naturally fits,
  but allow up to 180 seconds and cuts over 120 seconds when the idea earns the
  time. Do not shorten artificially, pad, or end on a clipped word or accidental
  beat.
- Gameplay with a facecam overlay: use the `gameplay-facecam` /
  `gameplay-screen` presets or `visual_layers`; never a generic center crop
  that repeats the facecam in a screen-focused scene.
- Source-baked text: protect the complete text-bearing region. Split the range
  when text appears or disappears; use a focused text-safe crop when it remains
  readable, otherwise fit the full horizontal composition inside the vertical
  canvas with intentional letterboxing.
- QA and handoff: always export SRT, render the preview, run `vtc qa-preview`,
  inspect the hook, crop changes, captions, payoff, and ending, and gate
  handoff on `vtc evaluate-edl --require-preview --strict-cut-warnings`.

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

For a horizontal title card or text-heavy frame that would be clipped by the
default vertical fill, give that interval its own range and reduce `zoom` until
the complete text-bearing region fits with safe side margins. With the current
post-fill transform semantics, a 16:9 source placed in a 9:16 canvas usually
needs a starting `zoom` near `0.316` for a full-frame contain layout. Derive the
general starting value as `(output_width / output_height) / (source_width /
source_height)`, then verify it in the rendered preview and exported FCPXML.
Black bars are preferable to cropped words. Resume the normal face/gameplay
crop in a new range as soon as the text is gone.

`allow_repeat: true` marks a range whose opening intentionally repeats a recent
phrase (anaphora, parallel questions) so `vtc qa-transcript` does not flag it.

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

When transcript timestamps and source audio activity disagree, trust the audio.
A larger Whisper model is not automatically better for timing: on one
45-minute Portuguese recording, `medium` dropped words and stretched one word
over 5 seconds where `small` stayed aligned with the audio.

For speech edits, verify the content, not only the boundaries: run
`vtc qa-transcript` after every EDL change and read its readout. Whisper often
writes a phrase once when it hears it twice in a row, so retakes can be missing
from the source transcript and only show up when each range is transcribed on
its own. List ambiguous editorial removals for the user with approximate
timecodes.

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

DaVinci Resolve Free may not expose external scripting. Its in-app Console
(**Workspace > Console**, Lua) does run the scripting API against the open
project; use it for small post-import fixes such as linking clips or removing a
track (`docs/resolve-console.md`). Some MCP servers offer
an in-app bridge depending on the Resolve version and setup; consult the
available server's instructions rather than assuming it works. If no suitable
integration is available, deliver validated EDL, SRT, and FCPXML and tell the
user how to import the FCPXML manually.
