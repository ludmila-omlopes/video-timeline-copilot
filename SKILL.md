---
name: video-timeline-copilot
description: "Use when editing local video footage with an AI agent: review and summarize footage, remove silence, build rough cuts, scenes, selects, script-based edits, highlights or Shorts, generate subtitles, and export editable timelines for DaVinci Resolve, Premiere Pro, or Final Cut Pro."
license: MIT
metadata:
  author: ludmila-omlopes
  version: "0.2.0"
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
17. Know the footage before choosing clips. Transcripts say what was said, not
    what happened on screen. For any cut where clips are chosen, and always for
    gameplay and other visual material, build contact sheets and written
    summaries first and cut from those plus the transcript.
18. Settle what kind of cut is wanted (cleanup, scene, selects, script edit,
    Short, rough cut) before selecting clips, and plan a story-shaped cut with
    the user before building it.
19. Speak to the user as an editor. Say "the cut", "the timeline", "this take".
    Keep file formats, JSON, and command names out of the conversation unless
    they ask how it works.
20. Remember what the user already told you. Read saved preferences and project
    context at the start, apply them without asking again, and save new
    standing rules when you learn them.
21. Deliver every chosen cut with short editorial notes: alternatives
    considered, judgment calls, and anything asked for that the footage did not
    contain.

## Guides

This file is the map. The detail lives in guides that ship with the CLI, so
they always match the installed commands. Print one with:

```bash
vtc guide <name>
```

`vtc guide` with no name lists them. When this skill folder contains
`helpers/guides/<name>.md`, reading that file is the same thing.

| Guide | Read it |
|---|---|
| `session` | Before the first edit of every session. The command-by-command flow, QA, and the self-evaluation gate. |
| `footage` | Before choosing clips for any creative cut, for gameplay or other visual material, or when the folder has more than three sources. Contact sheets, summaries, glossary, transcript proofreading, saved context, media checks, backups. |
| `cuts` | When the user wants a scene, selects, a script-based edit, or a rough cut, or the kind of cut is unclear. Planning, beat-by-beat building, review, editorial notes. |
| `edl` | Before writing or changing `edit/edl.json`. Ranges, transforms, gameplay presets, layers, speed, stills, mute. |
| `cut-craft` | For silence removal, highlights, talking heads, cut rhythm, repeated takes, and where cuts may land. |
| `shorts` | For Shorts, vertical, or any stand-alone social cut. |
| `handoff` | When delivering to Resolve, Premiere, Final Cut, or an unknown editor; when Resolve is open; for mixed frame rates and what each export carries. |
| `resolve-console`, `resolve-talking-head`, `fcpxml-audio` | When the `session` or `handoff` guide sends you there. |

Do not work from memory of a guide read in an earlier session. Commands and
rules change with the CLI; reread the guide the task calls for.

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

This skill needs a CLI that has the `guide` command. If `vtc guide` reports an
unknown command, the installed CLI is older than these instructions: ask for
approval, then rerun the install command above with `--force` and verify
`vtc guide` works before continuing. Do not fall back to instructions
remembered from an older version.

## Starting A Session

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
inventory indexes videos and still images, not every possible asset type;
inspect other supplied assets (music, separate audio, documents) separately and
do not claim the current EDL/exporters support an asset unless verified.

Take ownership of the internal workflow. Do not ask the user to name
`edit/edl.json` or specific helper commands.

Identify the destination editor early, before choosing a handoff or offering
editor integration. Use the user's request, the saved `editor` in
`vtc preferences` or `vtc context`, and available context first. If the
editor matters and remains unknown, ask one concise question such as "Which
editor do you want to open the timeline in?" Continue independent preparation
while waiting. Do not ask when the user already specified an editor or only
requested an FCPXML. If the editor is undecided, deliver the FCPXML and explain
that import behavior depends on the editor. Save the answer
(`vtc preferences --set editor=resolve|premiere|fcpx|other`) so it is not asked
again.

The `handoff` guide covers each editor, including checking early whether
DaVinci Resolve is running and how to work from a timeline that is already
open in it.

At handoff, distinguish what was generated, imported, checked for media links,
and visually inspected. Report any unverified or failed steps explicitly.

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

## The Flow

Every session follows this order. The `session` guide has the exact commands;
the other guides have the judgment.

1. Read what is already known: `vtc preferences`, and `vtc context` once the
   folder is identified.
2. Index the folder and check what is analyzed: `vtc inventory`, `vtc status`.
3. Know the footage, to the depth the request needs (`footage` guide):
   transcripts always; contact sheets, summaries, and transcript proofreading
   whenever clips are chosen or the picture matters. Do not propose a creative
   cut while `vtc status --ready` fails; finish the analysis or say what is
   missing and what that limits.
4. Settle the kind of cut. For mechanical requests, proceed on the defaults in
   `cut-craft`. Otherwise follow the `cuts` guide: ask once when the kind is
   unclear, and for a rough cut, agree a plan before building.
5. Write `edit/edl.json` (`edl` guide), from summaries, contact sheets, and
   word timings. Use only original user media as sources.
6. Make it technically sound: `vtc refine-audio-cuts`, `vtc validate-edl`,
   `vtc qa-transcript` for speech edits.
7. Export: `vtc verify-media`, `vtc export-srt`, `vtc export-fcpxml` (or
   `vtc export-xml` for Premiere and as the mixed-frame-rate fallback).
8. Check it: `vtc render-preview` and `vtc qa-preview` when framing or
   integrity matters and always for Shorts, then `vtc evaluate-edl`. Revise and
   repeat within the attempt limit.
9. Hand over (`handoff` guide): the timeline, the import step for their editor,
   what was and was not verified, and the editorial notes.
10. Save durable lessons (`vtc preferences --add-note`,
    `vtc context --add-note`, `--add-term`) and run `vtc backup`.

If an edit strategy could materially change the user's intended story, briefly
state the strategy before writing the EDL. For straightforward mechanical
requests like removing silence, proceed without asking for confirmation unless
there is ambiguity.

## Shorts

Whenever the user asks for Shorts, YouTube Shorts, vertical short-form, or a
social cut intended to stand alone, read the `shorts` guide
(`vtc guide shorts`) before selecting clips and follow its decision procedure,
framing rules, and QA checklist. The load-bearing defaults:

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
