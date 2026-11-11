# Choosing And Building The Cut

How to settle what kind of cut the user wants, plan a story-shaped cut with them, build it beat by beat, review it, and hand it over with editorial notes.

This guide covers the editorial half of the work. The mechanical half
(validation, audio-safe boundaries, preview, evaluation) is in the `session`
guide and applies to every cut built here.

## Settle The Kind Of Cut

People say "rough cut" or "edit this" loosely. Different kinds of cut need
different work, so know which one is wanted before choosing clips.

Proceed without asking when the request already names the kind: remove silence,
add captions, a Short about a named moment, cut to an attached script, every
mention of a topic. Otherwise ask once, with the options tool when one is
available, in plain words:

1. Cleanup: keep everything, remove silences and retakes.
2. Scene: one moment or story beat, usually 30 to 90 seconds.
3. Selects: a reel of every clip that matches something (best takes, a topic,
   B-roll of a subject).
4. Script edit: follow a written script line by line.
5. Short: one vertical, stand-alone idea. Read the `shorts` guide.
6. Rough cut: a full, story-shaped cut. This one is planned first.
7. Something else.

Say that the footage is ready and how much there is ("All 14 clips are
analyzed, about 52 minutes"), then ask. Do not explain why you are asking.

## The Direct Path: Cleanup, Scene, Selects, Script, Custom

These are built in the main conversation.

For a cleanup, follow the defaults in the `cut-craft` guide and proceed.

For the others, build the cut and show it to the user as a compact table before
exporting: order, source, in and out, length, and what is said or seen. Revise
until they say it is ready. Each revision shows the whole table again.

### Selects

- Put the selection criteria in the timeline `description` and name.
- One range per match. Find spoken matches with `vtc find-phrase`; find visual
  matches from summaries and contact sheets.
- Keep whole sentences, in source order unless asked otherwise, with markers on
  so each select is labelled in the editor.
- Report what you searched for and how many matches were left out and why.

### Script Edit

1. Get the script. It is pasted, attached, or lives in an app the user points
   to. If they only describe it, ask for it before going further.
2. Add its names and terms to the glossary and proofread the transcripts (the
   `footage` guide), so the script and the transcripts spell things the same.
3. Walk the script top to bottom. For each line, search a distinctive phrase:

   ```bash
   vtc find-phrase "a distinctive part of the line" --edit-dir <edit>
   ```

   When a line was recorded more than once, prefer the complete, fluent take.
   That is often the last one, but read each candidate before choosing.
4. Build the cut in script order, one range per line or beat, trimmed to the
   words of the script.
5. Where the footage does not contain a line, do not substitute a near match.
   List the missing lines and let the user decide: drop, reshoot, or accept a
   named alternative.
6. Leave out unscripted asides unless the user asks to keep them, and say which
   ones you left out when they are good.

Deliver a coverage table with the cut: each script line, the take used, and
anything missing.

## The Rough Cut Path

### Plan With The User

Planning happens in the main conversation, one question at a time, skipping
anything already answered.

1. Target length.
2. Whether they have a script or outline to follow. If they would rather cut
   from paper, write the full dialogue for them:
   `vtc dialogue --all --edit-dir <edit>`.
3. Read `edit/library.md` and every summary. They are short. This is the full
   picture of the material.
4. Propose three concepts, each a title and a one or two sentence arc. Make the
   first the straightforward version of what they most likely want. Make the
   other two structurally different, not rewordings.
5. Expand the chosen concept: format, three to six beats, and for each beat its
   purpose, its share of the runtime, and the footage that could carry it.
6. Revise with them. After every change, restate the whole plan.
7. Get an explicit yes. A requested tweak is not approval.
8. Save the approved plan to `edit/plans/plan_<short-name>_<YYYYMMDD_HHMMSS>.md`.

When nobody is there to answer, take the straightforward concept, save the plan,
and say at the top of the delivery which concept you chose and what the others
were.

### Build Beat By Beat

When the environment has sub-agents and the folder is large, hand the build to
one: give it the plan, the edit folder, and the names of this guide and the
`edl` guide. It works without asking questions and returns the EDL path and its
editorial notes. Otherwise build in the main thread the same way.

1. Take one beat from the plan.
2. Shortlist sources from the summaries. Read contact sheets and dialogue only
   for the shortlist.
3. Set in and out points from word times (`vtc find-phrase`, or the transcript
   words around the line).
4. Add the range to the EDL with `beat`, `quote`, `reason`, and a short
   `visual` note of what is on screen. Close enough is fine at this stage.
5. Move to the next beat.
6. After every three beats, look back. Replace an earlier clip if the same
   thing is said better later, tighten a beat that drags, and remove a point
   that now appears twice.

When a clip has dialogue, a complete sentence matters more than a tidy visual
cut. Trimming inside a sentence at word level is a normal tool: when a line
restates itself ("we tried to fix it, to actually really fix it properly"), end
the range after the first complete version.

The plan is the direction, not a paper cut. Deviate when the footage is better
than the plan expected, and record the deviation in the notes.

### Review Against The Format

With a complete first pass, review it as the thing it is meant to be (vlog,
gameplay episode, tutorial, documentary, Short).

- Beat lengths. A minute of static explanation can suit a documentary and sink
  a vlog. Five-second cutaways can suit a montage and feel twitchy in a
  tutorial.
- Dialogue tightness. Remove weak openers, filler, and restarts where it
  sharpens the line.
- Redundancy across beats. Keep the stronger statement of each point.
- The opening and the ending. Start on something worth hearing. End on a
  deliberate beat.
- Visual variety. Consecutive clips with the same framing read as jump cuts:
  use punch-ins for a talking head, or note a cutaway opportunity.

### Then Pass The Gates

A rough cut is still held to the technical gates in the `session` guide:
`vtc refine-audio-cuts`, `vtc validate-edl`, `vtc qa-transcript`, the preview
and its QA when framing matters, and `vtc evaluate-edl`. A cut that lands a
second off the word is not ready because it is "only a rough cut".

## Editorial Notes At Handoff

Every chosen cut (scene, selects, script, Short, rough cut) is delivered with
short notes, three to six lines, written as one editor to another:

- the alternatives you considered and what each would change ("the ending could
  land on the second boss instead; that swaps two clips");
- judgment calls and where you left the plan;
- pacing flags ("the intro runs 35 seconds; the takeoff alone would open it in
  8");
- lines or shots that were asked for and not found.

Offer to rebuild along any alternative. Small fixes are made directly in the EDL
and re-exported.

## Keeping Several Cuts

`edit/edl.json` is the working cut. When a folder holds more than one cut, give
each its own file directly inside `edit/` (`edit/edl.<short-name>.json`) and its
own `project_name`, so exports do not overwrite each other. EDL files must stay
directly inside `edit/`, because source paths resolve from its parent folder.
Reports under `edit/qa/` describe the last EDL that was checked. Run
`vtc backup --edit-dir <edit> --label <cut name>` after each delivery.

## Talking With The User

Speak as an editor. The user is cutting a video, not operating a tool.

- Say "the cut", "the timeline", "this take", "the opening". Do not mention
  EDL, JSON, file formats, or commands unless they ask how it works.
- "Got it. Three-second podium shots only. I'll start the edit." Not: "I'll
  write the EDL now."
- For long analysis, show a short plain checklist (transcripts, footage review,
  ready to plan) and update it. Keep helper names out of it.
- At delivery, give the file's location and the one-line import step for their
  editor (the `handoff` guide), then the editorial notes. Offer to open the
  file or reveal it in the file manager.
